/**
 * "모바일 레이아웃"의 단 하나의 정의. CSS 의 @media 와 반드시 같아야 합니다 (index.css 참고).
 *
 * 폭이 좁아도 폰을 가로로 눕힌 상태(높이 520px 이하)는 제외합니다 — 그때 모바일 규칙을 쓰면
 * 검색창과 결과 시트가 세로 공간을 다 차지해 지도가 완전히 가려집니다. 대신 데스크톱처럼
 * 왼쪽 패널 + 오른쪽 지도로 보여 줍니다.
 */
export const MOBILE_QUERY = '(max-width: 860px) and (not ((max-height: 520px) and (orientation: landscape)))'

export function isMobileLayout(): boolean {
  return window.matchMedia(MOBILE_QUERY).matches
}
