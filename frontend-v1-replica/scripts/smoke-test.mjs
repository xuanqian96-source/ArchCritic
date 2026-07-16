/* 本文件检查 React 复刻页面、关键流程和部署入口是否完整。 */
import { access, readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const routes = ["landing", "auth", "dashboard", "create", "info", "upload", "agents", "confirm", "processing", "report", "history"];

// 检查源码中是否包含关键内容。
function include(source, content, message) {
  if (!source.includes(content)) throw new Error(message);
}

// 执行全部基础检查。
async function test() {
  await access(join(root, "index.html"));
  await access(join(root, "src", "main.tsx"));
  await access(join(root, "src", "styles.css"));
  const app = await readFile(join(root, "src", "App.tsx"), "utf8");
  const flow = await Promise.all([
    "flowSetup.tsx",
    "flowDrawings.tsx",
    "flowReview.tsx",
  ].map((file) => readFile(join(root, "src", "pages", file), "utf8"))).then((parts) => parts.join("\n"));
  const publicPages = await readFile(join(root, "src", "pagesPublic.tsx"), "utf8");
  const results = await Promise.all([
    "reportPage.tsx",
    "historyPage.tsx",
  ].map((file) => readFile(join(root, "src", "pages", file), "utf8"))).then((parts) => parts.join("\n"));
  const workspace = await readFile(join(root, "src", "state", "workspace.tsx"), "utf8");
  routes.forEach((route) => include(app, `${route}:`, `${route} 页面路由缺失`));
  include(publicPages, "/homepage-cn/archcritic-homepage-cn-figma-dark.html", "官网入口缺失");
  include(flow, "选择新建评图方式", "新建评图弹窗缺失");
  include(flow, "上传设计图纸", "上传页缺失");
  include(results, "历史版本对比", "历史版本页面缺失");
  include(workspace, "startEvaluation", "流式评图连接缺失");
  include(workspace, "uploadTaskbook", "任务书上传连接缺失");
  include(workspace, "inheritProject", "项目继承连接缺失");
  include(workspace, "sendQuestion", "报告追问连接缺失");
  include(workspace, "pauseEvaluation", "暂停评图连接缺失");
  console.log(`基础检查通过：${routes.length + 7}/${routes.length + 7}`);
}

test().catch((error) => {
  console.error("基础检查失败：", error.message);
  process.exitCode = 1;
});
