// Vite 配置：接入 Tailwind，并保持独立预览工程可直接部署。
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [tailwindcss()],
  build: {
    rollupOptions: {
      input: {
        app: "index.html",
      },
    },
  },
});
