import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],

  server: {
    port: 5173,
    strictPort: true,

    allowedHosts: ['.app.github.dev'],

    // 개발 중에는 /api 요청을 로컬 백엔드로 넘겨 CORS 없이 같은 출처처럼 씁니다.
    // 배포에서는 vercel.json 이 /api/* 를 백엔드 서비스로 보냅니다.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
