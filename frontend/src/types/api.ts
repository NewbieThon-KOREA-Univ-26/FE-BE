/**
 * 화면에서 사용하는 경로 비교 결과 타입입니다.
 * 필드를 바꿀 때는 명세서도 같이 고쳐 주세요.
 */

/** 좌표. 명세서 규칙대로 X = 경도(lng), Y = 위도(lat) 입니다. */
export interface Coordinate {
  x: number
  y: number
}

export interface WalkInfo {
  paths?: Coordinate[][]
  geometryWarning?: string | null
  /** 총 도보 거리 (m) */
  distance: number
  /** 총 도보 시간 (분) */
  duration: number
  /** 소모 열량 (kcal). F7 구현 시에만 내려옵니다. */
  calories?: number
  /** 기존 단일 경로 응답과의 호환용. 지도는 구간별 paths를 사용합니다. */
  path?: Coordinate[]
}

export type TransitRouteMode = 'bus' | 'subway'

export interface TransitRouteStep {
  mode: TransitRouteMode
  lineName?: string
  fromName?: string
  toName?: string
}

export interface TransitInfo {
  paths?: Coordinate[][]
  geometryWarning?: string | null
  /** 대중교통 총 소요시간 (분) */
  duration: number
  /** 대중교통 요금 (원) */
  fare: number
  /** 환승 횟수 (회) */
  transfers: number
  /** 대중교통 경로 안에 포함된 도보 거리 (m) */
  walkDistance: number
  /** 대중교통 경로 안에 포함된 도보 시간 (분) */
  walkDuration: number
  /** 대중교통 경로 좌표. 정류장·역을 이은 근사 폴리라인입니다. */
  path?: Coordinate[]
  /** 대중교통 탑승 구간별 간단한 승차·하차 안내입니다. */
  routeSteps?: TransitRouteStep[]
}

export interface Savings {
  /** 걸었을 때 아끼는 돈 (원). 화면에서 가장 크게 보여줄 숫자입니다. */
  amount: number
  /** 걸을 때 더 드는 시간 (분) */
  extraMinutes: number
}

export type RecommendationChoice = 'walk' | 'transit'

export interface Recommendation {
  choice: RecommendationChoice
  /** 결과 화면의 한 줄 결론에 그대로 출력합니다. */
  reason: string
  /** 날씨를 반영한 추가 추천 이유. 예: 비가 와서 대중교통을 추천합니다. */
  weatherReason?: string
}

export interface WeatherInfo {
  condition: string
  iconUrl?: string
  temperatureC?: number
  precipitationProbability?: number
}

export interface CompareResponse {
  walk: WalkInfo
  transit: TransitInfo
  savings: Savings
  recommendation: Recommendation
  weather?: WeatherInfo
}

/** 화면이 안내 문구를 고를 때 쓰는 에러 코드. ErrorBanner 의 표와 짝을 이룹니다. */
export type ApiErrorCode =
  | 'INVALID_INPUT'
  | 'SAME_LOCATION'
  | 'NO_ROUTE'
  | 'UPSTREAM_ERROR'
  | 'RATE_LIMITED'
  | 'CONFIGURATION_ERROR'
  | 'SERVICE_NOT_CONFIGURED'
  | 'INTERNAL_ERROR'
