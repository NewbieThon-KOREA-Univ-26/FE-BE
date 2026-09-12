"""카카오맵 REST API 로 도보·대중교통 경로를 조회합니다.

2026년 7월에 열린 카카오맵 신규 REST API 4종(대중교통 경로 조회, 도보 경로 조회,
자전거 경로 조회, 정적 지도 조회)을 씁니다. 카카오디벨로퍼스의
[앱] > [제품 설정] > [카카오맵] 에서 [사용 설정] 을 켜면 별도 심사 없이 쓸 수 있습니다.

왜 브라우저가 아니라 여기서 부르는가
--------------------------------------
1. REST API 키는 비밀입니다. 프론트의 VITE_* 로 넣으면 번들에 그대로 노출됩니다.
2. 카카오 REST 엔드포인트는 브라우저에서 부르면 CORS 사전 요청이 막힙니다.
따라서 키를 가진 이 서버가 대신 부르고, 프론트는 /api/compare 만 호출합니다.

응답 형식에 대해
----------------
공식 문서를 확인하지 못한 채 작성했습니다. 그래서 필드를 하나의 이름으로 단정하지 않고
`pick()` 으로 여러 후보 이름을 훑습니다. 실제 응답을 한 번 받아 보고
아래 *_KEYS 목록에 진짜 이름을 넣으면 그때부터 정확히 동작합니다.
해석에 실패하면 응답의 최상위 키 목록을 담은 UPSTREAM_ERROR 를 던지므로,
서버 로그나 화면 메시지를 보고 어떤 이름인지 바로 알 수 있습니다.
"""

from typing import Any

import httpx

from src.config.settings import Settings
from src.services.compare import (
    ApiError,
    CompareResponse,
    Point,
    Transit,
    Walk,
    gather_and_compare,
    no_route,
    upstream_error,
)

KAKAO_HOST = 'https://dapi.kakao.com'

# 응답에서 찾을 필드 이름 후보입니다. 실제 이름을 확인하면 맨 앞에 추가하세요.
DURATION_KEYS = ('duration', 'totalTime', 'total_time', 'time', 'sectionTime')
DISTANCE_KEYS = ('distance', 'totalDistance', 'total_distance', 'length')
FARE_KEYS = ('fare', 'payment', 'totalFare', 'total_fare', 'price', 'charge')
TRANSFER_KEYS = ('transfers', 'transferCount', 'transfer_count', 'transitCount')
ROUTES_KEYS = ('routes', 'paths', 'path', 'result', 'documents')
SECTIONS_KEYS = ('sections', 'subPath', 'sub_path', 'steps', 'legs')
POINTS_KEYS = ('points', 'vertexes', 'vertices', 'graphPos', 'coordinates', 'polyline')

# 초 단위로 오는 값을 분으로 바꿀 기준. 이 값보다 크면 초로 봅니다.
SECONDS_THRESHOLD = 600


def pick(source: Any, keys: tuple[str, ...]) -> Any:
    """딕셔너리에서 후보 이름 중 먼저 발견되는 값을 돌려줍니다."""
    if not isinstance(source, dict):
        return None
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return None


def as_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float('inf') else None


def to_minutes(value: Any) -> float | None:
    """소요시간을 분으로 맞춥니다. 초로 오는 API 가 있어 크기로 판단합니다."""
    number = as_number(value)
    if number is None or number < 0:
        return None
    return round(number / 60) if number > SECONDS_THRESHOLD else number


def parse_points(value: Any) -> list[Point]:
    """좌표 목록을 뽑습니다. {x,y} 객체 배열과 [x, y, x, y...] 평면 배열을 모두 받습니다."""
    if not isinstance(value, list):
        return []
    points: list[Point] = []
    if value and all(isinstance(item, (int, float)) for item in value):
        for index in range(0, len(value) - 1, 2):
            x, y = as_number(value[index]), as_number(value[index + 1])
            if x is not None and y is not None and abs(x) <= 180 and abs(y) <= 90:
                points.append(Point(x=x, y=y))
        return points
    for item in value:
        if isinstance(item, list):
            points.extend(parse_points(item))
            continue
        x, y = as_number(pick(item, ('x', 'lng', 'longitude'))), as_number(pick(item, ('y', 'lat', 'latitude')))
        if x is not None and y is not None and abs(x) <= 180 and abs(y) <= 90:
            points.append(Point(x=x, y=y))
    return points


