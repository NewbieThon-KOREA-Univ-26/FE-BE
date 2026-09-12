import type { Coordinate, CompareResponse } from '../types/api'
import { mockCompare } from './mock'
import { compareWithOdsay } from './odsay'

/** .env 의 VITE_USE_MOCK=true 면 ODsay 대신 예시 응답을 씁니다. */
const IS_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

/**
 * 실제 모드에서는 브라우저가 ODsay Web API를 직접 호출해 비교합니다.
 */
export function fetchCompare(start: Coordinate, end: Coordinate): Promise<CompareResponse> {
  if (IS_MOCK) {
    return mockCompare(start, end)
  }
  return compareWithOdsay(start, end)
}
