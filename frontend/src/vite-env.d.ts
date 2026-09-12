/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 'true' 면 ODsay 대신 예시 응답을 사용합니다. */
  readonly VITE_USE_MOCK?: string
  /** 카카오 지도 JavaScript 키. 없으면 좌표 직접 입력 UI로 동작합니다. */
  readonly VITE_KAKAO_MAP_KEY?: string
  /** ODsay 서비스 URI에 묶인 브라우저용 Web API 키입니다. */
  readonly VITE_ODSAY_API_KEY?: string
  readonly VITE_WALK_MAX_MINUTES?: string
  readonly VITE_WALK_MAX_METERS?: string
}
