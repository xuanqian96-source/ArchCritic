/* 本文件检查 Vite 开发服务是否已经返回最新源码中的关键标记。 */
const [, , markerArg, moduleArg] = process.argv;
const marker = markerArg || "text-[10px] font-extrabold";
const modulePath = moduleArg || "/src/pagesFlow.tsx";
const url = `http://127.0.0.1:4173${modulePath}?t=${Date.now()}`;

// 从 4173 获取开发服务返回的模块内容。
async function fetchServedModule() {
  const response = await fetch(url, {
    headers: {
      "Cache-Control": "no-cache",
      "Pragma": "no-cache",
    },
  });
  if (!response.ok) {
    throw new Error(`开发服务未正常响应：${response.status} ${response.statusText}`);
  }
  return response.text();
}

// 检查返回内容中是否包含指定标记。
async function verify() {
  const served = await fetchServedModule();
  if (!served.includes(marker)) {
    throw new Error(`4173 未返回目标标记：${marker}`);
  }
  console.log(`开发服务已更新：1/1，命中标记：${marker}`);
}

verify().catch((error) => {
  console.error("开发服务检查失败：", error.message);
  process.exitCode = 1;
});
