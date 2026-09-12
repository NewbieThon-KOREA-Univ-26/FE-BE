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


class Transit(Geometry):
    duration: NonNegative
    fare: Annotated[int, Field(ge=0)]
    transfers: Annotated[int, Field(ge=0)]
    walkDistance: NonNegative
    walkDuration: NonNegative


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
            walk = Walk(distance=summary['distance'], duration=math.ceil(seconds / 60))
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
