from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    # 요청 쿼리 틀. 문서의 파라미터 이름이 다르면 배포 환경변수로만 바꿉니다.
    # {sx} {sy} {ex} {ey} 자리에 출발·도착 경도·위도가 들어갑니다.
    # 예) origin={sx},{sy}&destination={ex},{ey}
    kakao_transit_query: str = 'sx={sx}&sy={sy}&ex={ex}&ey={ey}'
    kakao_walk_query: str = 'sx={sx}&sy={sy}&ex={ex}&ey={ey}'
    # 파라미터를 어디에 실을지. 'get'(쿼리스트링) | 'post-json' | 'post-form'.
    # 데브톡에 "sx is required" (파라미터는 정상 포함) 사례가 있어, 문서가 POST 본문을
    # 요구하면 배포 환경변수로만 바꿀 수 있게 둡니다.
    kakao_request_style: Literal['get', 'post-json', 'post-form'] = 'get'
    # true 면 GET /api/debug/upstream/{walk|transit} 로 카카오 원본 응답을 그대로 볼 수 있습니다.
    # 응답 필드 이름을 확인하는 용도입니다. 키는 응답에 없으므로 노출되지 않습니다.
    debug_raw_upstream: bool = False

    odsay_api_key: SecretStr = SecretStr('')

    # 카카오 로그인(OAuth) 설정
    kakao_client_secret: SecretStr = SecretStr('')
    kakao_redirect_uri: str = 'http://localhost:8000/api/auth/kakao/callback'
    frontend_url: str = 'http://localhost:5173'
    session_secret_key: SecretStr = SecretStr('')
    session_cookie_secure: bool = False
    upstream_timeout_seconds: float = Field(default=10, gt=0)
    # NoDecode 를 붙여야 환경변수 문자열이 JSON 으로 먼저 해석되지 않습니다.
    # 그래야 아래 검사기에서 쉼표 구분과 JSON 배열을 모두 받을 수 있습니다.
    cors_origins: Annotated[list[str], NoDecode] = ['http://localhost:5173']

    @field_validator('cors_origins', mode='before')
    @classmethod
    def _read_origins(cls, value):
        """허용 출처를 쉼표 구분 문자열이나 JSON 배열로 받습니다.

        JSON 형식만 받으면 CORS_ORIGINS=https://example.com 처럼 적었을 때
        서버가 아예 뜨지 않습니다. 배포에서 자주 걸리는 부분이라 둘 다 받습니다.
        """
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith('['):
            import json
            return json.loads(text)
        return [part.strip() for part in text.split(',') if part.strip()]
    walk_max_minutes: float = Field(default=30, gt=0)
    walk_max_meters: float = Field(default=2000, gt=0)
