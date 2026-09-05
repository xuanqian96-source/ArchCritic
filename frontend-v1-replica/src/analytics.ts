// 从后端读取百度统计标识，记录固定页面名称，不发送账户和项目内容。
import { requestJson } from "./api/client";

declare global {
  interface Window { _hmt?: unknown[][] }
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
export async function startAnalytics(): Promise<void> {
  if (started || import.meta.env.DEV || window.top !== window.self) return;
  started = true;
  try {
    const config = await requestJson<{ baidu_tongji_site_id: string }>("/api/site/config");
    if (!/^[a-f0-9]{32}$/i.test(config.baidu_tongji_site_id)) return;
    window._hmt = window._hmt || [];
    window._hmt.push(["_setAutoPageview", false]);
    const script = document.createElement("script");
    script.async = true;
    script.src = `https://hm.baidu.com/hm.js?${config.baidu_tongji_site_id}`;
    script.onerror = () => console.warn("访问统计暂不可用。");
    document.head.appendChild(script);
    trackPage();
    window.addEventListener("hashchange", trackPage);
  } catch {
    console.warn("访问统计配置暂不可用。");
  }
}
