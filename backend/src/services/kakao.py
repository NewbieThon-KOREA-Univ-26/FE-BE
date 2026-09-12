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
카카오맵 REST 공식 응답의 route/properties 및 steps/path 구조를 읽습니다.
properties.totalTime은 초 단위이며 분으로 변환합니다.
기존 응답 형식은 후보 필드 이름을 통해 호환합니다.
해석에 실패하면 응답의 최상위 키 목록을 담은 UPSTREAM_ERROR 를 던지므로,
서버 로그나 화면 메시지를 보고 어떤 이름인지 바로 알 수 있습니다.
"""

from typing import Any
from urllib.parse import parse_qsl

import httpx

from src.config.settings import Settings
from src.services.compare import (
    ApiError,
    CompareResponse,
    Point,
    Transit,
    TransitRouteStep,
    Walk,
    gather_and_compare,
    no_route,
)

KAKAO_HOST = 'https://dapi.kakao.com'

# 응답에서 찾을 필드 이름 후보입니다. 실제 이름을 확인하면 맨 앞에 추가하세요.
DURATION_KEYS = ('duration', 'totalTime', 'total_time', 'time', 'sectionTime')
DISTANCE_KEYS = ('distance', 'totalDistance', 'total_distance', 'length')
FARE_KEYS = ('fare', 'payment', 'totalFare', 'total_fare', 'price', 'charge')
TRANSFER_KEYS = ('transfers', 'transferCount', 'transfer_count', 'transitCount')
ROUTES_KEYS = ('route', 'routes', 'paths', 'path', 'result', 'documents')
SECTIONS_KEYS = ('sections', 'subPath', 'sub_path', 'steps', 'legs')
POINTS_KEYS = ('points', 'vertexes', 'vertices', 'graphPos', 'coordinates', 'polyline')

# 초 단위로 오는 값을 분으로 바꿀 기준. 이 값보다 크면 초로 봅니다.
SECONDS_THRESHOLD = 600

# 상태 코드만 보고 바로 손댈 수 있는 원인. 메시지 끝에 붙습니다.
STATUS_HINTS = {
    404: ' — 엔드포인트 경로가 다를 수 있습니다. KAKAO_WALK_PATH / KAKAO_TRANSIT_PATH 환경변수로 바꿀 수 있습니다',
    400: ' — 요청 파라미터 이름이 다를 수 있습니다. KAKAO_WALK_QUERY / KAKAO_TRANSIT_QUERY 환경변수로 바꿀 수 있습니다',
}


def build_query(template: str, sx, sy, ex, ey) -> dict[str, str]:
    """'origin={sx},{sy}&destination={ex},{ey}' 같은 틀을 쿼리 딕셔너리로 바꿉니다.

    파라미터 이름을 문서에 맞추는 일을 코드 수정 없이 환경변수만으로 끝내기 위해서입니다.
    """
    try:
        filled = template.format(sx=sx, sy=sy, ex=ex, ey=ey)
    except (KeyError, IndexError, ValueError):
        raise ApiError(503, 'SERVICE_NOT_CONFIGURED',
                       'KAKAO_*_QUERY 틀에는 {sx} {sy} {ex} {ey} 자리만 쓸 수 있습니다') from None
    return dict(parse_qsl(filled, keep_blank_values=True))


def upstream_detail(response: httpx.Response, key: str) -> str:
    """4xx 본문에서 카카오가 준 코드와 설명만 골라 담습니다.

    "어떤 파라미터가 필요하다" 같은 설명이 원인을 바로 알려 주기 때문입니다.
    키가 섞여 있으면 지우고, 길이를 제한하고, 문자열이 아닌 값은 버립니다.
    """
    try:
        body = response.json()
    except ValueError:
        return ''
    if not isinstance(body, dict):
        return ''
    parts = []
    code = body.get('code', body.get('errorType'))
    if code is not None:
        parts.append(f'코드 {str(code)[:40]}')
    msg = body.get('msg') or body.get('message') or body.get('errorMessage')
    if isinstance(msg, str) and msg.strip():
        text = msg.strip().replace(key, '***') if key else msg.strip()
        parts.append(text[:160])
    return f', 카카오 설명: {" · ".join(parts)}' if parts else ''


def json_ready(params: dict[str, str]) -> dict[str, Any]:
    """JSON 본문으로 보낼 때 숫자처럼 생긴 값은 숫자로 바꿉니다. '127.0,37.5' 같은 값은 그대로 둡니다."""
    out: dict[str, Any] = {}
    for name, value in params.items():
        try:
            out[name] = float(value) if '.' in value else int(value)
        except ValueError:
            out[name] = value
    return out


def outline(value: Any, depth: int = 4) -> str:
    """응답 구조를 한 줄로 요약합니다. 이름·형태·작은 값만 담고 긴 목록은 첫 항목만 보입니다.

    해석에 실패했을 때 어떤 이름으로 어디에 값이 있는지 한 번에 알기 위해서입니다.
    """
    # 이름 단계(딕셔너리)만 깊이를 소모합니다. 목록은 첫 항목을 같은 깊이로, 작은 값은 항상 보입니다.
    if isinstance(value, dict):
        if depth <= 0:
            return '{…}'
        items = list(value.items())
        body = ', '.join(f'{k}: {outline(v, depth - 1)}' for k, v in items[:12])
        more = f', …+{len(items) - 12}' if len(items) > 12 else ''
        return '{' + body + more + '}'
    if isinstance(value, list):
        if not value:
            return '[] (0개)'
        return f'[{outline(value[0], depth)} …{len(value)}개]'
    if isinstance(value, str):
        return repr(value[:24] + ('…' if len(value) > 24 else ''))
    return repr(value)


# 값이 딕셔너리로 싸여 올 때 (예: fare: {regular: {totalFare: 1500}}) 먼저 볼 이름들.
NESTED_NUMBER_KEYS = ('total', 'totalFare', 'total_fare', 'regular', 'adult', 'fare',
                      'value', 'amount', 'taxi', 'seconds', 'minutes')


def unwrap_number(value: Any, depth: int = 2) -> float | None:
    """숫자, 또는 숫자를 감싼 딕셔너리·목록에서 숫자 하나를 꺼냅니다.

    딕셔너리는 알려진 이름을 먼저 보고, 없으면 숫자 값이 딱 하나일 때만 그것을 씁니다.
    (여러 개면 무엇인지 알 수 없어 고르지 않습니다.)
    """
    if isinstance(value, bool):
        return None
    number = as_number(value)
    if number is not None or depth <= 0:
        return number
    if isinstance(value, dict):
        for key in NESTED_NUMBER_KEYS:
            if key in value:
                number = unwrap_number(value[key], depth - 1)
                if number is not None:
                    return number
        numbers = [as_number(v) for v in value.values()
                   if not isinstance(v, bool) and as_number(v) is not None]
        return numbers[0] if len(numbers) == 1 else None
    if isinstance(value, list) and value:
        return unwrap_number(value[0], depth - 1)
    return None


def find_number(route: Any, data: Any, keys: tuple[str, ...]) -> float | None:
    """경로 객체 → 그 안의 summary → 응답 최상위 properties 순서로 숫자를 찾습니다."""
    holders = (pick(route, ('properties',)), route, pick(route, ('summary', 'info', 'total')),
               pick(data, ('properties', 'summary')))
    for holder in holders:
        number = unwrap_number(pick(holder, keys))
        if number is not None:
            return number
    return None


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
    # 공식 응답: 도보는 legs[].steps[], 대중교통은 steps[].path.points.
    # 각 단계의 선을 따로 유지하여 떨어진 구간을 직선으로 잇지 않습니다.
    if isinstance(route, dict) and isinstance(route.get('properties'), dict):
        return official_paths(route)
    sections = pick(route, SECTIONS_KEYS)
    paths: list[list[Point]] = []
    if isinstance(sections, list):
        for section in sections:
            points = parse_points(pick(section, POINTS_KEYS))
            if not points:
                # 구간 아래 도로 단위(roads[].vertexes)로 쪼개져 오면 이어 붙입니다.
                for road in pick(section, ('roads', 'links', 'legs', 'steps')) or []:
                    points.extend(parse_points(pick(road, POINTS_KEYS)))
            if len(points) >= 2:
                paths.append(points)
    if paths:
        return paths
    points = parse_points(pick(route, POINTS_KEYS))
    return [points] if len(points) >= 2 else []


def official_paths(route: dict) -> list[list[Point]]:
    paths = []
    points = parse_points(pick(pick(route, ('path',)), ('points',)))
    if len(points) >= 2:
        paths.append(points)
    for key in ('legs', 'steps'):
        children = route.get(key)
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    paths.extend(official_paths(child))
    return paths


def route_minutes(route: Any, data: Any) -> float | None:
    properties = pick(route, ('properties',))
    if isinstance(properties, dict):
        seconds = as_number(properties.get('totalTime'))
        return seconds / 60 if seconds is not None and seconds >= 0 else None
    return to_minutes(find_number(route, data, DURATION_KEYS))


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
                    f'카카오 {what} 응답을 해석하지 못했습니다 (받은 항목: {keys}; 구조: {outline(data)[:900]})')


def no_route_in(what: str, data: Any) -> ApiError:
    """경로 목록이 비었거나 못 찾았을 때. 왜인지 보이도록 구조를 담습니다."""
    return ApiError(404, 'NO_ROUTE',
                    f'비교할 {what} 경로를 찾을 수 없습니다 (구조: {outline(data)[:900]})')


RAIL_WORDS = ('SUBWAY', 'TRAIN', 'RAIL', 'TRAM')


def parse_guidance(text: str) -> tuple[str | None, str | None, str | None]:
    """'6호선 (안암(고대병원앞) > 삼각지(전쟁기념관))' → ('6호선', '안암(고대병원앞)', '삼각지(전쟁기념관)')"""
    head, sep, rest = text.partition(' (')
    if not sep:
        return (head.strip() or None, None, None)
    if rest.endswith(')'):
        rest = rest[:-1]
    start, arrow, end = rest.partition(' > ')
    return (head.strip() or None, start.strip() or None, (end.strip() or None) if arrow else None)


def text_of(item: Any, keys: tuple[str, ...]) -> str | None:
    """항목(또는 그 properties)에서 첫 문자열 값을 꺼냅니다."""
    holder = item.get('properties') if isinstance(item, dict) and isinstance(item.get('properties'), dict) else item
    value = pick(holder, keys)
    return str(value).strip() or None if value not in (None, '') else None


def route_step(step: dict) -> TransitRouteStep | None:
    """탑승 step 하나를 승차·하차 안내로 바꿉니다. 걷는 구간이면 None.

    stops·vehicles 안의 항목 이름은 아직 확인되지 않아 흔한 이름을 시도하고,
    없으면 확인된 guidance 문자열('6호선 (안암 > 삼각지)')을 잘라 씁니다.
    """
    props = step.get('properties') if isinstance(step.get('properties'), dict) else step
    kind = str(props.get('type') or '').upper()
    if not kind or kind == 'WALK':
        return None
    mode = 'subway' if any(word in kind for word in RAIL_WORDS) else 'bus'
    guide_line, guide_start, guide_end = parse_guidance(str(props.get('guidance') or ''))
    vehicles = props.get('vehicles') or []
    vehicle = vehicles[0] if isinstance(vehicles, list) and vehicles else (vehicles if isinstance(vehicles, dict) else {})
    line = text_of(vehicle, ('name', 'lineName', 'line', 'no', 'number', 'busNo', 'routeName'))
    direction = text_of(vehicle, ('headsign', 'direction', 'destination', 'toward', 'bound', 'terminal', 'lastStop'))
    stops = props.get('stops') or []
    names = [text_of(stop, ('name', 'stopName', 'stationName', 'title')) for stop in stops] if isinstance(stops, list) else []
    names = [name for name in names if name]
    start, end = (names[0], names[-1]) if len(names) >= 2 else (None, None)
    return TransitRouteStep(mode=mode, lineName=line or guide_line,
                            fromName=start or guide_start, toName=end or guide_end,
                            direction=direction)


def route_steps(steps: Any) -> list[TransitRouteStep] | None:
    if not isinstance(steps, list):
        return None
    guides = [guide for guide in (route_step(step) for step in steps if isinstance(step, dict)) if guide]
    return guides or None


class KakaoRouting:
    """도보·대중교통 경로를 카카오맵 REST API 에서 가져옵니다."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client, self.settings = client, settings

    async def request(self, what: str, path: str, params: dict) -> dict:
        """카카오 REST 를 부르고 본문(dict)을 돌려줍니다.

        실패하면 원인을 한 줄로 알 수 있게 상태 코드와 어느 조회(도보·대중교통)인지 담습니다.
        업스트림 본문·URL 은 그대로 노출하지 않습니다. 상태 코드와 숫자 코드만 담습니다.
        """
        key = self.settings.kakao_rest_api_key.get_secret_value()
        if not key:
            raise ApiError(503, 'SERVICE_NOT_CONFIGURED',
                           '서버의 카카오 REST API 키가 설정되지 않았습니다')
        # 환경변수로 바꿀 때 전체 URL 을 넣거나 앞 슬래시를 빼도 되게 합니다.
        url = path if path.startswith(('http://', 'https://')) else f"{KAKAO_HOST}/{path.lstrip('/')}"
        style = self.settings.kakao_request_style
        headers = {'Authorization': f'KakaoAK {key}'}
        timeout = self.settings.upstream_timeout_seconds
        try:
            if style == 'post-json':
                response = await self.client.post(url, json=json_ready(params), headers=headers, timeout=timeout)
            elif style == 'post-form':
                response = await self.client.post(url, data=params, headers=headers, timeout=timeout)
            else:
                response = await self.client.get(url, params=params, headers=headers, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise ApiError(502, 'UPSTREAM_ERROR',
                           f'카카오 {what} 경로 조회 응답 시간이 초과되었습니다. 다시 시도해 주세요') from exc
        except httpx.HTTPError as exc:
            raise ApiError(502, 'UPSTREAM_ERROR',
                           f'카카오 {what} 경로 조회 서비스에 연결하지 못했습니다') from exc

        target = httpx.URL(url)
        method = 'GET' if style == 'get' else 'POST'
        where = f'{method} {target.host}{target.path}'  # 쿼리(좌표)와 키(헤더)는 담지 않습니다.
        status = response.status_code
        if status in (401, 403):
            raise ApiError(503, 'SERVICE_NOT_CONFIGURED',
                           '카카오 REST API 키 인증에 실패했습니다. 키와 카카오맵 사용 설정을 확인하세요')
        if status == 429:
            raise ApiError(429, 'RATE_LIMITED', '호출 한도를 초과했습니다. 잠시 후 다시 시도하세요')
        if status >= 400:
            sent = ', '.join(params) or '없음'  # 이름만 담습니다. 값(좌표)은 담지 않습니다.
            raise ApiError(502, 'UPSTREAM_ERROR',
                           f'카카오 {what} 경로 조회가 실패했습니다 (요청: {where}, 보낸 파라미터: {sent}, '
                           f'카카오 응답 상태: {status}{upstream_detail(response, key)}'
                           f'{STATUS_HINTS.get(status, "")})')
        try:
            data = response.json()
        except ValueError as exc:
            kind = response.headers.get('content-type', '').split(';')[0].strip() or '알 수 없음'
            hint = ('' if target.host == 'dapi.kakao.com' else
                    ' — 문서 페이지 주소가 아니라 dapi.kakao.com 으로 시작하는 API 요청 URL 이어야 합니다')
            raise ApiError(502, 'UPSTREAM_ERROR',
                           f'카카오 {what} 경로 조회 응답이 JSON 이 아닙니다 '
                           f'(요청: {where}, 상태: {status}, 형식: {kind}){hint}') from exc
        if not isinstance(data, dict):
            raise ApiError(502, 'UPSTREAM_ERROR',
                           f'카카오 {what} 경로 조회 응답 형식이 예상과 다릅니다 ({type(data).__name__})')
        # 카카오는 오류를 본문에 담아 200 으로 주기도 합니다. 숫자 코드만 메시지에 담습니다.
        if 'errorType' in data or ('code' in data and pick(data, ROUTES_KEYS) is None):
            code = data.get('code', data.get('errorType'))
            shown = code if isinstance(code, (int, float)) else str(code)[:40]
            raise ApiError(404, 'NO_ROUTE',
                           f'비교할 {what} 경로를 찾을 수 없습니다 (카카오 응답 코드: {shown})')
        return data

    async def raw(self, kind: str, sx, sy, ex, ey) -> dict:
        """해석하지 않은 카카오 응답. 필드 이름을 확인하는 진단 용도로도 씁니다."""
        if kind == 'transit':
            return await self.request('대중교통', self.settings.kakao_transit_path,
                                      build_query(self.settings.kakao_transit_query, sx, sy, ex, ey))
        return await self.request('도보', self.settings.kakao_walk_path,
                                  build_query(self.settings.kakao_walk_query, sx, sy, ex, ey))

    async def transit(self, sx, sy, ex, ey) -> Transit:
        data = await self.raw('transit', sx, sy, ex, ey)
        route = first_route(data)
        if route is None:
            raise no_route_in('대중교통', data)
        duration = route_minutes(route, data)
        fare = find_number(route, data, FARE_KEYS)
        if duration is None or fare is None:
            raise shape_error('대중교통 경로', data)
        transfers = find_number(route, data, TRANSFER_KEYS) or 0
        walk_distance = find_number(route, data, ('totalWalk', 'walkDistance', 'walk_distance')) or 0
        walk_duration = to_minutes(find_number(route, data, ('totalWalkTime', 'walkTime', 'walk_time'))) or 0
        if isinstance(route.get('properties'), dict):
            steps = route.get('steps')
            walking = [step['properties'] for step in steps
                       if isinstance(step, dict) and isinstance(step.get('properties'), dict)
                       and step['properties'].get('type') == 'WALK'] if isinstance(steps, list) else []
            walk_distance = sum(max(0, as_number(step.get('distance')) or 0) for step in walking)
            walk_duration = sum(max(0, as_number(step.get('time')) or 0) for step in walking) / 60
        return Transit(
            duration=duration, fare=int(fare), transfers=int(max(0, transfers)),
            walkDistance=max(0.0, walk_distance), walkDuration=max(0.0, walk_duration),
            paths=parse_paths(route),
            routeSteps=route_steps(route.get('steps')) if isinstance(route, dict) else None,
        )

    async def walk(self, sx, sy, ex, ey) -> Walk:
        data = await self.raw('walk', sx, sy, ex, ey)
        route = first_route(data)
        if route is None:
            raise no_route_in('도보', data)
        distance = find_number(route, data, DISTANCE_KEYS)
        duration = route_minutes(route, data)
        if distance is None or duration is None:
            raise shape_error('도보 경로', data)
        return Walk(distance=max(0.0, distance), duration=max(0.0, duration),
                    paths=parse_paths(route))

    async def compare(self, sx, sy, ex, ey) -> CompareResponse:
        return await gather_and_compare(self, sx, sy, ex, ey)
