/**
 * 카카오 지도 SDK 중 이 프로젝트에서 쓰는 부분만 최소한으로 타이핑했습니다.
 * SDK 전체 타입이 필요해지면 kakao.maps.d.ts 같은 커뮤니티 타입으로 바꿔도 됩니다.
 */

export interface KakaoLatLng {
  getLat(): number
  getLng(): number
}

export interface KakaoLatLngBounds {
  extend(latlng: KakaoLatLng): void
}

export interface KakaoMap {
  getProjection(): {
    containerPointFromCoords(coords: KakaoLatLng): { x: number; y: number }
    coordsFromContainerPoint(point: { x: number; y: number }): KakaoLatLng
  }
  getCenter(): KakaoLatLng
  getLevel(): number
  jump(center: KakaoLatLng, level: number, options?: { animate: boolean | { duration: number } }): void
  setCenter(latlng: KakaoLatLng): void
  panBy(dx: number, dy: number): void
  setBounds(bounds: KakaoLatLngBounds, paddingTop?: number, paddingRight?: number, paddingBottom?: number, paddingLeft?: number): void
  setLevel(level: number): void
}

export interface KakaoMarker {
  setMap(map: KakaoMap | null): void
}

export interface KakaoPolyline {
  setMap(map: KakaoMap | null): void
}

export interface KakaoPolylineOptions {
  path: KakaoLatLng[]
  strokeWeight?: number
  strokeColor?: string
  strokeOpacity?: number
  strokeStyle?: 'solid' | 'shortdash' | 'dash' | 'dot' | 'longdash'
}

/** keywordSearch 결과 항목. x = 경도, y = 위도 (문자열로 옵니다). */
export interface KakaoPlaceResult {
  id: string
  place_name: string
  address_name: string
  road_address_name: string
  x: string
  y: string
}

export interface KakaoPlacesService {
  keywordSearch(
    keyword: string,
    callback: (data: KakaoPlaceResult[], status: string) => void,
  ): void
}

export interface KakaoSdk {
  maps: {
    Point: new (x: number, y: number) => { x: number; y: number }
    load(callback: () => void): void
    LatLng: new (lat: number, lng: number) => KakaoLatLng
    LatLngBounds: new () => KakaoLatLngBounds
    Map: new (container: HTMLElement, options: { center: KakaoLatLng; level: number }) => KakaoMap
    Marker: new (options: { position: KakaoLatLng; map?: KakaoMap }) => KakaoMarker
    Polyline: new (options: KakaoPolylineOptions) => KakaoPolyline
    services: {
      Status: { OK: string; ZERO_RESULT: string; ERROR: string }
      Places: new () => KakaoPlacesService
    }
  }
}

declare global {
  interface Window {
    kakao?: KakaoSdk
  }
}
