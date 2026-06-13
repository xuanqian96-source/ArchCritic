// Vite 配置：接入 Tailwind，并保持独立预览工程可直接部署。
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    watch: {
      // 项目在 WSL 的 /mnt/e Windows 挂载盘上，默认文件事件不稳定，使用轮询保证热更新可靠。
      usePolling: true,
      interval: 200,
    },
  },
  build: {
    rollupOptions: {
      input: {
        app: "index.html",
      },
    },
  },
});
