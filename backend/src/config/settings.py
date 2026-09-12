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
    kakao_walk_path: str = '/v2/routing/walk'
    # 요청 쿼리 틀. 문서의 파라미터 이름이 다르면 배포 환경변수로만 바꿉니다.
    # {sx} {sy} {ex} {ey} 자리에 출발·도착 경도·위도가 들어갑니다.
    # 예) origin={sx},{sy}&destination={ex},{ey}
    kakao_transit_query: str = 'start_x={sx}&start_y={sy}&end_x={ex}&end_y={ey}'
    kakao_walk_query: str = 'start_x={sx}&start_y={sy}&end_x={ex}&end_y={ey}'
    # 파라미터를 어디에 실을지. 'get'(쿼리스트링) | 'post-json' | 'post-form'.
    # 현재 카카오맵 REST 는 GET 쿼리스트링으로 동작이 확인되어 기본값 그대로 두면 됩니다.
    kakao_request_style: Literal['get', 'post-json', 'post-form'] = 'get'
    # true 면 GET /api/debug/upstream/{walk|transit} 로 카카오 원본 응답을 그대로 볼 수 있습니다.
    # 응답 필드 이름을 확인하는 용도입니다. 키는 응답에 없으므로 노출되지 않습니다.
    debug_raw_upstream: bool = False

    odsay_api_key: SecretStr = SecretStr('')

    # 날씨 (F6). 키가 없으면 날씨 없이 동작합니다. 실패해도 비교는 막지 않습니다.
    # weatherapi = WeatherAPI.com (한국어 날씨 문구·강수확률·아이콘 제공), openweather = OpenWeatherMap
    weather_provider: Literal['weatherapi', 'openweather'] = 'weatherapi'
    weather_api_key: SecretStr = SecretStr('')
    weather_timeout_seconds: float = Field(default=4, gt=0)

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
    # 이보다 먼 구간은 조회하지 않습니다. 카카오 도보 경로가 약 30km 를 넘으면 결과를 주지 않습니다.
    max_distance_km: float = Field(default=30, gt=0)

    # 남용 방지. IP 당 분당 /api 요청 수. 0 이면 제한하지 않습니다.
    rate_limit_per_minute: int = Field(default=60, ge=0)
    # 같은 출발·도착(소수 4자리 ≈ 10m)의 비교 결과를 재사용하는 시간(초). 0 이면 캐시하지 않습니다.
    compare_cache_seconds: int = Field(default=120, ge=0)
    # 적립권(바우처) 유효 시간. /api/compare 응답을 받고 이 시간 안에 "걸어갈래요"를 눌러야 합니다.
    savings_voucher_ttl_seconds: int = Field(default=1800, gt=0)
