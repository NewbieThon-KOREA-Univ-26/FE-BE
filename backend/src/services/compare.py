import asyncio
import math
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.config.settings import Settings

NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class Walk(BaseModel):
    distance: NonNegative
    duration: NonNegative


class Transit(BaseModel):
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
            return Walk(distance=summary['distance'], duration=math.ceil(seconds / 60))
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