def parse_paths(route: Any) -> list[list[Point]]:
    """구간별 좌표 묶음. 끊긴 구간을 잇지 않도록 구간마다 따로 담습니다."""
    sections = pick(route, SECTIONS_KEYS)
    paths: list[list[Point]] = []
    if isinstance(sections, list):
        for section in sections:
            points = parse_points(pick(section, POINTS_KEYS))
            if len(points) >= 2:
                paths.append(points)
    if paths:
        return paths
    points = parse_points(pick(route, POINTS_KEYS))
    return [points] if len(points) >= 2 else []


def first_route(data: Any) -> Any:
    """응답에서 첫 경로 객체를 찾습니다."""
    routes = pick(data, ROUTES_KEYS)
    if isinstance(routes, dict):
        routes = pick(routes, ROUTES_KEYS) or routes
    if isinstance(routes, list):
        return routes[0] if routes else None
    return routes if isinstance(routes, dict) else None


def shape_error(what: str, data: Any) -> ApiError:
    """어떤 이름으로 왔는지 알 수 있도록 최상위 키를 메시지에 담습니다."""
    keys = ', '.join(sorted(data)[:12]) if isinstance(data, dict) else type(data).__name__
    return ApiError(502, 'UPSTREAM_ERROR',
                    f'카카오 {what} 응답을 해석하지 못했습니다 (받은 항목: {keys})')


class KakaoRouting:
    """도보·대중교통 경로를 카카오맵 REST API 에서 가져옵니다."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client, self.settings = client, settings

    async def request(self, path: str, params: dict) -> dict:
        key = self.settings.kakao_rest_api_key.get_secret_value()
        if not key:
            raise ApiError(503, 'SERVICE_NOT_CONFIGURED',
                           '서버의 카카오 REST API 키가 설정되지 않았습니다')
        try:
            response = await self.client.get(
                f'{KAKAO_HOST}{path}',
                params=params,
                headers={'Authorization': f'KakaoAK {key}'},
                timeout=self.settings.upstream_timeout_seconds,
            )
            if response.status_code == 401 or response.status_code == 403:
                raise ApiError(503, 'SERVICE_NOT_CONFIGURED',
                               '카카오 REST API 키 인증에 실패했습니다. 키와 카카오맵 사용 설정을 확인하세요')
            if response.status_code == 429:
                raise ApiError(429, 'RATE_LIMITED', '호출 한도를 초과했습니다. 잠시 후 다시 시도하세요')
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise upstream_error()
            # 카카오는 오류를 본문에 담아 200 으로 주기도 합니다.
            if 'errorType' in data or ('code' in data and pick(data, ROUTES_KEYS) is None):
                raise no_route()
            return data
        except (httpx.HTTPError, ValueError) as exc:
            # 업스트림 URL·메시지에는 키가 섞일 수 있으므로 그대로 노출하지 않습니다.
            raise upstream_error() from exc

    async def transit(self, sx, sy, ex, ey) -> Transit:
        data = await self.request(self.settings.kakao_transit_path,
                                  {'sx': sx, 'sy': sy, 'ex': ex, 'ey': ey})
        route = first_route(data)
        if route is None:
            raise no_route()
        duration = to_minutes(pick(route, DURATION_KEYS))
        fare = as_number(pick(route, FARE_KEYS))
        if duration is None or fare is None:
            raise shape_error('대중교통 경로', data)
        transfers = as_number(pick(route, TRANSFER_KEYS)) or 0
        walk_distance = as_number(pick(route, ('totalWalk', 'walkDistance', 'walk_distance'))) or 0
        walk_duration = to_minutes(pick(route, ('totalWalkTime', 'walkTime', 'walk_time'))) or 0
        return Transit(
            duration=duration, fare=int(fare), transfers=int(max(0, transfers)),
            walkDistance=max(0.0, walk_distance), walkDuration=max(0.0, walk_duration),
            paths=parse_paths(route),
        )

    async def walk(self, sx, sy, ex, ey) -> Walk:
        data = await self.request(self.settings.kakao_walk_path,
                                  {'sx': sx, 'sy': sy, 'ex': ex, 'ey': ey})
        route = first_route(data)
        if route is None:
            raise no_route()
        distance = as_number(pick(route, DISTANCE_KEYS))
        duration = to_minutes(pick(route, DURATION_KEYS))
        if distance is None or duration is None:
            raise shape_error('도보 경로', data)
        return Walk(distance=max(0.0, distance), duration=max(0.0, duration),
                    paths=parse_paths(route))

    async def compare(self, sx, sy, ex, ey) -> CompareResponse:
        return await gather_and_compare(self, sx, sy, ex, ey)
