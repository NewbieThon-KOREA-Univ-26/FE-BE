import asyncio
import math
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.config.settings import Settings

NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class Point(BaseModel):
    x: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]


class Geometry(BaseModel):
    # Keep disconnected sections separate; never draw invented connecting lines.
    paths: list[list[Point]] = Field(default_factory=list)
    geometryWarning: str | None = None


class Walk(Geometry):
    distance: NonNegative
    duration: NonNegative
    # 기존 클라이언트를 위한 단일 경로 좌표입니다. 새 지도는 paths를 사용합니다.
    path: list[Point] | None = None


class TransitRouteStep(BaseModel):
    mode: Literal['bus', 'subway']
    lineName: str | None = None
    fromName: str | None = None
    toName: str | None = None
    # '인천공항2터미널 방면' 처럼 타는 방향. 제공자가 주지 않으면 비웁니다.
    direction: str | None = None


class Transit(Geometry):
    duration: NonNegative
    fare: Annotated[int, Field(ge=0)]
    transfers: Annotated[int, Field(ge=0)]
    walkDistance: NonNegative
    walkDuration: NonNegative
    # 대중교통 경로 좌표. 정류장·역 좌표를 이어 만든 근사 폴리라인입니다.
    path: list[Point] | None = None
    # 대중교통 탑승 구간별 간단한 승차·하차 안내입니다.
    routeSteps: list[TransitRouteStep] | None = None
    # 걷는 구간이 별도 step 으로 오지 않아 정류장 좌표 사이 거리로 어림한 경우 true. 화면은 '약' 을 붙입니다.
    walkEstimated: bool | None = None


class Savings(BaseModel):
    amount: int
    extraMinutes: float


class Recommendation(BaseModel):
    choice: Literal['walk', 'transit']
    reason: str
    # F6 — 날씨가 추천에 영향을 준 이유. 영향이 없으면 비웁니다.
    weatherReason: str | None = None


class WeatherInfo(BaseModel):
    condition: str
    temperatureC: float | None = None
    precipitationProbability: float | None = None
    iconUrl: str | None = None


class CompareResponse(BaseModel):
    walk: Walk
    transit: Transit
    savings: Savings
    recommendation: Recommendation
    # F6 — 출발지 기준 현재 날씨. 키가 없거나 조회에 실패하면 생략됩니다.
    weather: WeatherInfo | None = None


def distance_km(sx: float, sy: float, ex: float, ey: float) -> float:
    """두 좌표(경도, 위도) 사이의 직선 거리(km). 하버사인 공식."""
    from math import asin, cos, radians, sin, sqrt
    lon1, lat1, lon2, lat2 = map(radians, (sx, sy, ex, ey))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def no_route():
    return ApiError(404, 'NO_ROUTE', '비교할 도보 또는 대중교통 경로를 찾을 수 없습니다')


def upstream_error():
    return ApiError(502, 'UPSTREAM_ERROR', '경로 제공 서비스 응답을 확인할 수 없습니다')


# --- 경로 좌표 추출 -------------------------------------------------------
# 경로 선은 있으면 좋은 부가 정보입니다. 좌표를 못 꺼내도 비교 결과는 정상 응답해야 하므로
# 아래 함수들은 예외를 던지지 않고 None 또는 빈 목록을 돌려줍니다.

MIN_PATH_POINTS = 2


def _point(source, x_key: str, y_key: str) -> Point | None:
    """딕셔너리에서 좌표 한 쌍을 꺼냅니다. 형식이 다르면 None."""
    if not isinstance(source, dict):
        return None
    try:
        x, y = float(source[x_key]), float(source[y_key])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)
            and -180 <= x <= 180 and -90 <= y <= 90):
        return None
    return Point(x=x, y=y)


def _dedupe(points: list[Point]) -> list[Point] | None:
    """연속으로 같은 좌표를 지우고, 선을 그릴 만큼 남았을 때만 돌려줍니다."""
    result: list[Point] = []
    for point in points:
        if not result or (result[-1].x, result[-1].y) != (point.x, point.y):
            result.append(point)
    return result if len(result) >= MIN_PATH_POINTS else None


def transit_path(sections) -> list[Point] | None:
    """대중교통 경로 좌표를 subPath 구간에서 만듭니다.

    구간마다 passStopList 의 정류장·역 좌표가 있으면 그걸 쓰고, 없으면 구간의
    시작·끝 좌표만 씁니다. 둘 다 없으면 그 구간은 건너뜁니다.
    """
    if not isinstance(sections, list):
        return None
    points: list[Point] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        stations = (section.get('passStopList') or {})
        stations = stations.get('stations') if isinstance(stations, dict) else None
        stop_points = [p for p in (_point(s, 'x', 'y') for s in stations or []) if p]
        if stop_points:
            points.extend(stop_points)
            continue
        for pair in (('startX', 'startY'), ('endX', 'endY')):
            point = _point(section, *pair)
            if point:
                points.append(point)
    return _dedupe(points)


