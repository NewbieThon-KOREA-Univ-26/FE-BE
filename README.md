# FE-BE

2026 뉴비톤 32조 `걸을만한데?` 프로젝트입니다. 출발지와 도착지의 도보·대중교통 경로를
비교해 걸었을 때 절약하는 금액과 추가 시간을 보여줍니다.

## 현재 서비스 구조

```text
브라우저(Vercel)
├── 카카오 JavaScript SDK: 지도와 장소 검색
└── 카카오맵 REST API: 도보·대중교통 경로, 요금, 지도 좌표 (백엔드에서 호출)
```

운영 프론트는 ODsay를 직접 호출합니다. 따라서 Render 백엔드와 고정 공인 IP는 필요하지
않습니다. `backend/`의 FastAPI 코드는 기존 서버 방식의 참고·대체 구현으로 남겨둡니다.

## 실행

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

자세한 환경변수와 배포 방법은 [frontend/README.md](frontend/README.md)를 확인하세요.

## 배포 설정

경로 조회는 **백엔드가** 카카오맵 REST API 로 합니다. REST 키는 비밀이고,
카카오 REST 엔드포인트는 브라우저에서 부르면 CORS 가 막히기 때문입니다.

| 변수 | 쓰는 곳 | 값 |
| --- | --- | --- |
| `KAKAO_REST_API_KEY` | 백엔드 | 카카오 **REST API** 키 |
| `VITE_KAKAO_MAP_KEY` | 프론트 | 카카오 **JavaScript** 키 (지도·장소 검색) |
| `VITE_USE_MOCK` | 프론트 | `false` |

키 두 개는 서로 다릅니다. 바꿔 넣으면 동작하지 않습니다.
`VITE_` 로 시작하는 값은 브라우저 번들에 그대로 노출되므로 REST 키를 넣으면 안 됩니다.

카카오디벨로퍼스에서 다음을 확인하세요.

- [제품 설정] > [카카오맵] 에서 **사용 설정** 을 켭니다. 경로 API 가 여기에 묶여 있습니다.
- JavaScript SDK 허용 도메인에 `https://walkride-fe.vercel.app` 과 `http://localhost:5173` 을 등록합니다.

환경변수를 바꾼 뒤에는 **재배포해야** `VITE_` 값이 반영됩니다.

## 백엔드를 Render 에 배포하기

저장소 루트의 `render.yaml` 이 설정을 담고 있습니다. Render 대시보드에서 Blueprint 로
이 저장소를 연결하면 그대로 만들어집니다. 손으로 서비스를 만들었다면 Settings 를
아래와 같이 맞추세요.

| 항목 | 값 |
| --- | --- |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |

**Start Command 가 가장 자주 틀리는 부분입니다.** `--host 0.0.0.0` 이 없거나 포트를
`8000` 처럼 고정하면 Render 가 트래픽을 보내지 못해 요청이 404 로 떨어집니다.
이때 응답 헤더에 `x-render-routing: no-server` 가 붙습니다. CORS 문제로 보이지만
실제로는 서비스가 떠 있지 않은 것입니다.

환경변수는 대시보드에 넣습니다.

| 변수 | 값 |
| --- | --- |
| `KAKAO_REST_API_KEY` | 카카오 REST API 키 |
| `CORS_ORIGINS` | `https://walkride-fe.vercel.app,http://localhost:5173` |

`CORS_ORIGINS` 는 쉼표 구분과 JSON 배열을 모두 받습니다.

그다음 프론트(Vercel) 프로젝트에 백엔드 주소를 넣고 재배포합니다.

```
VITE_API_BASE_URL=https://walkride-api.onrender.com
```

> Render 무료 요금제는 접속이 없으면 서비스를 내립니다. 다시 깨어나는 데 1분쯤
> 걸리므로 첫 요청이 느릴 수 있습니다. 발표 직전에 한 번 열어 두세요.

## 백엔드를 따로 배포하기 (라우팅이 계속 막힐 때)

Vercel Services 는 Beta 라서 `/api/*` 로 보낸 경로와 쿼리가 백엔드까지 전달되지 않는
경우가 있습니다. 그럴 때는 라우팅 계층을 건너뛰는 편이 빠릅니다.

1. `backend/` 를 Root Directory 로 하는 **별도 Vercel 프로젝트**를 만듭니다.
2. 그 프로젝트에 `KAKAO_REST_API_KEY` 와 `CORS_ORIGINS=["https://walkride-fe.vercel.app"]` 를 넣습니다.
3. 프론트 프로젝트에 `VITE_API_BASE_URL=https://<백엔드주소>` 를 넣고 재배포합니다.

프론트는 이 값이 있으면 그 주소로 직접 호출합니다. 비어 있으면 지금처럼 같은 도메인의
`/api` 로 보냅니다. 코드 수정은 필요 없습니다.

## 요청이 어떻게 도착하는지 확인하기

`GET /api/echo?a=1` 을 열면 백엔드가 실제로 받은 메서드·경로·쿼리·본문을 그대로 돌려줍니다.
프록시가 무엇을 지우는지 확인할 때 쓰세요. 헤더는 이름만 담고 값은 담지 않습니다.
