import asyncio
import time
from contextlib import asynccontextmanager
import hmac
import math
from typing import Annotated

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from src.config.settings import Settings
from src.services.compare import ApiError, CompareResponse, Odsay, build_comparison, distance_km
from src.services.auth import (
    SESSION_COOKIE,
    STATE_COOKIE,
    STATE_TTL_SECONDS,
    AuthUser,
    KakaoAuth,
)
from src.services.kakao import KakaoRouting
from src.services.ratelimit import RateLimiter, client_key
from src.services.savings import SavingsLedger
from src.services.weather import Weather

Longitude = Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)]


class ClaimBody(BaseModel):
    total: str | None = None
    voucher: str
Latitude = Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)]


def create_app(settings: Settings | None = None, transport=None) -> FastAPI:
    settings = settings or Settings()

    def build_services():
        """이번 요청들이 함께 쓸 외부 호출 객체를 만듭니다."""
        client = httpx.AsyncClient(transport=transport)
        provider = KakaoRouting if settings.route_provider == 'kakao' else Odsay
        return {
            'router': provider(client, settings),
            'kakao_auth': KakaoAuth(client, settings),
            'weather': Weather(client, settings),
            'savings': SavingsLedger(settings),
        }, client

    def service(app: FastAPI, name: str):
        """app.state 에서 객체를 꺼냅니다. 없으면 그때 만듭니다.

        서버리스(Vercel)에서는 ASGI lifespan 이 실행되지 않을 수 있습니다.
        그러면 app.state 가 비어 있어 요청이 AttributeError 로 죽고 빈 500 이 나갑니다.
        여기서 없으면 만들어 두어 어느 환경에서도 동작하게 합니다.
        """
        value = getattr(app.state, name, None)
        if value is None:
            services, _ = build_services()
            for key, item in services.items():
                setattr(app.state, key, item)
            value = getattr(app.state, name)
        return value

    @asynccontextmanager
    async def lifespan(app):
        services, client = build_services()
        for key, item in services.items():
            setattr(app.state, key, item)
        try:
            yield
        finally:
            await client.aclose()
            for key in services:
                setattr(app.state, key, None)

    app = FastAPI(title='걸을만한데? API', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_credentials=True, allow_methods=['GET', 'POST'], allow_headers=['*'])

    limiter = RateLimiter(settings.rate_limit_per_minute)
    compare_cache: dict[tuple, tuple[float, CompareResponse]] = {}

    @app.middleware('http')
    async def guard(request: Request, call_next):
        """/api 요청에 남용 제한과 보안 헤더를 붙입니다."""
        if request.url.path.startswith('/api/') and request.url.path != '/api/health':
            if not limiter.allow(client_key(request.headers, request.client.host if request.client else None)):
                response = JSONResponse(status_code=429, content={'error': {
                    'code': 'RATE_LIMITED', 'message': '요청이 너무 많습니다. 잠시 후 다시 시도해 주세요'}})
                response.headers['Retry-After'] = '60'
                return response
        response = await call_next(request)
        if request.url.path.startswith('/api/'):
            response.headers.setdefault('X-Content-Type-Options', 'nosniff')
            response.headers.setdefault('Referrer-Policy', 'no-referrer')
            response.headers.setdefault('Cache-Control', 'no-store')
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status,
                            content={'error': {'code': exc.code, 'message': exc.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # 어떤 항목이 실제로 도착했는지 함께 알려 줍니다.
        # 배포 환경에서 쿼리스트링이 전달되지 않는 경우를 바로 구분하기 위해서입니다.
        # 값이 아니라 이름만 담습니다.
        received = ', '.join(sorted(request.query_params)) or '없음'
        missing = [str(error.get('loc', ('?',))[-1]) for error in exc.errors()]
        problem = ", ".join(missing) or "없음"
        if request.url.path.startswith('/api/compare'):
            message = ('유효한 출발지·도착지 경도와 위도를 입력하세요 '
                       f'(받은 경로: {request.url.path} / 받은 항목: {received} / 문제 항목: {problem})')
        else:
            message = f'요청 형식이 올바르지 않습니다 (문제 항목: {problem})'
        return JSONResponse(status_code=400, content={'error': {'code': 'INVALID_INPUT', 'message': message}})

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        # 빈 500 대신 화면이 안내할 수 있는 형식으로 돌려줍니다.
        # 예외 메시지에는 키가 섞일 수 있으므로 종류만 남깁니다.
        return JSONResponse(status_code=500, content={'error': {
            'code': 'INTERNAL_ERROR',
            'message': f'서버에서 예기치 못한 오류가 발생했습니다 ({type(exc).__name__})',
        }})

    @app.api_route('/api/echo', methods=['GET', 'POST'])
    async def echo(request: Request):
        """요청이 백엔드에 어떤 모습으로 도착했는지 그대로 보여 줍니다.

        배포 프록시가 경로·쿼리·메서드·본문 중 무엇을 지우는지 확인하는 용도입니다.
        비밀이 섞일 수 있는 헤더 값은 담지 않고 이름만 담습니다.
        """
        if not settings.debug_raw_upstream:
            raise ApiError(404, 'NOT_FOUND', '진단 엔드포인트가 꺼져 있습니다')
        try:
            body = (await request.body()).decode('utf-8', 'replace')[:500]
        except Exception:
            body = '(읽지 못함)'
        return {
            'method': request.method,
            'path': request.url.path,
            'query': str(request.url.query),
            'queryKeys': sorted(request.query_params),
            'body': body,
            'headerNames': sorted(request.headers),
        }

    @app.get('/api/health')
    async def health():
        return {'status': 'ok', 'provider': settings.route_provider}

    @app.get('/api/auth/kakao/login')
    async def kakao_login(request: Request):
        auth: KakaoAuth = service(request.app, 'kakao_auth')
        state = auth.new_state()
        response = RedirectResponse(auth.authorization_url(state), status_code=302)
        response.set_cookie(
            STATE_COOKIE,
            state,
            max_age=STATE_TTL_SECONDS,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite='lax',
            path='/api/auth/kakao',
        )
        return response

    @app.get('/api/auth/kakao/callback')
    async def kakao_callback(request: Request, code: str | None = None,
                             state: str | None = None, error: str | None = None):
        auth: KakaoAuth = service(request.app, 'kakao_auth')
        expected_state = request.cookies.get(STATE_COOKIE)
        valid_state = bool(state and expected_state and hmac.compare_digest(state, expected_state))
        if error or not code or not valid_state:
            response = RedirectResponse(auth.failure_url('KAKAO_LOGIN_FAILED'), status_code=302)
            response.delete_cookie(STATE_COOKIE, path='/api/auth/kakao')
            return response
        try:
            user = await auth.authenticate(code)
            response = RedirectResponse(settings.frontend_url, status_code=302)
            response.set_cookie(
                SESSION_COOKIE,
                auth.create_session(user),
                max_age=60 * 60 * 24 * 7,
                httponly=True,
                secure=settings.session_cookie_secure,
                samesite='lax',
                path='/',
            )
        except ApiError:
            response = RedirectResponse(auth.failure_url('KAKAO_LOGIN_FAILED'), status_code=302)
        response.delete_cookie(STATE_COOKIE, path='/api/auth/kakao')
        return response

    @app.get('/api/auth/me')
    async def current_user(request: Request) -> dict[str, AuthUser | None]:
        auth: KakaoAuth = service(request.app, 'kakao_auth')
        return {'user': auth.read_session(request.cookies.get(SESSION_COOKIE))}

    @app.post('/api/auth/logout', status_code=204)
    async def logout() -> Response:
        response = Response(status_code=204)
        response.delete_cookie(SESSION_COOKIE, path='/')
        return response

    async def run_compare(request: Request, sx: float, sy: float, ex: float, ey: float):
        if (sx, sy) == (ex, ey):
            raise ApiError(400, 'SAME_LOCATION', '출발지와 도착지가 같습니다')
        km = distance_km(sx, sy, ex, ey)
        if km > settings.max_distance_km:
            raise ApiError(400, 'TOO_FAR',
                           f'출발지와 도착지가 약 {km:.0f}km 떨어져 있어요. '
                           f'{settings.max_distance_km:g}km 이내 구간만 비교할 수 있습니다')
        cache_key = (round(sx, 4), round(sy, 4), round(ex, 4), round(ey, 4))
        cached = compare_cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            result = cached[1]
        else:
            # 날씨는 경로 조회와 나란히 묻고, 못 구하면 없이 갑니다 (F6).
            result, weather = await asyncio.gather(
                service(request.app, 'router').compare(sx, sy, ex, ey),
                service(request.app, 'weather').current(sx, sy),
            )
            if weather is not None:
                result = build_comparison(result.walk, result.transit, settings, weather)
            if settings.compare_cache_seconds:
                if len(compare_cache) >= 256:
                    compare_cache.pop(next(iter(compare_cache)))
                compare_cache[cache_key] = (time.monotonic() + settings.compare_cache_seconds, result)
        # 적립권은 캐시와 무관하게 요청마다 새로 발급합니다 (1회용이라 재사용되면 안 됩니다).
        response = result.model_copy(deep=True)
        response.savings.voucher = service(request.app, 'savings').issue_voucher(response.savings.amount)
        return response

    @app.get('/api/savings')
    async def read_savings(request: Request, total: str | None = None):
        """누적액 토큰을 검증해 숫자로 돌려줍니다. 위조·손상이면 0 과 valid=false."""
        saved, walks, valid = service(request.app, 'savings').total_from(total)
        return {'saved': saved, 'walks': walks, 'valid': valid}

    @app.post('/api/savings/claim')
    async def claim_savings(request: Request, body: ClaimBody):
        """F9 — 적립권을 소모하고 새 누적액 토큰을 돌려줍니다."""
        return service(request.app, 'savings').claim(body.total, body.voucher)

    @app.get('/api/debug/upstream/{kind}')
    async def debug_upstream(request: Request, kind: str, startX: Longitude, startY: Latitude,
                             endX: Longitude, endY: Latitude):
        """카카오 원본 응답을 그대로 돌려줍니다. DEBUG_RAW_UPSTREAM=true 일 때만 열립니다.

        해석에 실패했을 때 실제 필드 이름을 확인하는 용도입니다.
        응답에는 키가 들어 있지 않으므로 노출되는 비밀은 없습니다.
        """
        router = service(request.app, 'router')
        if not settings.debug_raw_upstream or kind not in ('walk', 'transit') or not hasattr(router, 'raw'):
            raise ApiError(404, 'NOT_FOUND', '진단 엔드포인트가 꺼져 있습니다')
        return {'kind': kind, 'data': await router.raw(kind, startX, startY, endX, endY)}

    # path 나 calories 처럼 값이 없는 선택 필드는 응답에서 아예 빼서
    # 명세서의 "구현 시에만 내려옵니다" 규칙을 지킵니다.
    @app.get('/api/compare', response_model=CompareResponse, response_model_exclude_none=True)
    async def compare(request: Request, startX: Longitude, startY: Latitude,
                      endX: Longitude, endY: Latitude):
        return await run_compare(request, startX, startY, endX, endY)

    def parse_pair(raw: str, label: str) -> tuple[float, float]:
        """'경도,위도' 문자열을 좌표로 바꿉니다."""
        parts = raw.split(',')
        if len(parts) != 2:
            raise ApiError(400, 'INVALID_INPUT', f'{label} 는 "경도,위도" 형식이어야 합니다')
        try:
            x, y = float(parts[0]), float(parts[1])
        except ValueError:
            raise ApiError(400, 'INVALID_INPUT', f'{label} 의 좌표를 숫자로 읽을 수 없습니다') from None
        if not (math.isfinite(x) and math.isfinite(y)) or abs(x) > 180 or abs(y) > 90:
            raise ApiError(400, 'INVALID_INPUT', f'{label} 좌표가 범위를 벗어났습니다')
        return x, y

    class ComparePoint(BaseModel):
        x: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
        y: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]

    class CompareRequest(BaseModel):
        start: ComparePoint
        end: ComparePoint

    # 좌표를 요청 본문으로 받습니다.
    #
    # 배포 프록시가 쿼리스트링이나 경로 뒷부분을 넘기지 않는 경우가 있습니다.
    # 본문은 그런 영향을 받지 않으므로 프론트는 이 방식을 먼저 씁니다.
    @app.post('/api/compare', response_model=CompareResponse, response_model_exclude_none=True)
    async def compare_by_body(request: Request, body: CompareRequest):
        return await run_compare(request, body.start.x, body.start.y, body.end.x, body.end.y)

    # 같은 비교를 경로(path)로도 받습니다.
    #
    # 배포 환경의 프록시가 쿼리스트링을 넘기지 않는 경우가 있어, 좌표를 경로에 실으면
    # 그 영향을 받지 않습니다. 프론트는 이쪽을 먼저 부르고 실패하면 쿼리 방식으로 돌아갑니다.
    #     GET /api/compare/127.0276,37.4979/127.04,37.51
    @app.get('/api/compare/{start}/{end}', response_model=CompareResponse,
             response_model_exclude_none=True)
    async def compare_by_path(request: Request, start: str, end: str):
        sx, sy = parse_pair(start, '출발지')
        ex, ey = parse_pair(end, '도착지')
        return await run_compare(request, sx, sy, ex, ey)

    return app


app = create_app()
