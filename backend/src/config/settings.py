from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / '.env',
        env_file_encoding='utf-8', extra='ignore',
    )
    # 경로 제공자. 'kakao' 또는 'odsay'. 키가 준비된 쪽으로 바꾸면 됩니다.
    route_provider: Literal['kakao', 'odsay'] = 'kakao'

    # 카카오맵 REST API 키 (카카오디벨로퍼스 > 앱 > 앱 키 > REST API 키).
    # [제품 설정] > [카카오맵] 에서 사용 설정을 켜야 호출됩니다.
    kakao_rest_api_key: SecretStr = SecretStr('')
    # 엔드포인트 경로. 문서 확인 후 다르면 배포 환경변수로만 고치면 됩니다.
    kakao_transit_path: str = '/v2/routing/publictraffic'
    kakao_walk_path: str = '/v2/routing/pedestrian'

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
