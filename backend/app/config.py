"""App configuration, loaded from environment variables / a local .env file."""
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PRIORITON_", extra="ignore")

    # Optional now - see app.security.get_or_create_secret_key. Set this
    # explicitly only if you want to manage the encryption key yourself
    # (Docker/CI, or just a preference) instead of letting it auto-provision
    # into the OS keyring on first run.
    secret_key: Optional[str] = None
    db_path: str = "./prioriton.db"
    sync_interval_minutes: int = 15
    # How often (days) the recommendation-eligibility job checks for a new
    # weekly recommendation to generate - see app.recommendation_service.
    recommendation_check_interval_hours: int = 24
    recommendation_period_days: int = 7
    frontend_origin: str = "http://localhost:5173"

    # Unprefixed since it's a standard external-service credential name, not
    # Prioriton-specific config - matches how most tooling expects it to be set.
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = "claude-sonnet-5"

    # For a shared public demo deployment only - see app/demo.py and
    # DEPLOY_DEMO.md. Disables connecting real Canvas/Gradescope/PrairieLearn
    # accounts and generating real AI recommendations (both would mean a
    # stranger's real data or a real Anthropic API call landing on a public,
    # shared instance), and periodically wipes + reseeds sample data so the
    # demo stays interactive without one visitor's changes lingering for the
    # next. Never turn this on for a real personal deployment.
    demo_mode: bool = False
    demo_reset_interval_hours: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
