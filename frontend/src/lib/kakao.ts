import type { KakaoSdk } from '../types/kakao'
import type { Place } from '../types/place'

const APP_KEY = import.meta.env.VITE_KAKAO_MAP_KEY ?? ''

/** 카카오 키가 설정되어 있는지. 없으면 장소 검색·지도 대신 좌표 직접 입력으로 동작합니다. */
export const hasKakaoKey = APP_KEY.length > 0

let loading: Promise<KakaoSdk> | null = null

/**
 * 카카오 지도 SDK 를 한 번만 불러옵니다. services 라이브러리(장소 검색)를 함께 로드합니다.
 * autoload=false 로 두고 kakao.maps.load 콜백 안에서 resolve 하므로,
 * 이 프로미스가 끝난 뒤에는 kakao.maps.* 를 바로 써도 됩니다.
 */
export function loadKakaoSdk(): Promise<KakaoSdk> {
  if (!hasKakaoKey) {
    return Promise.reject(new Error('VITE_KAKAO_MAP_KEY 가 설정되지 않았습니다'))
  }
  if (window.kakao?.maps?.services) {
    return Promise.resolve(window.kakao)
  }
  if (loading) {
    return loading
  }

  loading = new Promise<KakaoSdk>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(APP_KEY)}&libraries=services&autoload=false`
    script.async = true
    script.onload = () => {
      const kakao = window.kakao
      if (!kakao) {
        loading = null
        reject(new Error('카카오 지도 SDK 를 불러왔지만 window.kakao 가 없습니다'))
        return
      }
      kakao.maps.load(() => resolve(kakao))
    }
    script.onerror = () => {
      loading = null
      script.remove()
      reject(new Error('카카오 지도 SDK 를 불러오지 못했습니다. 키와 등록된 도메인을 확인하세요'))
    }
    document.head.appendChild(script)
  })
  return loading
}

/** 키워드로 장소를 검색해 좌표가 포함된 Place 목록으로 돌려줍니다. (F1 출발지·도착지 입력) */
export async function searchPlaces(keyword: string): Promise<Place[]> {
  const kakao = await loadKakaoSdk()
  const { Places, Status } = kakao.maps.services

  return new Promise<Place[]>((resolve, reject) => {
    new Places().keywordSearch(keyword, (data, status) => {
      if (status === Status.OK) {
        resolve(
          data.map((item) => ({
            name: item.place_name,
            address: item.road_address_name || item.address_name,
            x: Number(item.x),
            y: Number(item.y),
          })),
        )
      } else if (status === Status.ZERO_RESULT) {
        resolve([])
      } else {
        reject(new Error('장소 검색에 실패했습니다'))
      }
    })
  })
}
