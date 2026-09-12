from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / '.env',
        env_file_encoding='utf-8', extra='ignore',
    )
    odsay_api_key: SecretStr = SecretStr('')
    kakao_rest_api_key: SecretStr = SecretStr('')
    kakao_client_secret: SecretStr = SecretStr('')
    kakao_redirect_uri: str = 'http://localhost:8000/api/auth/kakao/callback'
    frontend_url: str = 'http://localhost:5173'
    session_secret_key: SecretStr = SecretStr('')
    session_cookie_secure: bool = False
    upstream_timeout_seconds: float = Field(default=10, gt=0)
    cors_origins: list[str] = ['http://localhost:5173']
    walk_max_minutes: float = Field(default=30, gt=0)
    walk_max_meters: float = Field(default=2000, gt=0)
