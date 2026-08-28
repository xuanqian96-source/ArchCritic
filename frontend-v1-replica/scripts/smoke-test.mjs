/* 本文件检查 React 复刻页面、关键流程和部署入口是否完整。 */
import { access, readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const routes = ["landing", "auth", "dashboard", "create", "info", "upload", "agents", "confirm", "processing", "report", "history", "knowledge"];

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
  const knowledge = await readFile(join(root, "src", "pages", "knowledgePage.tsx"), "utf8");
  const knowledgeStyles = await readFile(join(root, "src", "styles", "knowledge.css"), "utf8");
  const knowledgeAssistant = await readFile(join(root, "src", "pages", "knowledgeAssistant.tsx"), "utf8");
  const knowledgeApi = await readFile(join(root, "src", "api", "knowledge.ts"), "utf8");
  const sidebar = await readFile(join(root, "src", "components", "sidebar.tsx"), "utf8");
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
  include(knowledge, "getKnowledgeLibrary", "知识库目录接口缺失");
  include(knowledge, "knowledge-relation-row", "知识库正文关联跳转缺失");
  include(knowledge, "返回知识库总览", "知识库总览与深度阅读切换缺失");
  include(knowledge, 'tab !== "all"', "知识库全部状态仍会显示二级分类");
  include(knowledge, "knowledge-overview-case-section", "知识库全部状态缺少上方案例区");
  include(knowledge, "knowledge-overview-knowledge-section", "知识库全部状态缺少下方知识卡区");
  include(knowledge, "knowledge-category-scroll", "知识库次级分类没有独立滚动区");
  include(knowledge, "sortLibraryItems", "知识库卡片没有按类型与层级稳定排序");
  include(knowledge, "SEARCH_HISTORY_KEY", "知识库最近搜索记录缺失");
  include(knowledge, "slice(0, 3)", "知识库搜索历史没有限制为三条");
  include(knowledge, "knowledge-search-submit", "知识库搜索按钮缺失");
  include(knowledge, "knowledge-search-clear", "知识库搜索清空按钮缺失");
  include(knowledge, "if (!query)", "知识库空搜索回车没有恢复总览");
  include(knowledge, "openItem(itemId, activeOverviewQuery)", "知识库搜索结果进入详情时没有保留搜索条件");
  include(knowledge, 'onClear={() => onQuery("")}', "知识库清空搜索时仍会重置主标签");
  include(knowledge, "catalogList.scrollTop", "知识库详情目录没有自动定位当前卡片");
  include(knowledge, "clearDetailSearch", "知识库详情清空搜索没有同步总览状态");
  include(knowledge, "overviewPositionRef", "知识库总览没有保存返回位置");
  include(knowledge, "restorePosition.itemOffset", "知识库总览没有按原卡片位置恢复");
  include(knowledge, "resultCategoryNames", "知识库搜索结果没有过滤零数量分类");
  include(knowledge, 'categories.length > 0', "知识库无分类结果时仍会显示分类栏");
  include(knowledge, "showCategories={false}", "知识库详情仍会显示分类栏");
  include(knowledge, "countKinds", "知识库搜索结果计数没有同步更新");
  include(knowledgeStyles, "font-size: 34px !important", "知识库标题没有沿用统一页面标题字号");
  include(knowledgeStyles, "knowledge-level-master", "知识卡分级紫色缺失");
  include(knowledgeAssistant, "knowledge-assistant-toggle", "知识库 AI 悬浮助手缺失");
  include(knowledgeAssistant, "knowledge-assistant-overlay", "知识库助手遮罩缺失");
  include(knowledgeAssistant, "!open &&", "知识库助手打开后入口仍然显示");
  include(knowledgeAssistant, "is-tracking", "知识库助手没有鼠标方向跟随");
  include(knowledgeAssistant, "scheduleBlink", "知识库助手没有自然眨眼");
  include(knowledgeStyles, "knowledge-assistant-eye-idle", "知识库助手眼睛没有默认游动动画");
  include(knowledgeAssistant, "您的建筑知识助手", "知识库助手标题缺失");
  include(knowledgeAssistant, "TOOL_DEFINITIONS", "知识库助手内置工具栏缺失");
  include(knowledgeAssistant, "sendKnowledgeAssistantMessage", "知识库助手没有调用真实后端接口");
  include(knowledgeAssistant, "requestControllerRef", "知识库助手缺少请求取消能力");
  include(knowledgeAssistant, "knowledge-assistant-editor", "知识库助手输入框没有改为自适应编辑区");
  include(knowledgeAssistant, "knowledge-assistant-inline-tool", "知识助手工具没有跟随文字行内显示");
  include(knowledgeAssistant, 'setMessages((current) => [...current, { role: "user", content }])', "知识助手没有在请求开始时显示用户消息");
  include(knowledge, "knowledge-assistant-result-banner", "AI 推荐结果状态栏缺失");
  include(knowledge, "返回原总览", "AI 推荐结果缺少返回原总览入口");
  include(knowledge, "待专业复核", "AI 推荐没有显示内容复核状态");
  include(knowledgeApi, "/api/knowledge/assistant/chat", "知识库助手接口地址缺失");
  include(sidebar, '["dashboard", "create", "knowledge"]', "知识库页面仍会选中项目");
  include(sidebar, "h-[52px] w-[204px]", "侧栏账户样式没有恢复");
  console.log(`基础检查通过：${routes.length + 52}/${routes.length + 52}`);
}

test().catch((error) => {
  console.error("基础检查失败：", error.message);
  process.exitCode = 1;
});
