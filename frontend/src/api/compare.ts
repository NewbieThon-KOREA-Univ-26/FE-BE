import type { Coordinate, CompareResponse } from '../types/api'
import { getJson } from './client'
import { mockCompare } from './mock'

/** .env 의 VITE_USE_MOCK=true 면 백엔드 대신 예시 응답을 씁니다. */
const IS_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

/**
 * GET /api/compare — 도보와 대중교통을 비교해 절감액과 추천을 받습니다.
 * 실제 경로 조회는 백엔드가 카카오맵 REST API 로 대신합니다.
 */
export function fetchCompare(start: Coordinate, end: Coordinate): Promise<CompareResponse> {
  if (IS_MOCK) {
    return mockCompare(start, end)
  }
  return getJson<CompareResponse>('/api/compare', {
    startX: start.x,
    startY: start.y,
    endX: end.x,
    endY: end.y,
  })
}