def transit_route_steps(sections) -> list[TransitRouteStep] | None:
    """ODsay 구간에서 버스·지하철 승차/하차 안내를 추출합니다."""
    if not isinstance(sections, list):
        return None
    result: list[TransitRouteStep] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        traffic_type = section.get('trafficType')
        if traffic_type not in (1, 2):
            continue
        stop_list = section.get('passStopList') or {}
        stations = stop_list.get('stations') if isinstance(stop_list, dict) else None
        station_names = [
            str(station.get('stationName') or station.get('name') or '').strip()
            for station in stations or []
            if isinstance(station, dict)
        ]
        station_names = [name for name in station_names if name]
        lane = section.get('lane')
        if isinstance(lane, list):
            lane = lane[0] if lane else None
        line_name = ''
        if isinstance(lane, dict):
            line_name = str(lane.get('name') or lane.get('busNo') or '').strip()
        if not line_name:
            line_name = str(section.get('laneName') or '').strip()
        from_name = str(section.get('startName') or (station_names[0] if station_names else '')).strip()
        to_name = str(section.get('endName') or (station_names[-1] if station_names else '')).strip()
        if not line_name and not from_name and not to_name:
            continue
        result.append(TransitRouteStep(
            mode='subway' if traffic_type == 1 else 'bus',
            lineName=line_name or None,
            fromName=from_name or None,
            toName=to_name or None,
        ))
    return result or None


def walk_path(path) -> list[Point] | None:
    """기존 단일 경로 응답용 좌표. 구간별 실제 routes 좌표는 walk()에서 추출합니다."""
    if not isinstance(path, dict):
        return None
    recommend = path.get('recommend')
    if not isinstance(recommend, dict):
        return None
    for key in ('sections', 'steps', 'path', 'points'):
        sections = recommend.get(key)
        if not isinstance(sections, list):
            continue
        points: list[Point] = []
        for section in sections:
            if isinstance(section, dict):
                for inner in ('points', 'graphPos', 'coordinates'):
                    nested = section.get(inner)
                    if isinstance(nested, list):
                        points.extend(p for p in (_point(n, 'x', 'y') for n in nested) if p)
                point = _point(section, 'x', 'y')
                if point:
                    points.append(point)
        found = _dedupe(points)
        if found:
            return found
    return None


