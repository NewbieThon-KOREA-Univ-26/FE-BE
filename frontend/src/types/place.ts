import type { Coordinate } from './api'

/** 사용자가 고른 출발지·도착지. 이름은 화면 표시용이고 백엔드에는 좌표만 보냅니다. */
export interface Place extends Coordinate {
  name: string
  address?: string
}

/** 두 장소가 같은 좌표인지. 사용자 흐름 문서의 "출발지와 도착지가 같음 → 입력 단계에서 막기"에 씁니다. */
export function isSamePlace(a: Coordinate, b: Coordinate): boolean {
  return a.x === b.x && a.y === b.y
}
