import type { Coordinate, CompareResponse } from '../types/api'
import { postJson } from './client'
import { mockCompare } from './mock'

/** .env 의 VITE_USE_MOCK=true 면 백엔드 대신 예시 응답을 씁니다. */
const IS_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

/**
 * POST /api/compare — 도보와 대중교통을 비교해 절감액과 추천을 받습니다.
 * 실제 경로 조회는 백엔드가 카카오맵 REST API 로 대신합니다.
 */
export function fetchCompare(start: Coordinate, end: Coordinate): Promise<CompareResponse> {
  if (IS_MOCK) {
    return mockCompare(start, end)
  }
  // 좌표를 요청 본문에 싣습니다. 배포 프록시가 쿼리스트링이나 경로 뒷부분을
  // 백엔드까지 넘기지 않는 경우가 있어, 본문으로 보내면 그 영향을 받지 않습니다.
  // 백엔드는 본문·경로·쿼리 세 방식을 모두 받습니다.
  return postJson<CompareResponse>('/api/compare', { start, end })
}