class Odsay:
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client, self.settings = client, settings

    async def request(self, endpoint: str, params: dict):
        service = {'searchWalkPathV2': '도보 경로', 'searchPubTransPathT': '대중교통 경로',
                   'loadLane': '대중교통 지도 좌표'}.get(endpoint, '경로')
        key = self.settings.odsay_api_key.get_secret_value()
        if not key:
            raise ApiError(503, 'SERVICE_NOT_CONFIGURED', '서버의 ODsay API 키가 설정되지 않았습니다')
        try:
            response = await self.client.get(
                f'https://api.odsay.com/v1/api/{endpoint}',
                params={**params, 'apiKey': key, 'output': 'json'},
                timeout=self.settings.upstream_timeout_seconds,
            )
            if response.status_code == 429:
                raise ApiError(429, 'RATE_LIMITED', '호출 한도를 초과했습니다. 잠시 후 다시 시도하세요')
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise upstream_error()
            if 'error' in data:
                error = data['error']
                if isinstance(error, list):
                    error = error[0] if error else {}
                code = str(error.get('code')) if isinstance(error, dict) else ''
                # Inspect known provider markers but never expose its raw message or key.
                message = str(error.get('message', '')) if isinstance(error, dict) else ''
                if 'ApiKeyAuthFailed' in message:
                    raise ApiError(502, 'UPSTREAM_ERROR',
                                   f'ODsay {service} 인증에 실패했습니다. 서버 키와 등록된 외부 통신 IP를 확인해 주세요.')
                if code in {'3', '4', '5', '6', '-98', '-99'}:
                    raise no_route()
                raise ApiError(502, 'UPSTREAM_ERROR',
                               f'ODsay {service} 요청이 거절되었습니다. 해당 API의 사용 권한과 호출 한도를 확인해 주세요.')
            return data
        except httpx.TimeoutException as exc:
            raise ApiError(502, 'UPSTREAM_ERROR', f'ODsay {service} 응답 시간이 초과되었습니다. 다시 시도해 주세요.') from exc
        except (httpx.HTTPError, ValueError) as exc:
            # Never expose upstream URLs/messages: they may contain the API key.
            raise ApiError(502, 'UPSTREAM_ERROR', f'ODsay {service} 서비스에 연결하거나 응답을 읽지 못했습니다.') from exc

    async def transit(self, sx, sy, ex, ey) -> Transit:
        data = await self.request('searchPubTransPathT', {
            'SX': sx, 'SY': sy, 'EX': ex, 'EY': ey, 'SearchType': 0,
        })
        try:
            result = data['result']
            # This MVP compares city transit only, not intercity terminal-to-terminal fares.
            if result.get('searchType') != 0:
                raise no_route()
            paths = result['path']
            if not paths:
                raise no_route()
            candidates = []
            for path in paths:
                info, sections = path['info'], path['subPath']
                walking = [s for s in sections if s['trafficType'] == 3]
                boardings = sum(s['trafficType'] in (1, 2) for s in sections)
                if not boardings:
                    raise upstream_error()
                candidates.append((Transit(
                    duration=info['totalTime'], fare=info['payment'],
                    transfers=boardings - 1, walkDistance=info['totalWalk'],
                    walkDuration=sum(s['sectionTime'] for s in walking),
                    path=transit_path(sections),
                    routeSteps=transit_route_steps(sections),
                ), info.get('mapObj')))
            selected, map_object = min(candidates, key=lambda p: (
                p[0].duration, p[0].fare, p[0].transfers))
            try:
                if not map_object:
                    raise ValueError('Missing geometry reference')
                map_object = str(map_object)
                first_segment = map_object.split('@', 1)[0]
                has_coordinate_base = (
                    '@' in map_object and len(first_segment.split(':')) == 2
                )
                # Zero base requests absolute WGS84 coordinates.
                if has_coordinate_base:
                    map_object = f'0:0@{map_object.split("@", 1)[1]}'
                else:
                    map_object = f'0:0@{map_object}'
                geometry = await self.request('loadLane', {'mapObject': map_object})
                selected.paths = [
                    [Point.model_validate(point) for point in section['graphPos']]
                    for lane in geometry['result']['lane'] for section in lane['section']
                    if len(section['graphPos']) >= 2
                ]
                if not selected.paths:
                    raise ValueError('Empty geometry')
            except (ApiError, KeyError, TypeError, ValueError):
                selected.paths = []
                selected.geometryWarning = '대중교통 경로 선을 불러오지 못했습니다. 시간·요금은 확인할 수 있습니다.'
            return selected
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise upstream_error() from exc

    async def walk(self, sx, sy, ex, ey) -> Walk:
        data = await self.request('searchWalkPathV2', {
            'loc': f'{sx},{sy},{ex},{ey}', 'opt': 'reco',
        })
        try:
            paths = data['result']['path']
            if not paths:
                raise no_route()
            path = paths[0]
            if path['hasPathResult'] is not True:
                if str(path.get('errorCode')) in {'400', '409', '411', '412', '413', '414'}:
                    raise no_route()
                raise upstream_error()
            summary = path['recommend']['summary']
            seconds = float(summary['duration'])
            if not math.isfinite(seconds) or seconds < 0:
                raise upstream_error()
            walk = Walk(distance=summary['distance'], duration=math.ceil(seconds / 60),
                        path=walk_path(path))
            try:
                points = [Point.model_validate(route['coordinate'])
                          for route in path['recommend']['routes']]
                walk.paths = [points] if len(points) >= 2 else []
                if not walk.paths:
                    raise ValueError('Empty geometry')
            except (KeyError, TypeError, ValueError):
                walk.paths = []
                walk.geometryWarning = '도보 경로 선을 불러오지 못했습니다. 거리·시간은 확인할 수 있습니다.'
            return walk
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise upstream_error() from exc

    async def compare(self, sx, sy, ex, ey) -> CompareResponse:
        return await gather_and_compare(self, sx, sy, ex, ey)


# --- 제공자 공통 -----------------------------------------------------------

def raise_combined(results: dict[str, object]) -> None:
    """실패가 있으면 두 조회의 결과를 한 메시지에 담아 던집니다.

    도보만 실패했는데 대중교통이 됐는지, 둘 다 실패했는지가 한 번에 보여야
    한 라운드에 원인을 좁힐 수 있습니다. 상태·코드는 먼저 실패한 쪽을 따릅니다.
    ApiError 가 아닌 예외는 그대로 올립니다 (500 으로 처리됩니다).
    """
    failures = [(name, r) for name, r in results.items() if isinstance(r, Exception)]
    if not failures:
        return
    name, first = failures[0]
    if not isinstance(first, ApiError):
        raise first
    if len(failures) == len(results):
        others = [f.message for _, f in failures[1:]
                  if isinstance(f, ApiError) and f.message != first.message]
        if others:
            raise ApiError(first.status, first.code, ' / '.join([first.message, *others]))
        raise first
    succeeded = '·'.join(n for n in results if n != name)
    raise ApiError(first.status, first.code, f'{first.message} ({succeeded} 조회는 성공)')


