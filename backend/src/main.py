from contextlib import asynccontextmanager
import hmac
from typing import Annotated

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response

from src.config.settings import Settings
from src.services.compare import ApiError, CompareResponse, Odsay
from src.services.auth import (
    SESSION_COOKIE,
    STATE_COOKIE,
    STATE_TTL_SECONDS,
    AuthUser,
    KakaoAuth,
)
from src.services.kakao import KakaoRouting

Longitude = Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)]
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

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status,
                            content={'error': {'code': exc.code, 'message': exc.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400, content={'error': {
            'code': 'INVALID_INPUT', 'message': '유효한 출발지·도착지 경도와 위도를 입력하세요',
        }})

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        # 빈 500 대신 화면이 안내할 수 있는 형식으로 돌려줍니다.
        # 예외 메시지에는 키가 섞일 수 있으므로 종류만 남깁니다.
        return JSONResponse(status_code=500, content={'error': {
            'code': 'INTERNAL_ERROR',
            'message': f'서버에서 예기치 못한 오류가 발생했습니다 ({type(exc).__name__})',
        }})

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

    # path 나 calories 처럼 값이 없는 선택 필드는 응답에서 아예 빼서
    # 명세서의 "구현 시에만 내려옵니다" 규칙을 지킵니다.
    @app.get('/api/compare', response_model=CompareResponse, response_model_exclude_none=True)
    async def compare(request: Request, startX: Longitude, startY: Latitude,
                      endX: Longitude, endY: Latitude):
        if (startX, startY) == (endX, endY):
            raise ApiError(400, 'SAME_LOCATION', '출발지와 도착지가 같습니다')
        return await service(request.app, 'router').compare(startX, startY, endX, endY)

    return app


app = create_app()
