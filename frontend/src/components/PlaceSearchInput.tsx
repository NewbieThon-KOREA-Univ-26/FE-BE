import { useEffect, useRef, useState } from 'react'
import { hasKakaoKey, searchPlaces } from '../lib/kakao'
import type { Place } from '../types/place'

interface Props {
  id: string
  label: string
  value: Place | null
  onChange: (place: Place | null) => void
  placeholder?: string
}

/**
 * 출발지·도착지 입력칸 (F1).
 * 카카오 키가 있으면 키워드 검색으로 장소를 고르고, 없으면 "위도, 경도"를 직접 입력합니다.
 * 어느 쪽이든 결과는 좌표가 들어 있는 Place 라서 백엔드 호출 방식은 같습니다.
 */
export function PlaceSearchInput(props: Props) {
  return hasKakaoKey ? <KakaoPlaceInput {...props} /> : <ManualPlaceInput {...props} />
}

function KakaoPlaceInput({ id, label, value, onChange, placeholder }: Props) {
  const [query, setQuery] = useState(value?.name ?? '')
  const [results, setResults] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const latestKeyword = useRef('')

  // 현재 위치 버튼 등 바깥에서 값이 바뀌면 입력칸 글자도 맞춥니다.
  useEffect(() => {
    if (value) {
      setQuery(value.name)
    }
  }, [value])

  useEffect(() => {
    const keyword = query.trim()
    latestKeyword.current = keyword
    if (!open || keyword.length < 2 || keyword === value?.name) {
      setResults([])
      return
    }
    const timer = setTimeout(() => {
      searchPlaces(keyword)
        .then((places) => {
          if (latestKeyword.current === keyword) {
            setResults(places.slice(0, 8))
            setError(null)
          }
        })
        .catch((cause: Error) => {
          if (latestKeyword.current === keyword) {
            setError(cause.message)
          }
        })
    }, 300)
    return () => clearTimeout(timer)
  }, [query, open, value])

  const select = (place: Place) => {
    onChange(place)
    setQuery(place.name)
    setOpen(false)
    setResults([])
  }

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="search">
        <input
          id={id}
          type="text"
          autoComplete="off"
          value={query}
          placeholder={placeholder ?? '장소, 주소, 역 이름'}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onChange={(event) => {
            setQuery(event.target.value)
            setOpen(true)
            if (value) {
              onChange(null)
            }
          }}
        />
        {open && results.length > 0 && (
          <ul className="search-results" role="listbox">
            {results.map((place) => (
              <li key={`${place.name}-${place.x}-${place.y}`}>
                <button
                  type="button"
                  role="option"
                  aria-selected={false}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => select(place)}
                >
                  <strong>{place.name}</strong>
                  {place.address && <small>{place.address}</small>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {value?.address && <small className="hint">{value.address}</small>}
      {error && <small className="hint hint-error">{error}</small>}
    </div>
  )
}

function parseLatLng(text: string): { x: number; y: number } | null {
  const parts = text.split(',').map((part) => Number(part.trim()))
  if (parts.length !== 2 || !parts.every(Number.isFinite)) {
    return null
  }
  const [lat, lng] = parts as [number, number]
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
    return null
  }
  return { x: lng, y: lat }
}

function ManualPlaceInput({ id, label, value, onChange, placeholder }: Props) {
  const [text, setText] = useState(value ? `${value.y}, ${value.x}` : '')

  useEffect(() => {
    if (value) {
      setText(`${value.y}, ${value.x}`)
    }
  }, [value])

  const handleChange = (next: string) => {
    setText(next)
    const parsed = parseLatLng(next)
    onChange(parsed ? { name: next.trim(), ...parsed } : null)
  }

  const invalid = text.trim().length > 0 && !parseLatLng(text)

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={text}
        placeholder={placeholder ?? '위도, 경도  예: 37.4979, 127.0276'}
        aria-invalid={invalid}
        onChange={(event) => handleChange(event.target.value)}
      />
      {value && value.name !== text.trim() && <small className="hint">{value.name}</small>}
      {invalid && <small className="hint hint-error">"위도, 경도" 형식으로 입력해 주세요</small>}
    </div>
  )
}
