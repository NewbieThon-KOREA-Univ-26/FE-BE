from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config.settings import Settings
from src.services.compare import ApiError, CompareResponse, Odsay

Longitude = Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)]
Latitude = Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)]


def create_app(settings: Settings | None = None, transport=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(transport=transport) as client:
            app.state.odsay = Odsay(client, settings)
            yield

    app = FastAPI(title='걸을만한데? API', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=['GET'], allow_headers=['*'])

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status,
                            content={'error': {'code': exc.code, 'message': exc.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400, content={'error': {
            'code': 'INVALID_INPUT', 'message': '유효한 출발지·도착지 경도와 위도를 입력하세요',
        }})

    @app.get('/api/health')
    async def health():
        return {'status': 'ok'}

    @app.get('/api/compare', response_model=CompareResponse)
    async def compare(request: Request, startX: Longitude, startY: Latitude,
                      endX: Longitude, endY: Latitude):
        if (startX, startY) == (endX, endY):
            raise ApiError(400, 'SAME_LOCATION', '출발지와 도착지가 같습니다')
        return await request.app.state.odsay.compare(startX, startY, endX, endY)

    return app


app = create_app()
