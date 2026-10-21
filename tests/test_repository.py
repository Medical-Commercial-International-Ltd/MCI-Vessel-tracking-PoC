from datetime import date, datetime, timezone

from app.models import (
    AnalysisDocument,
    AnalysisInput,
    AnalysisStatistics,
    AuditRecord,
    DataQuality,
    DatePeriod,
    RiskAssessment,
    RiskComponents,
    VesselIdentity,
)
from app.repositories import FileAnalysisRepository
import os
import pytest


def make_analysis() -> AnalysisDocument:
    now = datetime.now(timezone.utc)
    return AnalysisDocument(
        id="analysis_test",
        analysis_id="analysis_test",
        status="completed",
        created_at=now,
        created_by="tester@mciuw.com",
        input=AnalysisInput(
            identifier_type="MMSI",
            identifier="123456789",
            period=DatePeriod(from_date=date(2021, 1, 1), to_date=date(2025, 12, 31)),
        ),
        vessel=VesselIdentity(name="MCI Test", mmsi=["123456789"]),
        risk=RiskAssessment(
            score=42,
            band="ELEVATED",
            confidence="HIGH",
            components=RiskComponents(worst_encounter=50, top_three_average=40, recurrence=25),
        ),
        statistics=AnalysisStatistics(
            ais_observation_count=100,
            observed_days=20,
            named_storm_encounters=1,
            hours_within_200_nm=3,
            hours_within_34_kt_wind_field=0,
            minimum_distance_nm=120,
        ),
        data_quality=DataQuality(
            rating="HIGH",
            identity_confidence="HIGH",
            years_covered=[2021, 2022, 2023, 2024, 2025],
        ),
        audit=AuditRecord(
            calculation_started_at=now,
            calculation_completed_at=now,
            application_version="test",
            calculation_hash="abc123",
        ),
    )


def test_analysis_round_trip(tmp_path):
    repository = FileAnalysisRepository(tmp_path)
    analysis = make_analysis()
    repository.save_analysis(analysis)

    loaded = repository.get_analysis("mci", "analysis_test")

    assert loaded is not None
    assert loaded.id == analysis.id
    assert loaded.risk.score == 42
    assert repository.list_analyses("mci")[0].analysis_id == "analysis_test"


def test_json_uses_cosmos_compatible_field_names(tmp_path):
    repository = FileAnalysisRepository(tmp_path)
    repository.save_analysis(make_analysis())
    contents = (tmp_path / "mci" / "analysis_test" / "analysis.json").read_text()

    assert '"tenantId": "mci"' in contents
    assert '"analysisId": "analysis_test"' in contents
    assert '"schemaVersion": "1.0"' in contents


@pytest.mark.skipif(os.name != "nt", reason="Windows file replacement locking")
def test_atomic_write_retries_temporary_windows_lock(tmp_path, monkeypatch):
    from app import repositories
    original = repositories.os.replace
    calls = []
    def locked_once(source, target):
        calls.append(target)
        if len(calls) == 1:
            raise PermissionError("temporary file lock")
        return original(source, target)
    monkeypatch.setattr(repositories.os, "replace", locked_once)
    monkeypatch.setattr(repositories.time, "sleep", lambda _: None)
    repository = FileAnalysisRepository(tmp_path)
    repository.save_analysis(make_analysis())
    assert repository.get_analysis("mci", "analysis_test").risk.score == 42
    assert len(calls) == 2

