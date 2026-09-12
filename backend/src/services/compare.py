import asyncio
import math
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.config.settings import Settings

NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Finite = Annotated[float, Field(allow_inf_nan=False)]


class Point(BaseModel):
    """지도에 경로 선을 그릴 좌표. X = 경도(lng), Y = 위도(lat)."""

    x: Finite
    y: Finite


class Walk(BaseModel):
    distance: NonNegative
    duration: NonNegative
    # 도보 경로 좌표. 지금 쓰는 ODsay 응답에서 꺼낼 수 없으면 생략됩니다.
    # 프론트는 path 가 없으면 출발지-도착지 직선을 점선으로 그립니다.
    path: list[Point] | None = None


class Transit(BaseModel):
    duration: NonNegative
    fare: Annotated[int, Field(ge=0)]
    transfers: Annotated[int, Field(ge=0)]
    walkDistance: NonNegative
    walkDuration: NonNegative
    # 대중교통 경로 좌표. 정류장·역 좌표를 이어 만든 근사 폴리라인입니다.
    path: list[Point] | None = None


class Savings(BaseModel):
    amount: int
    extraMinutes: float


class Recommendation(BaseModel):
    choice: Literal['walk', 'transit']
    reason: str


class CompareResponse(BaseModel):
    walk: Walk
    transit: Transit
    savings: Savings
    recommendation: Recommendation


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
    if not (math.isfinite(x) and math.isfinite(y)):
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


def walk_path(path) -> list[Point] | None:
    """도보 경로 좌표.

    TODO: 현재 쓰는 searchWalkPathV2 응답에서 좌표를 담은 필드를 확인하지 못했습니다.
    실제 키를 확인하면 아래 후보 목록에 이름을 추가하세요. 못 찾으면 None 이 되고
    프론트가 출발지-도착지 직선을 점선으로 그립니다.
    """
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
                if code in {'3', '4', '5', '6', '-98', '-99'}:
                    raise no_route()
                raise upstream_error()
            return data
        except (httpx.HTTPError, ValueError) as exc:
            # Never expose upstream URLs/messages: they may contain the API key.
            raise upstream_error() from exc

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
                candidates.append(Transit(
                    duration=info['totalTime'], fare=info['payment'],
                    transfers=boardings - 1, walkDistance=info['totalWalk'],
                    walkDuration=sum(s['sectionTime'] for s in walking),
                    path=transit_path(sections),
                ))
            return min(candidates, key=lambda p: (p.duration, p.fare, p.transfers))
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
            return Walk(distance=summary['distance'], duration=math.ceil(seconds / 60),
                        path=walk_path(path))
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise upstream_error() from exc

    async def compare(self, sx, sy, ex, ey) -> CompareResponse:
        # Await both requests even when one fails so no task outlives the request/client.
        results = await asyncio.gather(
            self.walk(sx, sy, ex, ey), self.transit(sx, sy, ex, ey),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                raise result
        walk, transit = results
        extra = walk.duration - transit.duration
        choice = 'walk' if (walk.duration <= self.settings.walk_max_minutes
                            and walk.distance <= self.settings.walk_max_meters) else 'transit'
        if choice == 'transit':
            reason = f'도보 {walk.duration:g}분·{walk.distance:g}m로 걷기 추천 기준을 초과합니다'
        else:
            time = f'{extra:g}분 더 걸리지만' if extra > 0 else (
                f'{-extra:g}분 더 빠르고' if extra < 0 else '같은 시간이 걸리고')
            reason = f'걸으면 {time} {transit.fare:,}원을 아낍니다'
        return CompareResponse(
            walk=walk, transit=transit,
            savings=Savings(amount=transit.fare, extraMinutes=extra),
            recommendation=Recommendation(choice=choice, reason=reason),
        )
