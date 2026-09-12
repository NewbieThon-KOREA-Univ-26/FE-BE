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