async def gather_and_compare(provider, sx, sy, ex, ey) -> CompareResponse:
    """도보와 대중교통을 함께 조회해 비교 결과를 만듭니다.

    provider 는 walk(), transit() 와 settings 를 가진 객체면 무엇이든 됩니다.
    (Odsay, KakaoRouting 이 여기에 해당합니다.)
    """
    # 하나가 실패해도 두 요청을 모두 기다립니다. 클라이언트보다 오래 사는 태스크를 남기지 않기 위해서입니다.
    results = await asyncio.gather(
        provider.walk(sx, sy, ex, ey), provider.transit(sx, sy, ex, ey),
        return_exceptions=True,
    )
    raise_combined(dict(zip(('도보', '대중교통'), results)))
    walk, transit = results
    return build_comparison(walk, transit, provider.settings)


def format_minutes(minutes: float) -> str:
    """16.4 → '16분', 312.2 → '5시간 12분'. 사람에게 보여 줄 문장용이라 분 단위로 반올림합니다."""
    total = max(0, round(minutes))
    hours, rest = divmod(total, 60)
    if hours == 0:
        return f'{rest}분'
    return f'{hours}시간' if rest == 0 else f'{hours}시간 {rest}분'


def format_distance(meters: float) -> str:
    """320 → '320m', 19274 → '19.3km'"""
    return f'{round(meters)}m' if meters < 1000 else f'{meters / 1000:.1f}km'


BAD_WEATHER_WORDS = ('비', '눈', '소나기', '뇌우', '폭우', '진눈깨비', '우박', '태풍')


def weather_penalty(weather: WeatherInfo | None) -> str | None:
    """걷기를 덜 권할 날씨면 그 이유를, 아니면 None. 기능 명세서 F6 '비·더위면 걷기를 덜 권한다'."""
    if weather is None:
        return None
    text = weather.condition or ''
    if any(word in text for word in BAD_WEATHER_WORDS):
        return f'지금 {text}'
    if weather.precipitationProbability is not None and weather.precipitationProbability >= 60:
        return f'강수확률 {weather.precipitationProbability:g}%'
    if weather.temperatureC is not None and weather.temperatureC >= 30:
        return f'{weather.temperatureC:g}°C 더위'
    if weather.temperatureC is not None and weather.temperatureC <= -5:
        return f'{weather.temperatureC:g}°C 추위'
    return None


def build_comparison(walk: Walk, transit: Transit, settings: Settings,
                     weather: WeatherInfo | None = None) -> CompareResponse:
    """절감액과 추천을 계산합니다.

    "도보로 너무 먼 거리" 와 "너무 가까워서 대중교통이 무의미" 는 에러가 아닙니다.
    항상 200 으로 응답하고 recommendation.choice 로 구분합니다.
    """
    # 소요시간은 제공자에 따라 소수(초/60)로 올 수 있습니다. 차이는 분 단위로 반올림해 돌려줍니다.
    extra = round(walk.duration - transit.duration)
    max_minutes, max_meters = settings.walk_max_minutes, settings.walk_max_meters
    walkable = walk.duration <= max_minutes and walk.distance <= max_meters
    # 날씨가 나쁘면 걷기 기준을 절반으로 낮춥니다. 짧은 거리는 여전히 걷기를 권합니다.
    penalty = weather_penalty(weather)
    weather_reason = None
    if penalty:
        max_minutes, max_meters = max_minutes / 2, max_meters / 2
        walkable_now = walk.duration <= max_minutes and walk.distance <= max_meters
        if walkable and not walkable_now:
            weather_reason = f'{penalty}라 오늘은 타는 걸 권해요'
        elif walkable_now:
            weather_reason = f'{penalty}지만 짧은 거리라 걸을 만해요'
        else:
            weather_reason = f'{penalty}'
        walkable = walkable_now
    choice = 'walk' if walkable else 'transit'
    walk_text = f'도보 {format_minutes(walk.duration)}·{format_distance(walk.distance)}'
    if choice == 'transit':
        reason = (f'{walk_text}로 오늘 날씨에는 걷기를 권하지 않아요' if weather_reason and '타는 걸' in weather_reason
                  else f'{walk_text}로 걷기 추천 기준을 초과합니다')
    else:
        time = f'{format_minutes(extra)} 더 걸리지만' if extra > 0 else (
            f'{format_minutes(-extra)} 더 빠르고' if extra < 0 else '같은 시간이 걸리고')
        reason = f'걸으면 {time} {transit.fare:,}원을 아낍니다'
    return CompareResponse(
        walk=walk, transit=transit,
        savings=Savings(amount=transit.fare, extraMinutes=extra),
        recommendation=Recommendation(choice=choice, reason=reason, weatherReason=weather_reason),
        weather=weather,
    )
