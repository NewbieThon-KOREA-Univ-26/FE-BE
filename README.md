# FE-BE

2026 뉴비톤 32조 `걸을만한데?` 프로젝트입니다. 출발지와 도착지의 도보·대중교통 경로를
비교해 걸었을 때 절약하는 금액과 추가 시간을 보여줍니다.

## 현재 서비스 구조

```text
브라우저(Vercel)
├── 카카오 JavaScript SDK: 지도와 장소 검색
└── ODsay Web API: 도보·대중교통 경로, 요금, 지도 좌표
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

Vercel에는 다음 환경변수가 필요합니다.

- `VITE_USE_MOCK=false`
- `VITE_KAKAO_MAP_KEY`: 카카오 JavaScript 키
- `VITE_ODSAY_API_KEY`: ODsay Web 키
- `VITE_WALK_MAX_MINUTES=30`
- `VITE_WALK_MAX_METERS=2000`

ODsay 서비스 URI에는 `walkride-fe.vercel.app`, 카카오 JavaScript SDK 허용 도메인에는
`https://walkride-fe.vercel.app`을 등록하고 Vercel을 재배포합니다.
