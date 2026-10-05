import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// 브라우저 개발 모드(Tauri 없이)에서는 dev_bridge.py(포트 8765)로 IPC를 프록시한다.
// Tauri 프로덕션 빌드에서는 이 프록시가 사용되지 않고 Rust invoke가 직접 동작한다.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  clearScreen: false,
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      "/sidecar": {
        target: "http://127.0.0.1:8765",
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/sidecar/, ""),
      },
    },
  },
  build: {
    target: "es2022",
    outDir: "dist",
    emptyOutDir: true,
  },
});
