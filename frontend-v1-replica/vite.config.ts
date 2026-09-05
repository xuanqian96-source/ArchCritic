// Vite 配置：接入 Tailwind，并保持独立预览工程可直接部署。
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import siteConfig from "./site.config.json";

// 构建时把官方加载代码放进首页源码，供百度检查器直接识别。
function baiduAnalyticsHead() {
  const siteId = siteConfig.baiduTongjiSiteId;
  if (siteId && !/^[a-f0-9]{32}$/i.test(siteId)) throw new Error("百度统计站点 ID 格式不正确。");
  return {
    name: "archcritic-baidu-analytics-head",
    apply: "build" as const,
    transformIndexHtml() {
      if (!siteId) return [];
      return [{
        tag: "script",
        attrs: { id: "archcritic-baidu-options" },
        injectTo: "head" as const,
        children: `
var _hmt = _hmt || [];
_hmt.push(["_setAutoPageview", false]);
window.__archcriticAnalyticsInstalled = window.top === window.self && ${JSON.stringify(siteConfig.analyticsHosts)}.includes(window.location.hostname) && window.location.protocol === "https:";`,
      }, {
        tag: "script",
        attrs: { id: "archcritic-baidu-analytics" },
        injectTo: "head" as const,
        children: `
var _hmt = _hmt || [];
(function() {
  var hm = document.createElement("script");
  hm.src = "https://hm.baidu.com/hm.js?${siteId}";
  var s = document.getElementsByTagName("script")[0];
  s.parentNode.insertBefore(hm, s);
})();`,
      }];
    },
  };
}

export default defineConfig({
  plugins: [tailwindcss(), baiduAnalyticsHead()],
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
