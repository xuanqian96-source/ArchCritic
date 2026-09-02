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
  const appStyles = await readFile(join(root, "src", "styles.css"), "utf8");
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
  const reportStyles = await readFile(join(root, "src", "styles", "report.css"), "utf8");
  const reportAssistant = await readFile(join(root, "src", "pages", "reportAssistant.tsx"), "utf8");
  const reportShared = await readFile(join(root, "src", "pages", "reportShared.tsx"), "utf8");
  const reportKnowledgeCard = await readFile(join(root, "src", "pages", "reportKnowledgeCard.tsx"), "utf8");
  const reportApi = await readFile(join(root, "src", "api", "reports.ts"), "utf8");
  const baseComponents = await readFile(join(root, "src", "components", "baseComponents.tsx"), "utf8");
  const helpComponents = await readFile(join(root, "src", "components", "helpComponents.tsx"), "utf8");
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
  include(flow, "taskbookErrorTitle(error)", "任务书上传错误仍被固定显示为项目重名");
  include(flow, "line-clamp-2 overflow-hidden leading-[18px]", "任务书摘要没有限制在文件卡片内");
  include(workspace, "inheritProject", "项目继承连接缺失");
  include(workspace, "sendQuestion", "报告追问连接缺失");
  include(reportAssistant, "图纸复核", "报告助手缺少图纸复核工具");
  include(reportAssistant, "knowledge_recommendation", "报告助手缺少知识推荐工具");
  include(reportAssistant, 'alt="AI 辅助助手"', "报告对话缺少助手头像");
  include(reportAssistant, '{canPause ? "暂停" : "发送"}', "报告助手没有使用中文暂停按钮");
  include(reportAssistant, "onPointerDown={startDrag}", "报告助手入口不支持拖动");
  include(reportAssistant, "saveReportKnowledgeContext", "报告知识推荐没有携带整组推荐上下文");
  include(reportAssistant, "syncReportQuestion", "报告助手输入框没有清理空行节点");
  include(reportAssistant, "contentEditable suppressContentEditableWarning", "报告助手工作时仍禁止输入文字");
  include(reportAssistant, "您的设计反馈助手", "报告助手标题没有明确设计反馈用途");
  include(results, "FeedbackPanel", "报告右侧没有改为反馈要点面板");
  include(results, "buildReportSubScores(selected)", "评分维度缺少四项具体小分");
  if (results.includes(">具体小分<")) throw new Error("评分维度仍显示多余的具体小分标题");
  include(results, 'top-[252px] grid h-[176px]', "下方小分说明区域没有使用标题释放后的高度");
  include(results, 'className="report-sub-score-copy report-hover-scroll"', "小分说明不支持区域内滚动");
  include(results, "splitReadableParagraphs(item.reason)", "小分说明没有按自然段改善可读性");
  if (results.includes("pr-2 pb-16")) throw new Error("反馈要点列表底部仍保留多余空白");
  include(reportShared, "report-hover-scroll-on-dark", "评分维度摘要没有使用悬停滚动条");
  include(results, "getReferenceDisplay(referenceId, references)", "反馈要点没有优先显示知识库真实编号");
  include(reportShared, "MAX_REFERENCE_LINKS = 3", "旧报告自动补充知识关联的三条上限被意外改变");
  include(reportShared, "ReportKnowledgeContent", "报告关联知识卡没有展示完整正文");
  include(reportKnowledgeCard, "getKnowledgeDetail(itemId)", "报告关联知识卡没有读取知识库完整详情");
  include(reportKnowledgeCard, "detail?.content", "报告关联知识卡仍优先使用摘要快照");
  if (reportShared.includes(">在知识库查看<")) throw new Error("报告知识卡仍保留二次跳转按钮");
  if (reportShared.includes(".slice(0, 14)") || reportShared.includes("image_urls.slice(0, 6)")) throw new Error("报告知识卡正文或图片仍被缩略截断");
  include(reportApi, "report/export?format=pdf", "下载报告按钮没有请求真实 PDF");
  include(reportApi, "URL.createObjectURL", "报告 PDF 没有在当前页安全下载");
  if (reportApi.includes("window.location.href")) throw new Error("报告下载失败仍会跳离当前页面");
  include(reportApi, "/chat/stream", "报告助手没有使用流式回答接口");
  include(workspace, "streamChat(submissionId", "工作区没有持续接收报告回答流");
  include(workspace, "mergePersistedChatMessages", "报告消息轮询仍可能覆盖刚发送的问题");
  include(results, "window.setTimeout(refreshPendingAnswer, 2000)", "报告消息轮询没有等待后端先保存用户问题");
  include(knowledge, "返回报告界面", "报告推荐知识页缺少返回报告入口");
  include(knowledge, 'backLabel={assistantResult ? "返回推荐总览"', "推荐卡详情没有返回推荐总览");
  include(knowledge, "hideEmpty={Boolean(assistantResult)}", "推荐结果仍会显示数量为零的类型");
  include(knowledge, "assistantResult ? undefined : onQuiz", "推荐结果仍显示知识测试入口");
  include(knowledge, "<ReportAssistant", "报告推荐知识页没有保留原报告助手");
  include(baseComponents, 'className="fixed inset-0 z-[1000]', "通用提示卡遮罩没有覆盖完整视口");
  include(baseComponents, "createPortal", "通用提示卡没有挂到页面最外层");
  include(helpComponents, "<AppPromptOverlay onClose={onCancel}>", "退出登录提示没有使用统一全屏遮罩");
  if (results.includes("openDimensionDetail")) throw new Error("评分维度仍保留重复的查看详情入口");
  include(reportStyles, ".report-sub-score-card", "报告具体小分卡片样式缺失");
  include(reportStyles, "background: transparent", "报告具体小分仍使用嵌套灰色卡片");
  include(reportStyles, ".report-feedback-meta", "反馈编号与详情入口没有压缩到同一行");
  include(reportStyles, ".report-hover-scroll:hover", "评分说明滚动条没有设置为悬停显示");
  include(reportStyles, "font-size: 10px; line-height: 20px", "小分正文没有使用 10px 字号");
  if (reportStyles.includes("scrollbar-gutter: stable")) throw new Error("隐藏滚动条仍占用小分文本宽度");
  include(reportStyles, "overflow-y: overlay", "小分滚动条仍会挤压正文宽度");
  include(reportStyles, "scrollbar-color: transparent transparent;\n  scrollbar-width: thin", "小分滚动条显隐仍会改变正文宽度");
  if (appStyles.includes("min-height: 224px")) throw new Error("提示卡仍被固定为多余高度");
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
  include(knowledgeAssistant, "streamKnowledgeAssistantMessage", "知识库助手没有调用真实流式后端接口");
  include(knowledgeAssistant, "requestControllerRef", "知识库助手缺少请求取消能力");
  include(knowledgeAssistant, "knowledge-assistant-editor", "知识库助手输入框没有改为自适应编辑区");
  include(knowledgeAssistant, "knowledge-assistant-inline-tool", "知识助手工具没有跟随文字行内显示");
  include(knowledgeAssistant, "CONVERSATION_SCROLL_KEY", "知识助手没有保存或恢复会话滚动位置");
  include(knowledgeAssistant, 'setMessages((current) => [...current, { role: "user", content, tool: submittedTool }])', "知识助手没有让工具标签随用户消息进入对话");
  include(knowledge, "knowledge-assistant-result-banner", "AI 推荐结果状态栏缺失");
  include(knowledge, "返回原总览", "AI 推荐结果缺少返回原总览入口");
  include(knowledge, "部分内容可能存在遗漏或偏差，请留意核对", "AI 推荐缺少精简的内容提示");
  if (knowledge.includes("recommendation.matched_fields")) throw new Error("AI 推荐卡仍显示不准确的紫色关键词");
  if (knowledge.includes("待专业复核")) throw new Error("AI 推荐仍显示内部流程状态");
  include(knowledgeApi, "/api/knowledge/assistant/chat", "知识库助手接口地址缺失");
  include(sidebar, '["dashboard", "create", "knowledge"]', "知识库页面仍会选中项目");
  include(sidebar, "h-[52px] w-[204px]", "侧栏账户样式没有恢复");
  console.log(`基础检查通过：${routes.length + 102}/${routes.length + 102}`);
}

test().catch((error) => {
  console.error("基础检查失败：", error.message);
  process.exitCode = 1;
});
