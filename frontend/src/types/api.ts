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
}

export interface CompareResponse {
  walk: WalkInfo
  transit: TransitInfo
  savings: Savings
  recommendation: Recommendation
}

/** 명세서의 에러 코드. 프론트에서만 쓰는 NETWORK_ERROR 는 client.ts 에서 추가합니다. */
export type ApiErrorCode =
  | 'INVALID_INPUT'
  | 'SAME_LOCATION'
  | 'NO_ROUTE'
  | 'UPSTREAM_ERROR'
  | 'RATE_LIMITED'
  | 'CONFIGURATION_ERROR'
  | 'SERVICE_NOT_CONFIGURED'
