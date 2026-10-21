from __future__ import annotations

import json
import os
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path

from app.models import AnalysisDocument, EncounterDocument


class AnalysisRepository(ABC):
    @abstractmethod
    def save_analysis(self, analysis: AnalysisDocument) -> None: ...

    @abstractmethod
    def get_analysis(self, tenant_id: str, analysis_id: str) -> AnalysisDocument | None: ...

    @abstractmethod
    def list_analyses(self, tenant_id: str) -> list[AnalysisDocument]: ...

    @abstractmethod
    def save_encounter(self, encounter: EncounterDocument) -> None: ...

    @abstractmethod
    def list_encounters(self, tenant_id: str, analysis_id: str) -> list[EncounterDocument]: ...


class FileAnalysisRepository(AnalysisRepository):
    """Cosmos-compatible JSON persistence for the localhost application."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _analysis_dir(self, tenant_id: str, analysis_id: str) -> Path:
        safe_tenant = _safe_segment(tenant_id)
        safe_analysis = _safe_segment(analysis_id)
        return self.root / safe_tenant / safe_analysis

    def save_analysis(self, analysis: AnalysisDocument) -> None:
        target = self._analysis_dir(analysis.tenant_id, analysis.analysis_id) / "analysis.json"
        _atomic_json_write(target, analysis.model_dump(mode="json", by_alias=True))

    def get_analysis(self, tenant_id: str, analysis_id: str) -> AnalysisDocument | None:
        target = self._analysis_dir(tenant_id, analysis_id) / "analysis.json"
        if not target.exists():
            return None
        with target.open("r", encoding="utf-8") as handle:
            return AnalysisDocument.model_validate(json.load(handle))

    def list_analyses(self, tenant_id: str) -> list[AnalysisDocument]:
        tenant_dir = self.root / _safe_segment(tenant_id)
        if not tenant_dir.exists():
            return []
        documents: list[AnalysisDocument] = []
        for target in tenant_dir.glob("*/analysis.json"):
            try:
                with target.open("r", encoding="utf-8") as handle:
                    documents.append(AnalysisDocument.model_validate(json.load(handle)))
            except (json.JSONDecodeError, ValueError):
                continue
        return sorted(documents, key=lambda item: item.created_at, reverse=True)

    def save_encounter(self, encounter: EncounterDocument) -> None:
        target = (
            self._analysis_dir(encounter.tenant_id, encounter.analysis_id)
            / "encounters"
            / f"{_safe_segment(encounter.id)}.json"
        )
        _atomic_json_write(target, encounter.model_dump(mode="json", by_alias=True))

    def list_encounters(self, tenant_id: str, analysis_id: str) -> list[EncounterDocument]:
        encounter_dir = self._analysis_dir(tenant_id, analysis_id) / "encounters"
        if not encounter_dir.exists():
            return []
        results: list[EncounterDocument] = []
        for target in encounter_dir.glob("*.json"):
            try:
                with target.open("r", encoding="utf-8") as handle:
                    results.append(EncounterDocument.model_validate(json.load(handle)))
            except (json.JSONDecodeError, ValueError):
                continue
        return sorted(results, key=lambda item: item.closest_approach.timestamp)


def _safe_segment(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    cleaned = "".join(character for character in value if character in allowed)
    if not cleaned or cleaned != value:
        raise ValueError("Unsafe storage identifier")
    return cleaned


def _atomic_json_write(target: Path, payload: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(5):
            try:
                os.replace(temporary_name, target)
                break
            except PermissionError:
                # Windows readers/indexers can briefly deny replacement. Preserve
                # the original and retry the same atomic operation for < 1 second.
                if os.name != "nt" or attempt == 4:
                    raise
                time.sleep(0.025 * (2 ** attempt))
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
