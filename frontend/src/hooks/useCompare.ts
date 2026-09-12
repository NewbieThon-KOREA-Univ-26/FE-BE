import { useCallback, useRef, useState } from 'react'
import { fetchCompare } from '../api/compare'
import { ApiError } from '../api/client'
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
