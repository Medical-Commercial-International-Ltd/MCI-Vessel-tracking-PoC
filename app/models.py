from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class DocumentModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class DatePeriod(DocumentModel):
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")

    @field_validator("to_date")
    @classmethod
    def validate_period(cls, value: date, info):
        start = info.data.get("from_date")
        if start and value < start:
            raise ValueError("The end date must be on or after the start date")
        return value


class AnalysisInput(DocumentModel):
    identifier_type: Literal["IMO", "MMSI"]
    identifier: str
    period: DatePeriod
    coastal_limit_nm: float = Field(default=75, gt=0, le=200)
    storm_proximity_nm: float = Field(default=200, gt=0, le=500)
    region: str = "US_COASTAL"


class VesselIdentity(DocumentModel):
    name: str
    imo: str | None = None
    mmsi: list[str] = Field(default_factory=list)
    vessel_type: str = "Unknown"
    flag: str | None = None
    length_m: float | None = None
    width_m: float | None = None
    draft_m: float | None = None


class RiskComponents(DocumentModel):
    worst_encounter: int
    top_three_average: int
    recurrence: int


class RiskAssessment(DocumentModel):
    model_version: str = "TC-EXPOSURE-v0.1"
    score: int = Field(ge=0, le=100)
    band: Literal["LOW", "MODERATE", "ELEVATED", "HIGH", "SEVERE"]
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]
    components: RiskComponents
    underwriter_referral: bool = False
    actuarially_calibrated: bool = False


class AnalysisStatistics(DocumentModel):
    ais_observation_count: int = Field(ge=0)
    observed_days: int = Field(ge=0)
    named_storm_encounters: int = Field(ge=0)
    hours_within_200_nm: float = Field(ge=0)
    hours_within_34_kt_wind_field: float = Field(ge=0)
    minimum_distance_nm: float | None = Field(default=None, ge=0)
    distance_travelled_nm: float = Field(default=0, ge=0)
    average_speed_kt: float = Field(default=0, ge=0)
    maximum_speed_kt: float = Field(default=0, ge=0)


class DataQuality(DocumentModel):
    rating: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]
    identity_confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]
    years_covered: list[int] = Field(default_factory=list)
    significant_storm_period_gaps: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)


class SourceReference(DocumentModel):
    provider: str
    dataset: str
    retrieved_at: datetime


class ArtifactReference(DocumentModel):
    type: str
    storage_key: str
    content_type: str
    sha256: str | None = None


class AuditRecord(DocumentModel):
    calculation_started_at: datetime
    calculation_completed_at: datetime
    application_version: str
    calculation_hash: str


class AnalysisDocument(DocumentModel):
    id: str
    document_type: Literal["vesselRiskAnalysis"] = "vesselRiskAnalysis"
    schema_version: str = "1.0"
    tenant_id: str = "mci"
    analysis_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    is_synthetic: bool = True
    synthetic_notice: str | None = "Demonstration data — not for underwriting use"
    created_at: datetime
    created_by: str
    input: AnalysisInput
    vessel: VesselIdentity
    risk: RiskAssessment
    statistics: AnalysisStatistics
    encounter_ids: list[str] = Field(default_factory=list)
    data_quality: DataQuality
    sources: list[SourceReference] = Field(default_factory=list)
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    audit: AuditRecord


class Position(DocumentModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class StormDetails(DocumentModel):
    id: str
    name: str
    classification: str
    category: int | None = Field(default=None, ge=1, le=5)


class ClosestApproach(DocumentModel):
    timestamp: datetime
    distance_nm: float = Field(ge=0)
    vessel_position: Position
    storm_position: Position


class EncounterExposure(DocumentModel):
    duration_within_200_nm_hours: float = Field(ge=0)
    duration_within_34_kt_wind_field_hours: float = Field(default=0, ge=0)
    strongest_wind_field: str
    maximum_storm_wind_kt: int = Field(ge=0)


class EventRisk(DocumentModel):
    event_score: int = Field(ge=0, le=100)
    proximity_points: int = Field(ge=0)
    intensity_points: int = Field(ge=0)
    wind_field_points: int = Field(ge=0)
    duration_points: int = Field(ge=0)


class EncounterDocument(DocumentModel):
    id: str
    document_type: Literal["stormEncounter"] = "stormEncounter"
    schema_version: str = "1.0"
    tenant_id: str = "mci"
    analysis_id: str
    storm: StormDetails
    closest_approach: ClosestApproach
    exposure: EncounterExposure
    risk: EventRisk


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
