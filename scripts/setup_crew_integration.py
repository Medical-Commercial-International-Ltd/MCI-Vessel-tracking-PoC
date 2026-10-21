"""Import saved test evidence and optionally create a random test vessel roster.

Run from the repository: python -m scripts.setup_crew_integration
Use --configure-development to enable development access in the ignored .env.
Use --random-test-roster to assign Sam/Freya to a randomly selected assessed vessel.
The generated test-roster.json makes repeated setup idempotent.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import re

from app.config import Settings
from app.crewdentials import import_development_snapshots, CrewdentialsProvider
from app.crew import CrewRepository
from app.crew_risk import assess_crew, combine_risk
from app.repositories import FileAnalysisRepository, _atomic_json_write

ROOT = Path(__file__).resolve().parents[1]


def setup(configure=False, random_roster=False):
    if configure:
        collection = json.loads((ROOT / "Crewdentials Crew Documents API.postman_collection.json").read_text(encoding="utf-8-sig"))
        values = {row["key"]: row["value"] for row in collection["variable"]}
        if values["BASE_URL"] != "https://crewdentials-api-dev.onrender.com/api":
            raise SystemExit("Only the supplied development environment may be configured.")
        path = ROOT / ".env"
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        for key, value in {"CREW_PROVIDER": "crewdentials", "CREWDENTIALS_BASE_URL": values["BASE_URL"],
                           "CREWDENTIALS_API_KEY": values["API_KEY"]}.items():
            if re.search(r"^" + key + "=", content, re.M):
                content = re.sub(r"^" + key + r"=.*$", lambda _: key + "=" + value, content, flags=re.M)
            else:
                content = content.rstrip() + "\n" + key + "=" + value + "\n"
        path.write_text(content, encoding="utf-8")
        print("Development crew access configured in ignored .env (credentials not printed).")
    settings = Settings(crew_provider="crewdentials")
    profiles = import_development_snapshots(settings.data_dir)
    print("Connected test profiles registered:", len(profiles))
    if not random_roster:
        return
    root = settings.data_dir / "crew"
    roster_path = root / "test-roster.json"
    if roster_path.exists():
        print("Random test roster already exists:", roster_path)
        return
    repository = FileAnalysisRepository(settings.analyses_dir)
    analyses = repository.list_analyses("mci")
    candidates = [a for a in analyses if a.status == "completed" and a.is_synthetic == (settings.analysis_provider == "demo")]
    store = CrewRepository(root / "assignments.sqlite")
    candidates = [a for a in candidates if not store.list(store.key(a))]
    if not candidates:
        raise SystemExit("No assessed vessel with an empty roster is available. Run a vessel analysis first.")
    generator = random.SystemRandom()
    analysis = generator.choice(candidates)
    roles = ["Captain", "Chief officer"]
    generator.shuffle(roles)
    today = datetime.now(timezone.utc).date()
    provider = CrewdentialsProvider(settings)
    assignments = []
    for profile_id, role in zip(["01a1445b-3696-7470-90a5-93a29a28e6cd", "01a1445f-010f-7724-9aca-ba417003f334"], roles):
        person = provider.get(profile_id)
        if not person:
            raise SystemExit("Import the two provider-created profiles first.")
        store.save(store.key(analysis), person, role, today, today + timedelta(days=180), "MCI POC random test setup")
        assignments.append({"crewProfileId": profile_id, "name": person["first_name"] + " " + person["last_name"], "role": role})
    report = {"isTestData": True, "selection": "Random existing assessed vessel and shuffled deck roles; not actual crewing information",
              "analysisId": analysis.analysis_id, "vessel": analysis.vessel.model_dump(mode="json"),
              "startDate": today.isoformat(), "endDate": (today + timedelta(days=180)).isoformat(), "assignments": assignments}
    _atomic_json_write(roster_path, report)
    for other in analyses:
        if store.key(other) == store.key(analysis):
            other.underwriting = combine_risk(other, assess_crew(store.list(store.key(other)), provider))
            other.schema_version = "1.1"
            repository.save_analysis(other)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configure-development", action="store_true")
    parser.add_argument("--random-test-roster", action="store_true")
    args = parser.parse_args()
    setup(args.configure_development, args.random_test_roster)
