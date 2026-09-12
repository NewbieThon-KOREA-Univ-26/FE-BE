# FE-BE
2026 뉴비톤 FE + BE

한 정거장 거리, 걸을까 탈까? 도보 경로와 대중교통 경로를 비교해서 걸으면 얼마를 아끼는지 보여주는 웹서비스입니다.

| 폴더 | 내용 | 실행 방법 |
| --- | --- | --- |
| `frontend/` | React + Vite | [frontend/README.md](frontend/README.md) |
| `backend/` | Python + FastAPI | [backend/README.md](backend/README.md) |

## 한 번에 띄우기

터미널 두 개를 씁니다.

```powershell
# 터미널 1 — 백엔드 (8000번)
cd backend
.\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --port 8000

# 터미널 2 — 프론트엔드 (5173번)
cd frontend
npm run dev
```

`frontend/.env` 의 `VITE_USE_MOCK` 을 `false` 로 두면 실제 백엔드를 호출합니다.
`true` 면 백엔드 없이 예시 응답으로 화면만 돌려볼 수 있습니다.

## 배포 (Vercel)

`vercel.json` 이 프론트와 백엔드를 하나의 Vercel 프로젝트에 **두 서비스**로 배포합니다.
`/api/*` 요청은 백엔드로, 나머지는 프론트로 갑니다.
같은 도메인에서 서비스되므로 CORS 설정이 필요 없습니다.

Vercel 대시보드에 넣을 환경변수입니다. 값을 바꾸면 **재배포해야** 반영됩니다.

| 변수 | 값 | 쓰는 곳 |
| --- | --- | --- |
| `VITE_KAKAO_MAP_KEY` | 카카오 **JavaScript** 키 | 프론트. REST API 키가 아닙니다 |
| `VITE_USE_MOCK` | `false` | 프론트. 백엔드가 함께 배포되므로 |
| `ODSAY_API_KEY` | ODsay 키 | 백엔드. 없으면 비교 요청이 503 을 돌려줍니다 |

`VITE_` 로 시작하는 값은 브라우저 번들에 그대로 노출됩니다. ODsay 키는 넣지 마세요.

카카오 키를 쓰려면 배포 주소를 카카오 콘솔의 JavaScript SDK 도메인에 등록해야 합니다.
Vercel 미리보기 주소는 배포마다 바뀌므로 고정된 Production 주소를 등록하고 그 주소에서 확인하세요.

> Vercel Services 는 Beta 기능입니다. 배포가 실패하면 `vercel.json` 을 빼고
> 프로젝트 설정의 Root Directory 를 `frontend` 로 두어 프론트만 먼저 올릴 수 있습니다.
> 이 경우 백엔드가 없으므로 `VITE_USE_MOCK` 은 `true` 여야 합니다.
