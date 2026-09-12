# Backend (선택)

Python 3.13 + FastAPI 기반 도보 길찾기 서비스 백엔드입니다.

이 서버가 카카오맵 REST API를 호출해 경로를 비교합니다. 프론트는 `/api/compare` 만 부릅니다. (이 서버는 현재 배포에
필요하지 않습니다. 서버 키와 고정 외부 통신 IP를 사용할 수 있는 환경으로 되돌릴 때를
위한 대체 구현입니다.

## 설치 (PowerShell)

프로젝트 루트에서 실행합니다.

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

- `fastapi[standard]`: API 프레임워크와 Uvicorn 서버 등 표준 의존성
- `httpx`: 외부 도보 길찾기 API의 비동기 HTTP 호출
- `pydantic-settings`: 환경변수 및 `.env` 설정 읽기

가상환경을 활성화하지 않아도 위처럼 실행 파일 경로를 지정하면 됩니다.
`py -3.13`이 Python을 찾지 못하면 `& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv .venv`로 생성할 수 있습니다.
API 키를 담은 `.env`와 `.venv`는 Git에서 제외합니다.

## 실행

`backend/`에서 `.env.example`을 `.env`로 복사하고 `KAKAO_REST_API_KEY`를 입력합니다.
카카오디벨로퍼스의 [제품 설정] > [카카오맵]에서 **사용 설정**을 켜야 경로 API가 호출됩니다.
실제 키는 커밋하거나 프론트에 전달하지 마세요.

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

- API 문서: http://localhost:8000/docs
- 상태 확인: `GET /api/health` (외부 API 사용 가능 여부까지 검사하지는 않음)
- 비교: `GET /api/compare?startX=127.0276&startY=37.4979&endX=127.04&endY=37.51`
- 프론트 `.env`에서 `VITE_USE_MOCK=false`로 설정하면 실제 백엔드를 호출합니다.

## 카카오 로그인

카카오 로그인은 이 백엔드가 인가 코드 교환과 서비스 세션 생성을 처리합니다. `backend/.env`에
아래 값을 채우고, 카카오 개발자 콘솔에서 카카오 로그인을 활성화합니다.

```env
KAKAO_REST_API_KEY=카카오_REST_API_키
KAKAO_CLIENT_SECRET=카카오_클라이언트_시크릿
KAKAO_REDIRECT_URI=http://localhost:8000/api/auth/kakao/callback
FRONTEND_URL=http://localhost:5173
SESSION_SECRET_KEY=충분히_긴_무작위_문자열
SESSION_COOKIE_SECURE=false
```

- 카카오 로그인 Redirect URI에는 `KAKAO_REDIRECT_URI`와 정확히 같은 주소를 등록합니다.
- 카카오 앱의 클라이언트 시크릿이 활성화되어 있으면 `KAKAO_CLIENT_SECRET`도 필수입니다.
- 배포에서는 `KAKAO_REDIRECT_URI`, `FRONTEND_URL`, `CORS_ORIGINS`를 실제 HTTPS 주소로 바꾸고
  `SESSION_COOKIE_SECURE=true`로 설정합니다.
- `GET /api/auth/kakao/login`, `GET /api/auth/me`, `POST /api/auth/logout`을 제공합니다.
  로그인 완료 후에는 카카오 액세스 토큰이 아니라 7일짜리 HttpOnly 서비스 세션 쿠키만 저장합니다.

## 비교 정책 및 응답

카카오맵 REST API의 대중교통 경로 조회와 도보 경로 조회를 호출합니다.
두 API 모두 발급 키의 사용 권한이 필요합니다. 실제 계정의 권한·요금·호출 한도는 별도 확인해야 합니다.
엔드포인트 경로는 `KAKAO_TRANSIT_PATH`, `KAKAO_WALK_PATH` 환경변수로 바꿀 수 있습니다.
문서의 요청 URL 을 통째로 넣어도 됩니다.
요청 파라미터 이름은 `KAKAO_TRANSIT_QUERY`, `KAKAO_WALK_QUERY` 로 바꿉니다.
`{sx}` `{sy}` `{ex}` `{ey}` 자리에 출발·도착 경도·위도가 들어갑니다.

```
KAKAO_TRANSIT_QUERY=origin={sx},{sy}&destination={ex},{ey}
```

파라미터를 쿼리스트링이 아니라 POST 본문으로 보내야 하면 `KAKAO_REQUEST_STYLE` 을
`post-json` 또는 `post-form` 으로 둡니다 (기본값 `get`).

응답 필드 이름을 확인해야 하면 `DEBUG_RAW_UPSTREAM=true` 로 두고
`GET /api/debug/upstream/transit?startX=…&startY=…&endX=…&endY=…` (또는 `walk`) 를 엽니다.
카카오 원본 응답이 그대로 나옵니다. 확인이 끝나면 끕니다.

## 보안·남용 방지

- **절감액 누적(F8·F9)** 은 서버가 서명한 토큰(`?t=…`)으로 저장합니다. 주소창에서 내용을 고치면 서명이
  깨져 0 으로 돌아가고, 적립은 `/api/compare` 가 준 1회용 적립권을 `/api/savings/claim` 에 내야만 됩니다.
  서명 비밀은 `SESSION_SECRET_KEY` 입니다. 없으면 프로세스마다 임의 키를 써서 재시작 시 누적액이 무효가 되므로
  배포에서는 꼭 넣으세요 (`render.yaml` 이 자동 생성합니다).
- **요청 제한**: IP 당 분당 `RATE_LIMIT_PER_MINUTE`(기본 60) 을 넘으면 429 `RATE_LIMITED`. `/api/health` 는 예외.
- **결과 캐시**: 같은 출발·도착(≈10m)은 `COMPARE_CACHE_SECONDS`(기본 120) 동안 카카오를 다시 부르지 않습니다.
- **진단 엔드포인트** `/api/echo`, `/api/debug/upstream/*` 는 `DEBUG_RAW_UPSTREAM=true` 일 때만 열립니다.
- `/api` 응답에는 `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, `Referrer-Policy: no-referrer` 가 붙습니다.
- 비밀은 `SecretStr` 로만 다루고, 오류 메시지에는 업스트림 본문·키를 담지 않습니다 (테스트로 고정).

날씨(F6)는 `WEATHER_API_KEY` 를 넣으면 켜집니다. 기본 제공자는 WeatherAPI.com 이고
`WEATHER_PROVIDER=openweather` 로 OpenWeatherMap 을 쓸 수 있습니다. 키가 없거나 조회에 실패해도
비교 결과는 날씨 없이 정상 응답합니다. 비·눈, 강수확률 60% 이상, 30°C 이상, -5°C 이하면
걷기 추천 기준을 절반으로 낮추고 `recommendation.weatherReason` 에 이유를 담습니다.

출발지·도착지 직선 거리가 `MAX_DISTANCE_KM`(기본 30) 을 넘으면 조회하지 않고 `TOO_FAR`(400) 로 알립니다.
프론트도 같은 기준으로 요청 전에 막습니다 (`frontend/src/lib/geo.ts`).

오류 메시지에는 요청한 호스트·경로와 카카오 응답 상태 코드가 담기므로,
경로·파라미터 중 무엇이 틀렸는지 화면에서 바로 알 수 있습니다.

- 도시내 대중교통 경로 중 최단시간, 동률이면 최저요금·최소환승 순서로 선택합니다.
- 요금은 선택 경로의 `payment` 값이며, 별도의 학생 할인 계산은 하지 않습니다.
- 환승은 버스·지하철 탑승 구간 수에서 1을 뺍니다.
- 대중교통 내 도보 시간은 도보 구간의 `sectionTime` 합계입니다.
- 도보 추천 경로의 초 단위 시간을 분으로 올림합니다. 거리 m, 시간 분, 금액 원입니다.
- 절감액은 대중교통 요금, 추가 시간은 도보 시간 - 대중교통 시간입니다. 음수면 걷기가 더 빠릅니다.
- 임시 걷기 추천 기준은 30분·2000m 이하입니다. `WALK_MAX_MINUTES`, `WALK_MAX_METERS`로 변경합니다.

응답은 프론트 `CompareResponse` 형식의 `walk`, `transit`, `savings`, `recommendation`을 제공합니다.
선택 기능인 칼로리는 반환하지 않습니다.

## 오류와 현재 범위

오류 형식: `{"error":{"code":"NO_ROUTE","message":"..."}}`

| HTTP | code | 상황 |
| --- | --- | --- |
| 400 | INVALID_INPUT | 좌표 누락·형식·범위 오류 |
| 400 | SAME_LOCATION | 동일한 출발·도착 좌표 |
| 404 | NO_ROUTE | 도보 또는 도시내 대중교통 경로 없음 |
| 429 | RATE_LIMITED | 외부 API가 HTTP 429 반환 |
| 502 | UPSTREAM_ERROR | 외부 API 오류·타임아웃·잘못된 응답 |
| 503 | SERVICE_NOT_CONFIGURED | 서버 API 키 미설정 |

대중교통 경로가 없으면 `NO_ROUTE`입니다. `ROUTE_PROVIDER=odsay`로 되돌리면 기존 ODsay 구현을 그대로 씁니다.
없는 요금·시간을 만들어 반환하지 않습니다. 도보만 표시하는 부분 성공 응답은 프론트 타입과 합의 후 확장해야 합니다.
도보 경로가 정상 반환되면 추천 거리 초과는 200 응답으로 처리합니다.
외부 API가 HTTP 200의 오류 본문으로 반환하는 인증·한도 오류는 현재 `UPSTREAM_ERROR`입니다.
도시간 경로, TMAP 대체, 날씨·누적 절감액은 이번 구현 범위에 없습니다.

## 지도 경로 표시

`walk.paths`와 `transit.paths`는 구간별 좌표 배열(`[[{"x":127.0,"y":37.5}, ...], ...]`)입니다.
도보는 `recommend.routes[].coordinate`, 대중교통은 선택한 경로의 `mapObj`로
`loadLane`을 추가 호출하여 `lane[].section[].graphPos`를 사용합니다.
대중교통 경로 선은 버스·지하철 탑승 구간이며, 환승·접근 도보 연결선을 임의로 생성하지 않습니다.
서로 떨어진 구간은 별도 선으로 그립니다.

좌표만 누락되거나 조회가 실패하면 기존 비교 응답은 유지하고 해당 수단에
`paths: []`, `geometryWarning`을 반환합니다. 경로 요약 조회 자체의 실패는 오류 응답입니다.

현재 프론트는 이 응답을 사용하지 않습니다. 서버 방식을 다시 사용할 경우 프론트 API 계층과
환경변수를 별도로 되돌려야 합니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

HTTP 모의 응답으로 경로 선택·단위 변환·환승 계산·좌표 검증·오류 처리를 검증합니다.
실제 키와 서비스 권한 검증은 별도로 `/api/compare`를 호출해야 합니다.

## 경로 제공자 바꾸기

`ROUTE_PROVIDER` 환경변수로 고릅니다. 기본값은 `kakao` 입니다.

| 값 | 필요한 키 | 구현 |
| --- | --- | --- |
| `kakao` | `KAKAO_REST_API_KEY` | `src/services/kakao.py` |
| `odsay` | `ODSAY_API_KEY` | `src/services/compare.py` |

두 구현 모두 같은 `/api/compare` 응답을 돌려주므로 프론트는 손댈 필요가 없습니다.

> **카카오 응답 형식은 아직 실물로 확인하지 못했습니다.**
> `src/services/kakao.py` 가 여러 후보 이름을 훑어 읽고, 해석에 실패하면
> 응답의 최상위 키 목록을 오류 메시지에 담습니다. 실제 키 이름을 확인하면
> 같은 파일 위쪽의 `*_KEYS` 목록 맨 앞에 추가하세요.

## 진입점

배포와 로컬이 같은 경로를 쓰도록 서비스 루트에 `main.py` 를 두었습니다.

```
backend/main.py      -> from src.main import app   (Vercel entrypoint: main:app)
backend/src/main.py  -> 실제 앱 구성
```

`vercel.json` 이 `src.main:app` 을 직접 가리키면 Vercel 이 그 파일을 단독 모듈로 읽어
안쪽의 `from src.config...` 가 `No module named 'src'` 로 깨집니다.
루트의 `main.py` 를 거치면 `backend/` 가 모듈 경로에 들어가 정상 동작합니다.
