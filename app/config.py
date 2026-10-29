from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    max_routes: int = Field(default=5, ge=1, le=5)
    default_max_routes: int = Field(default=5, ge=1, le=5)
    place_search_limit: int = Field(default=10, ge=1, le=20)
    place_search_radius_meters: int = Field(default=50_000, ge=1_000, le=100_000)
    preference_corridor_meters: int = Field(default=500, ge=50, le=2_000)
    preference_match_bonus: float = Field(default=0.35, ge=0, le=1)
    preference_route_candidates: int = Field(default=3, ge=0, le=5)
    preference_search_radius_meters: int = Field(default=5_000, ge=500, le=50_000)
    preference_search_points_per_route: int = Field(default=3, ge=1, le=5)


settings = AppSettings()
