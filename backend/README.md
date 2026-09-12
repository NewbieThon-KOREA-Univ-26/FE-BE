# Backend

Python 3.13 + FastAPI 기반 도보 길찾기 서비스 백엔드입니다.

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

`backend/`에서 `.env.example`을 `.env`로 복사하고 `ODSAY_API_KEY`를 입력합니다.
실제 키는 커밋하거나 프론트에 전달하지 마세요.

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --port 8000
```

- API 문서: http://localhost:8000/docs
- 상태 확인: `GET /api/health` (외부 API 사용 가능 여부까지 검사하지는 않음)
- 비교: `GET /api/compare?startX=127.0276&startY=37.4979&endX=127.04&endY=37.51`
- 프론트 `.env`에서 `VITE_USE_MOCK=false`로 설정하면 실제 백엔드를 호출합니다.

## 비교 정책 및 응답

ODsay `searchPubTransPathT`와 `searchWalkPathV2`를 호출합니다.
두 API 모두 발급 키의 사용 권한이 필요합니다. 실제 계정의 권한·요금·호출 한도는 별도 확인해야 합니다.
명세 출처: https://lab.odsay.com/guide/releaseReference?platform=web

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

ODsay가 가까운 거리(`-98`)로 대중교통 경로를 반환하지 않는 경우에도 현재는 `NO_ROUTE`입니다.
없는 요금·시간을 만들어 반환하지 않습니다. 도보만 표시하는 부분 성공 응답은 프론트 타입과 합의 후 확장해야 합니다.
도보 경로가 정상 반환되면 추천 거리 초과는 200 응답으로 처리합니다.
외부 API가 HTTP 200의 오류 본문으로 반환하는 인증·한도 오류는 현재 `UPSTREAM_ERROR`입니다.
도시간 경로, TMAP 대체, 지도 경로 좌표, 날씨·누적 절감액은 이번 구현 범위에 없습니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

HTTP 모의 응답으로 경로 선택·단위 변환·환승 계산·좌표 검증·오류 처리를 검증합니다.
실제 키와 서비스 권한 검증은 별도로 `/api/compare`를 호출해야 합니다.
