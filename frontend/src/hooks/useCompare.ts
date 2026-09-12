import { useCallback, useRef, useState } from 'react'
import { fetchCompare } from '../api/compare'
import { ApiError } from '../api/client'
import { MAX_COMPARE_KM, distanceKm } from '../lib/geo'
import type { Coordinate, CompareResponse } from '../types/api'

export type CompareState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: CompareResponse }
  | { status: 'error'; error: ApiError }

/**
 * 비교 요청의 상태(대기 → 로딩 → 성공/실패)를 관리합니다.
 * 요청이 겹치면 마지막 요청의 결과만 반영합니다.
 */
export function useCompare() {
  const [state, setState] = useState<CompareState>({ status: 'idle' })
  const requestId = useRef(0)

  const run = useCallback(async (start: Coordinate, end: Coordinate) => {
    const id = ++requestId.current
    // 너무 먼 구간은 서버에 묻지 않고 바로 알립니다. 서버도 같은 기준으로 한 번 더 막습니다.
    const km = distanceKm(start, end)
    if (km > MAX_COMPARE_KM) {
      setState({
        status: 'error',
        error: new ApiError('TOO_FAR',
          `출발지와 도착지가 약 ${Math.round(km)}km 떨어져 있어요. ${MAX_COMPARE_KM}km 이내 구간만 비교할 수 있습니다`, 400),
      })
      return
    }
    setState({ status: 'loading' })
    try {
      const data = await fetchCompare(start, end)
      if (id === requestId.current) {
        setState({ status: 'success', data })
      }
    } catch (error) {
      if (id !== requestId.current) {
        return
      }
      setState({
        status: 'error',
        error:
          error instanceof ApiError
            ? error
            : new ApiError('UNKNOWN', '알 수 없는 오류가 발생했습니다', 0),
      })
    }
  }, [])

  const reset = useCallback(() => {
    requestId.current += 1
    setState({ status: 'idle' })
  }, [])

  return { state, run, reset }
}
