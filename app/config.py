from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MCI Marine Risk Intelligence"
    app_env: str = "development"
    session_secret: str = "development-only-change-me"
    admin_email: str = "demo@mciuw.com"
    admin_password: str = "ChangeMe123!"
    analysis_provider: str = "demo"
    demo_seed_count: int = Field(default=248, ge=0, le=5000)
    data_dir: Path = Path("data")
    ais_cache_dir: Path = Path("C:/MCI-AIS-Cache")
    ais_cache_limit_gb: int = Field(default=100, ge=5, le=500)

    @property
    def analyses_dir(self) -> Path:
        return self.data_dir / "analyses"

    @property
    def users_file(self) -> Path:
        return self.data_dir / "users" / "local-users.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
