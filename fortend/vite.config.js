import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { port: 5173, watch: { ignored: ['**/backend/**', '**/.runtime/**'] } },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/echarts') || id.includes('node_modules/zrender'))
            return 'charts'
          if (id.includes('node_modules/ant-design') || id.includes('node_modules/@ant-design'))
            return 'antd'
        },
      },
    },
  },
})
