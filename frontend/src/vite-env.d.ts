/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 'true' 면 ODsay 대신 예시 응답을 사용합니다. */
  readonly VITE_USE_MOCK?: string
  /** 카카오 지도 JavaScript 키. 없으면 좌표 직접 입력 UI로 동작합니다. */
  readonly VITE_KAKAO_MAP_KEY?: string
  /**
   * 백엔드 주소. 비워 두면 같은 도메인의 /api 로 보냅니다.
   * 백엔드를 별도 프로젝트로 배포했다면 그 주소를 넣습니다. 예: https://walkride-api.vercel.app
   */
  readonly VITE_API_BASE_URL?: string
}
