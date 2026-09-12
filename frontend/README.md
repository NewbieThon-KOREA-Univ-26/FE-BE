# Frontend

React + Vite로 만든 `걸을만한데?` 웹 앱입니다. 브라우저에서 카카오 지도·장소 검색과
ODsay Web API를 직접 호출하므로 배포 환경에서 FastAPI 또는 Render가 필요하지 않습니다.

## 로컬 실행

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

`frontend/.env`에 다음 값을 설정합니다.

```env
VITE_USE_MOCK=false
VITE_KAKAO_MAP_KEY=카카오_JavaScript_키
VITE_ODSAY_API_KEY=ODsay_Web_키
VITE_WALK_MAX_MINUTES=30
VITE_WALK_MAX_METERS=2000
```

카카오 JavaScript SDK 허용 도메인과 ODsay 서비스 URI에 로컬 주소 `localhost:5173`을
등록해야 합니다. 설정 변경 후에는 개발 서버를 재시작합니다.

## 동작 구조

1. 카카오 장소 검색에서 출발지·도착지의 WGS84 경도·위도를 얻습니다.
2. 브라우저가 ODsay `searchWalkPathV2`와 `searchPubTransPathT`를 병렬 호출합니다.
3. 최단시간 대중교통 경로를 선택합니다. 동률이면 요금과 환승 횟수가 적은 경로를 선택합니다.
4. 선택 경로의 `mapObj`로 `loadLane`을 호출해 버스·지하철 경로 좌표를 받습니다.
5. 도보 거리·시간, 대중교통 시간·요금, 절감액과 추천 결과를 화면에 표시합니다.

지도에서 빨간색은 도보 경로, 파란색은 버스·지하철 탑승 구간입니다. 지도 좌표만
조회하지 못한 경우에도 거리·시간·요금 결과는 유지합니다.

걷기 추천 기준은 기본 30분·2km 이하입니다. 필요하면 `VITE_WALK_MAX_MINUTES`와
`VITE_WALK_MAX_METERS`로 바꿀 수 있습니다.

## Vercel 배포

Vercel 프로젝트의 환경변수에 다음 값을 설정하고 재배포합니다.

| 변수 | 값 |
| --- | --- |
| `VITE_USE_MOCK` | `false` |
| `VITE_KAKAO_MAP_KEY` | 카카오 JavaScript 키 |
| `VITE_ODSAY_API_KEY` | ODsay 서비스 URI에 연결된 Web 키 |
| `VITE_WALK_MAX_MINUTES` | `30` |
| `VITE_WALK_MAX_METERS` | `2000` |

ODsay 서비스 URI에는 실제 운영 도메인 `walkride-fe.vercel.app`을 등록합니다.
Vercel Preview 주소는 매번 달라질 수 있으므로 등록된 Production 주소에서 확인합니다.

`VITE_` 변수는 브라우저 번들에 포함됩니다. ODsay에는 Server 키가 아닌 도메인 인증용
Web 키를 사용합니다. 키에 특수문자가 있어도 `URLSearchParams`가 URL 인코딩합니다.

## 주요 파일

```text
src/
├── api/odsay.ts              ODsay Web API 호출·응답 검증·비교 계산
├── api/compare.ts            실제/예시 데이터 모드 선택
├── api/mock.ts               화면 개발용 예시 데이터
├── components/MapPanel.tsx   카카오 지도·마커·경로 선
├── components/ResultPanel.tsx 비교 결과와 ODsay 출처 표시
├── components/RouteForm.tsx  출발지·도착지 입력
├── lib/kakao.ts              카카오 SDK와 장소 검색
└── types/api.ts              화면에서 사용하는 경로 비교 타입
```

## 검증

```powershell
npm run build
```

배포 후 브라우저 개발자 도구의 Network 탭에서 `searchWalkPathV2`,
`searchPubTransPathT`, `loadLane` 요청을 확인할 수 있습니다. 인증 오류가 나면 ODsay Web 키와
실제 페이지 도메인이 서비스 URI와 일치하는지 확인합니다.
