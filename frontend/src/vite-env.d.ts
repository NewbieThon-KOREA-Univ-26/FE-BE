/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 'true' 면 ODsay 대신 예시 응답을 사용합니다. */
  readonly VITE_USE_MOCK?: string
  /** 카카오 지도 JavaScript 키. 없으면 좌표 직접 입력 UI로 동작합니다. */
  readonly VITE_KAKAO_MAP_KEY?: string
}
