# Frontend

React 19 + Vite + TypeScript 기반 "걸을까 탈까" 프론트엔드입니다.
노션의 기획 · 기능 명세서 · 사용자 흐름 · API 명세서 문서를 바탕으로 뼈대만 잡아 두었습니다.

## 실행 (PowerShell)

프로젝트 루트에서 실행합니다. Node.js 20 이상이 필요합니다.

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

브라우저에서 http://localhost:5173 을 엽니다.
`.env.example` 그대로 복사하면 **예시 데이터 모드**(`VITE_USE_MOCK=true`)라서 백엔드 없이도 화면이 돌아갑니다.
"예시 좌표 채우기" 를 누르고 "비교하기" 를 누르면 결과 화면까지 볼 수 있습니다.

| 명령 | 하는 일 |
| --- | --- |
| `npm run dev` | 개발 서버 (핫 리로드) |
| `npm run build` | 타입 검사 후 `dist/` 에 배포용 빌드 |
| `npm run preview` | 빌드 결과 미리보기 |
| `npm run typecheck` | 타입 검사만 |

## 환경변수 (`.env`)

| 변수 | 설명 |
| --- | --- |
| `VITE_API_BASE_URL` | 백엔드 주소. 비워 두면 개발 서버가 `/api` 요청을 `http://localhost:8000` 으로 프록시합니다. 배포 시 백엔드 주소를 넣습니다. |
| `VITE_USE_MOCK` | `true` 면 백엔드 대신 API 명세서의 예시 응답을 씁니다. 화면 상단에 "예시 데이터 모드" 표시가 나옵니다. |
| `VITE_KAKAO_MAP_KEY` | 카카오 지도 JavaScript 키. 없으면 장소 검색과 지도 대신 "위도, 경도" 직접 입력으로 동작합니다. |

`.env` 는 Git에 올라가지 않습니다. 카카오 키는 브라우저에 노출되는 키이므로 카카오 개발자 콘솔에서 허용 도메인을 꼭 등록하세요.
ODsay 등 유료·비밀 키는 프론트에 넣지 말고 백엔드에만 둡니다 (API 명세서 참고).

## 폴더 구조

```
src/
├── main.tsx                 진입점
├── App.tsx                  한 페이지 레이아웃 (왼쪽 입력+결과, 오른쪽 지도)
├── index.css                전역 스타일
├── api/
│   ├── client.ts            fetch 래퍼, 명세서의 에러 형식을 ApiError 로 변환
│   ├── compare.ts           GET /api/compare 호출
│   └── mock.ts              백엔드 없이 쓰는 예시 응답
├── components/
│   ├── RouteForm.tsx        1. 입력 화면 — 출발지·도착지, 현재 위치, 비교하기 (F1)
│   ├── PlaceSearchInput.tsx 장소 검색 (카카오 키 있을 때) / 좌표 직접 입력 (없을 때)
│   ├── ResultPanel.tsx      2. 비교 결과 화면 — 절감액, 걷기 vs 대중교통, 한 줄 결론 (F2~F5)
│   ├── ErrorBanner.tsx      에러 코드별 안내 + 다시 시도
│   └── MapPanel.tsx         카카오 지도 + 출발지·도착지 마커 (키 없으면 자리표시자)
├── hooks/
│   ├── useCompare.ts        비교 요청 상태 (idle / loading / success / error)
│   └── useCurrentPosition.ts 브라우저 위치 권한 처리
├── lib/kakao.ts             카카오 지도 SDK 로더, 키워드 장소 검색
├── types/
│   ├── api.ts               API 명세서와 1:1로 맞춘 요청·응답 타입
│   ├── place.ts             출발지·도착지 타입
│   └── kakao.ts             카카오 SDK 중 쓰는 부분만 타이핑
└── utils/format.ts          원 · 분 · m/km 표기
```

## 노션 문서와의 대응

| 문서 | 반영한 곳 |
| --- | --- |
| 기능 명세서 F1 출발지·도착지 입력 | `RouteForm`, `PlaceSearchInput`, `useCurrentPosition` |
| 기능 명세서 F2~F5 조회·절감액·비교 표시 | `ResultPanel` (데이터는 백엔드 `/api/compare` 가 계산) |
| 기능 명세서 F7 소모 열량 (선택) | `walk.calories` 가 오면 표시, 없으면 숨김 |
| 사용자 흐름 · 화면 스케치 | `App` 레이아웃, 좌표 직접 입력 폴백 |
| 사용자 흐름 · 예외 상황 표 | 같은 좌표 차단, 위치 권한 거부 시 버튼 숨김, 오류 시 입력값 유지 |
| API 명세서 · 응답 필드와 에러 코드 | `types/api.ts`, `api/client.ts`, `ErrorBanner` |

## 백엔드와 붙이기

- 개발 중에는 Vite 프록시가 `/api` 를 `http://localhost:8000` 으로 넘기므로 같은 출처처럼 동작합니다.
- 배포하면 프론트(Vercel)와 백엔드 도메인이 달라지므로 FastAPI 에 CORS 미들웨어가 필요합니다 (API 명세서 "정해야 할 것" 참고).
- 응답 필드를 바꾸면 `src/types/api.ts` 와 노션 API 명세서를 같이 고칩니다.

## 아직 안 한 것

- 카카오 지도 키 없이 만들었으므로 **장소 검색과 지도는 실제 키로 동작 확인이 필요**합니다. 키 없이 도는 좌표 직접 입력 화면만 확인했습니다.
- 지도에 경로 선(스케치의 빨간 도보 / 파란 대중교통)은 그리지 않습니다. 백엔드 응답에 경로 좌표가 없어서입니다.
- 상세 화면(3번), 날씨(F6), 절감액 누적(F8), 라우터, 테스트, 린트 설정.
- "걸을 만하다" 의 경계 등 미정 항목은 백엔드가 `recommendation` 으로 내려주는 값을 그대로 씁니다. 예시 데이터 모드의 임시 기준은 `src/api/mock.ts` 상단에 있습니다.
