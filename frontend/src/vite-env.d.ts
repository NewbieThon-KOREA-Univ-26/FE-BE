/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 백엔드 주소. 비어 있으면 상대 경로(/api)로 요청하고 개발 서버 프록시가 처리합니다. */
  readonly VITE_API_BASE_URL?: string
  /** 'true' 면 백엔드 대신 예시 응답을 사용합니다. */
  readonly VITE_USE_MOCK?: string
  /** 카카오 지도 JavaScript 키. 없으면 좌표 직접 입력 UI로 동작합니다. */
  readonly VITE_KAKAO_MAP_KEY?: string
}
