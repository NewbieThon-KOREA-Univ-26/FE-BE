import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 개발 중에는 /api 요청을 로컬 FastAPI 서버로 넘겨서 CORS 문제를 피합니다.
    // 배포 환경에서는 VITE_API_BASE_URL 로 백엔드 주소를 직접 지정합니다.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
