// 复用首页头部安装的百度统计，记录固定页面名称，不发送账户和项目内容。

declare global {
  interface Window { _hmt?: unknown[][]; __archcriticAnalyticsInstalled?: boolean }
}

let started = false;
let lastPage = "";
const pageNames = new Set(["landing", "auth", "dashboard", "create", "info", "upload", "agents", "confirm", "processing", "report", "history", "knowledge"]);

// 只发送白名单中的页面名称，不把查询参数或自定义 hash 交给统计平台。
function trackPage(): void {
  const route = window.location.hash.replace(/^#\//, "");
  const page = pageNames.has(route) ? `/${route}` : "/landing";
  if (lastPage === page) return;
  lastPage = page;
  window._hmt?.push(["_trackPageview", page]);
}

// 正式网站启动一次；本地开发和嵌入首页不重复记录访问。
export function startAnalytics(): void {
  if (started || import.meta.env.DEV || !window.__archcriticAnalyticsInstalled) return;
  started = true;
  trackPage();
  window.addEventListener("hashchange", trackPage);
}
