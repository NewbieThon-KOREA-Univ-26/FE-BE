import { useCallback, useState } from 'react'
import type { Coordinate } from '../types/api'

export type GeoStatus = 'idle' | 'loading' | 'ready' | 'denied' | 'unsupported' | 'error'

interface GeoState {
  status: GeoStatus
  position?: Coordinate
  message?: string
}

/**
 * 브라우저 위치 권한으로 현재 위치를 가져옵니다. (F1 "현재 위치로 출발지 자동 채우기")
 * 권한을 거부하면 status 가 'denied' 가 되므로 화면에서는 버튼을 숨기고 직접 입력을 안내합니다.
 */
export function useCurrentPosition() {
  const [state, setState] = useState<GeoState>(() =>
    typeof navigator !== 'undefined' && 'geolocation' in navigator
      ? { status: 'idle' }
      : { status: 'unsupported', message: '이 브라우저는 위치 기능을 지원하지 않습니다' },
  )

  const request = useCallback(() => {
    if (!('geolocation' in navigator)) {
      return
    }
    setState({ status: 'loading' })
    navigator.geolocation.getCurrentPosition(
      (result) => {
        setState({
          status: 'ready',
          position: { x: result.coords.longitude, y: result.coords.latitude },
        })
      },
      (error) => {
        if (error.code === error.PERMISSION_DENIED) {
          setState({ status: 'denied', message: '위치 권한이 거부되어 출발지를 직접 입력해 주세요' })
        } else {
          setState({ status: 'error', message: '현재 위치를 가져오지 못했습니다. 직접 입력해 주세요' })
        }
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 60_000 },
    )
  }, [])

  return { ...state, request }
}
