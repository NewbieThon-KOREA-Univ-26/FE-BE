import { useEffect, useRef, useState, type FormEvent } from 'react'
import { hasKakaoKey } from '../lib/kakao'
import { useCurrentPosition } from '../hooks/useCurrentPosition'
import { isSamePlace, type Place } from '../types/place'
import { PlaceSearchInput } from './PlaceSearchInput'

interface Props {
  start: Place | null
  end: Place | null
  onStartChange: (place: Place | null) => void
  onEndChange: (place: Place | null) => void
  onSubmit: () => void
  loading: boolean
}

/** 1. 입력 화면 — 출발지·도착지를 넣고 비교하기를 누릅니다. */
export function RouteForm({ start, end, onStartChange, onEndChange, onSubmit, loading }: Props) {
  const geo = useCurrentPosition()
  const [validation, setValidation] = useState<string | null>(null)

  const useCurrentLocation = () => {
    geo.request()
  }

  // 현재 위치가 준비되면 출발지에 채웁니다. 콜백은 ref 로 들고 있어 부모가 매 렌더마다 새 함수를 넘겨도 한 번만 반영됩니다.
  const onStartChangeRef = useRef(onStartChange)
  onStartChangeRef.current = onStartChange
  const geoPosition = geo.position
  useEffect(() => {
    if (geoPosition) {
      onStartChangeRef.current({ name: '현재 위치', ...geoPosition })
    }
  }, [geoPosition])

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!start || !end) {
      setValidation('출발지와 도착지를 모두 입력해 주세요')
      return
    }
    if (isSamePlace(start, end)) {
      setValidation('출발지와 도착지가 같습니다. 다른 도착지를 입력해 주세요')
      return
    }
    setValidation(null)
    onSubmit()
  }

  const canUseLocation = geo.status !== 'denied' && geo.status !== 'unsupported'

  return (
    <form className={`route-form ${loading ? 'is-loading' : ''}`} onSubmit={handleSubmit} noValidate>
      <PlaceSearchInput id="start" label="출발지" value={start} onChange={onStartChange} />
      <PlaceSearchInput id="end" label="도착지" value={end} onChange={onEndChange} />

      <div className="form-tools">
        {canUseLocation && (
          <button
            type="button"
            className="link"
            onClick={useCurrentLocation}
            disabled={geo.status === 'loading'}
          >
            {geo.status === 'loading' ? '위치 확인 중…' : '현재 위치를 출발지로'}
          </button>
        )}
      </div>

      {geo.message && <p className="hint">{geo.message}</p>}
      {!hasKakaoKey && (
        <p className="hint">
          카카오 지도 키가 없어 좌표를 직접 입력합니다. .env 의 VITE_KAKAO_MAP_KEY 를 채우면 장소 검색이 켜집니다.
        </p>
      )}
      {validation && (
        <p className="hint hint-error" role="alert">
          {validation}
        </p>
      )}

      <button type="submit" className="primary" disabled={loading}>
        {loading ? '비교하는 중…' : '비교하기'}
      </button>
    </form>
  )
}
