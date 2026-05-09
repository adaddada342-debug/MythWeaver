from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


def _default_data_dir() -> Path:
    return Path(os.getenv("MYTHWEAVER_DATA_DIR", Path.home() / ".mythweaver"))


class Settings(BaseModel):
    """Runtime settings with no required AI provider."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    data_dir: Path = Field(default_factory=_default_data_dir)
    output_dir: Path = Field(default_factory=lambda: _default_data_dir() / "output")
    cache_db: Path = Field(default_factory=lambda: _default_data_dir() / "cache.sqlite3")
    modrinth_base_url: str = "https://api.modrinth.com/v2"
    modrinth_user_agent: str = Field(
        default_factory=lambda: os.getenv(
            "MYTHWEAVER_MODRINTH_USER_AGENT",
            "local/MythWeaver/0.1.0 (agent-first modpack intelligence service)",
        )
    )
    prism_path: str | None = Field(default_factory=lambda: os.getenv("MYTHWEAVER_PRISM_PATH"))
    prism_root: Path | None = Field(
        default_factory=lambda: (
            Path(value) if (value := os.getenv("MYTHWEAVER_PRISM_ROOT")) else None
        )
    )
    prism_profile: str | None = Field(default_factory=lambda: os.getenv("MYTHWEAVER_PRISM_PROFILE"))
    prism_executable_path: str | None = Field(default_factory=lambda: os.getenv("MYTHWEAVER_PRISM_EXECUTABLE_PATH"))
    prism_instances_path: Path | None = Field(
        default_factory=lambda: (
            Path(value) if (value := os.getenv("MYTHWEAVER_PRISM_INSTANCES_PATH")) else None
        )
    )
    prism_account_name: str | None = Field(default_factory=lambda: os.getenv("MYTHWEAVER_PRISM_ACCOUNT_NAME"))
    launch_timeout_seconds: int = Field(default_factory=lambda: int(os.getenv("MYTHWEAVER_LAUNCH_TIMEOUT_SECONDS", "300")))
    java_path: str | None = Field(default_factory=lambda: os.getenv("MYTHWEAVER_JAVA_PATH"))
    validation_enabled: bool = Field(
        default_factory=lambda: os.getenv("MYTHWEAVER_VALIDATION_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    )
    ai_base_url: str | None = Field(default_factory=lambda: os.getenv("MYTHWEAVER_AI_BASE_URL"))
    ai_api_key: str | None = Field(default_factory=lambda: os.getenv("MYTHWEAVER_AI_API_KEY"))
    ai_model: str | None = Field(default_factory=lambda: os.getenv("MYTHWEAVER_AI_MODEL"))

    @property
    def ai_enabled(self) -> bool:
        return bool(self.ai_base_url)

    @property
    def resolved_prism_path(self) -> str | None:
        return self.prism_executable_path or self.prism_path

    @property
    def resolved_prism_root(self) -> Path | None:
        return self.prism_instances_path or self.prism_root

    @property
    def resolved_prism_profile(self) -> str | None:
        return self.prism_account_name or self.prism_profile

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_db.parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
