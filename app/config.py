from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VTON_", env_file=".env", extra="ignore")
    app_name: str = Field(default="OpenTryOn", min_length=1, max_length=40)
    app_tagline: str = Field(default="开源 AI 虚拟试衣", min_length=1, max_length=80)
    repository_url: str = ""
    provider: Literal["fashn", "remote", "space"] = "fashn"
    weights_dir: Path = Path("weights")
    data_dir: Path = Path("data")
    device: Literal["auto", "cuda", "cpu"] = "auto"
    api_key: str = ""
    remote_url: str = ""
    remote_api_key: str = ""
    retention_hours: int = Field(default=24, ge=1, le=720)
    max_pending: int = Field(default=8, ge=1, le=100)
