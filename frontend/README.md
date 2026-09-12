# 걸을만한데? — 프론트엔드

React 19 · TypeScript · Vite 8. 지도와 장소 검색은 카카오 지도 JavaScript SDK 로 브라우저에서 하고,
경로 비교는 백엔드 `/api/compare` 에 맡깁니다. 전체 소개는 [루트 README](../README.md) 를 보세요.

## 실행

```bash
npm install
cp .env.example .env     # 아래 값 채우기
npm run dev              # http://localhost:5173
```

| 변수 | 값 |
| --- | --- |
| `VITE_KAKAO_MAP_KEY` | 카카오 **JavaScript** 키. 카카오디벨로퍼스 → 플랫폼 → Web 에 `http://localhost:5173` 등록 |
| `VITE_API_BASE_URL` | 백엔드 주소. 로컬 `http://localhost:8000`, 배포는 Render 주소 |
| `VITE_USE_MOCK` | `true` 면 백엔드 없이 예시 응답으로 동작 |

`VITE_` 값은 빌드 시점에 번들에 들어갑니다. 바꾸면 **재시작(로컬) 또는 재배포(Vercel)** 해야 반영됩니다.
비밀 키(카카오 REST 키 등)는 절대 여기 넣지 마세요.

## 명령

| 명령 | 하는 일 |
| --- | --- |
| `npm run dev` | 개발 서버 |
| `npm run build` | 타입 검사 + 빌드 (`dist/`) |
| `npm run typecheck` | 타입 검사만 |

## 구조

```
src/
├── App.tsx                 화면 조립 · 적립(F9) · 누적액 검증
├── components/
│   ├── RouteForm.tsx        출발지·도착지 입력 (F1)
│   ├── PlaceSearchInput.tsx 카카오 장소 검색 자동완성
│   ├── ResultPanel.tsx      비교 결과 · 카드 · 승차하차 타임라인 (F5)
│   ├── MapPanel.tsx         카카오 지도 · 경로 선 · 범례
│   ├── ErrorBanner.tsx      오류 안내 (사람 말로, ?debug 면 진단)
│   ├── SavingsTotalBadge.tsx 누적 절감액 (F8)
│   ├── WalkRewardModal.tsx  적립 팝업 (F9)
│   └── ErrorBoundary.tsx    렌더링 오류 안내
├── api/                    client(HTTP) · compare · savings · mock
├── hooks/useCompare.ts     비교 요청 상태 (30km 사전 검사 포함)
├── lib/                    savings(서명 토큰) · geo(거리) · layout(모바일 판정) · kakao(SDK 로더)
├── types/                  API · 장소 타입
└── utils/format.ts         원 · 분 · km 표기
```

## 알아 두면 좋은 것

- **모바일 판정**은 `lib/layout.ts` 의 `MOBILE_QUERY` 한 곳입니다. CSS `@media` 와 같은 조건이어야 합니다.
- 누적 절감액은 주소의 `?t=` 토큰입니다. 서버 서명이라 고치면 0 으로 돌아갑니다.
- 오류 화면에서 코드·진단을 보려면 주소 뒤에 `?debug` 를 붙이세요.
