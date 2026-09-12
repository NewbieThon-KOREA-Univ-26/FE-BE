/** 1400 → "1,400원" */
export function formatWon(amount: number): string {
  return `${amount.toLocaleString('ko-KR')}원`
}

/** 16 → "16분", 75 → "1시간 15분". 312.23 처럼 소수로 와도 분 단위로 반올림합니다. */
export function formatMinutes(minutes: number): string {
  const total = Math.max(0, Math.round(minutes))
  if (total < 60) {
    return `${total}분`
  }
  const hours = Math.floor(total / 60)
  const rest = total % 60
  return rest === 0 ? `${hours}시간` : `${hours}시간 ${rest}분`
}

/** 320 → "320m", 1180 → "1.2km" */
export function formatDistance(meters: number): string {
  if (meters < 1000) {
    return `${Math.round(meters)}m`
  }
  return `${(meters / 1000).toFixed(1)}km`
}
