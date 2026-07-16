// 流程共享配置：统一阶段 Agent、表单校验、步骤外壳和首页提示。
import { useEffect, type PropsWithChildren } from "react";
import type { PageProps, Route } from "../App";
import { PageTitle, Sidebar, Steps } from "../components";
import { rememberSubmissionRoute } from "../state/flowRoutes";
import { useWorkspace } from "../state/workspace";
import type { Attachment, DrawingFile } from "../types/api";

function floorText(floor: number): string {
  return ["零", "一", "二", "三", "四", "五", "六", "七"][floor] ?? String(floor);
}

export interface AgentCardSpec {
  type: string;
  name: string;
  display: string;
  desc: string;
  cardDesc: string;
  image: string;
}
export const agentCards: AgentCardSpec[] = [
  { type: "site_agent", name: "场地 Agent", display: "场地", desc: "分析建筑与城市、场地和环境的关系", cardDesc: "分析基地、交通、城市界面与环境响应。", image: "/assets/v1/agent-site.png" },
  { type: "function_agent", name: "功能与流线 Agent", display: "功能与流线", desc: "检查空间组织、使用路径和流线关系", cardDesc: "检查功能组织、动线效率和公共性。", image: "/assets/v1/agent-flow.png" },
  { type: "form_agent", name: "几何形式 Agent", display: "几何形式", desc: "识别体量、秩序、比例和空间形式", cardDesc: "评价体量、立面逻辑和空间表达。", image: "/assets/v1/agent-form.png" },
  { type: "structure_agent", name: "结构 Agent", display: "结构", desc: "核对结构逻辑、跨度和构造合理性", cardDesc: "发现影响落地的结构和尺度问题。", image: "/assets/v1/agent-structure.png" },
  { type: "concept_agent", name: "设计概念 Agent", display: "设计概念", desc: "评估概念立意、空间叙事和方案生成逻辑", cardDesc: "检查概念是否清晰，并能转化为空间策略。", image: "/assets/v1/agent-concept.png" },
  { type: "drawing_agent", name: "图面表达 Agent", display: "图面表达", desc: "检查图纸完整度、表达清晰度和信息层级", cardDesc: "核对图纸表达、标注、排版和阅读效率。", image: "/assets/v1/agent-drawing.png" },
  { type: "review_agent", name: "综合评审 Agent", display: "综合评审", desc: "汇总各专项判断，生成最终反馈报告", cardDesc: "整合专项结论，形成总分、问题和修改建议。", image: "/assets/v1/agent-review.png" },
];
export const agentByType = new Map(agentCards.map((agent) => [agent.type, agent]));
export const fixedFlowImageSources = [...new Set(agentCards.map((agent) => agent.image))];
export let fixedFlowImagesPreloaded = false;

// 提前加载固定图片，避免进入 Agent 页面时才看到图片慢慢出现。
export function preloadFixedFlowImages() {
  if (fixedFlowImagesPreloaded || typeof window === "undefined") return;
  fixedFlowImagesPreloaded = true;
  fixedFlowImageSources.forEach((src) => {
    const image = new Image();
    image.decoding = "async";
    image.src = src;
  });
}

export const stageAgentTypes: Record<string, string[]> = {
  概念阶段: ["site_agent", "form_agent", "concept_agent", "review_agent"],
  方案阶段: ["function_agent", "site_agent", "form_agent", "structure_agent", "review_agent"],
  图纸阶段: ["drawing_agent", "function_agent", "site_agent", "form_agent", "structure_agent", "review_agent"],
};
export function getStageAgentTypes(stage: string) {
  return stageAgentTypes[stage] ?? stageAgentTypes["方案阶段"];
}
export function getAgentSpecs(types: string[]) {
  return types.map((type) => agentByType.get(type)).filter(Boolean) as AgentCardSpec[];
}
export const buildingTypeOptions = ["博物馆建筑", "学校建筑", "酒店建筑", "社区活动中心", "办公建筑", "居住建筑", "商业建筑"];
export const gradeOptions = ["大一", "大二", "大三", "大四", "大五"];
export const modelOptions = [
  { value: "dashscope|qwen3.6-plus", label: "qwen3.6-plus" },
  { value: "gemini|gemini-2.5-flash", label: "gemini-2.5-flash" },
];
export const drawingTypeOptions = [
  { value: "site", label: "总平面图" },
  { value: "plan", label: "首层平面图" },
  { value: "floor-plan", label: "非首层平面图" },
  { value: "section", label: "剖面图" },
  { value: "elevation", label: "立面图" },
  { value: "analysis", label: "分析图" },
  { value: "render", label: "效果图" },
];
export const floorPlanOptions = Array.from({ length: 6 }, (_, index) => {
  const floor = index + 2;
  return { value: `plan-${floor}`, label: `${floorText(floor)}层平面图` };
});
export interface PendingUpload {
  id: string;
  name: string;
}
export interface ReplacingUpload {
  drawingId: number | null;
  name: string;
}
export interface DrawingPreviewTarget {
  src: string;
  alt: string;
  pdf: boolean;
}

// 在本地记录草稿当前停留步骤，方便从首页查看详情时回到原页面。
export function useRememberFlowRoute(route: Route) {
  const { submission } = useWorkspace();
  useEffect(() => {
    rememberSubmissionRoute(submission?.id, route);
  }, [route, submission?.id]);
}

// 保存草稿后立刻记录当前步骤，避免用户返回首页时再次触发未保存提醒。
export async function saveDraftAtRoute(saveDraft: () => Promise<{ id: number }>, route: Route) {
  const savedSubmission = await saveDraft();
  rememberSubmissionRoute(savedSubmission.id, route);
}

// 切页后在后台保存草稿，不阻塞用户进入下一页。
export function saveDraftAtRouteInBackground(saveDraft: () => Promise<{ id: number }>, route: Route, setNotice: (message: string) => void) {
  void saveDraftAtRoute(saveDraft, route).catch(() => {
    setNotice("后台保存失败，请稍后手动保存草稿。");
  });
}

// 把缺失字段转换成统一的弹窗提示。
export function buildMissingMessage(items: string[]) {
  return `请先补充完整以下内容：${items.join("、")}。`;
}

// 把确认页长文本压成连续段落，避免展示态和编辑态换行不一致。
export function collapseConfirmText(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

// 校验项目信息页进入下一步前必须填写的内容。
export function validateProjectInfoStep(draft: { name: string; buildingType: string; grade: string; siteLocation: string; description: string }, attachments: Attachment[]) {
  const missing: string[] = [];
  if (!draft.name.trim()) missing.push("项目名称");
  if (!draft.siteLocation.trim()) missing.push("基地位置");
  if (!draft.buildingType.trim()) missing.push("建筑类型");
  if (!draft.grade.trim()) missing.push("设计年级");
  if (!draft.description.trim()) missing.push("设计说明");
  if (!attachments.length) missing.push("任务书");
  else if (!attachments.some((item) => item.extraction_status === "ready")) missing.push("可读取文字的任务书");
  if (missing.length) throw new Error(buildMissingMessage(missing));
}

// 避免空白新建时复用已有项目名称，防止报告被归到旧项目组。
export function validateUniqueProjectName(draftName: string, projects: Array<{ id: number; name: string }>, currentProjectId?: number | null) {
  const normalizedName = draftName.trim().replace(/\s+/g, " ").toLowerCase();
  if (!normalizedName || currentProjectId) return;
  const duplicated = projects.some((item) => item.name.trim().replace(/\s+/g, " ").toLowerCase() === normalizedName);
  if (duplicated) throw new Error("这个项目名称已经被使用了。为了避免报告归到已有项目下，请换一个项目名称。");
}

// 校验阶段和 Agent 页进入下一步前必须选择的内容。
export function validateAgentStep(draft: { designStage: string; enabledAgents: string[] }) {
  const missing: string[] = [];
  if (!draft.designStage.trim()) missing.push("项目阶段");
  if (!draft.enabledAgents.some((agent) => agent !== "review_agent")) missing.push("至少一个专项 AI Agent");
  if (missing.length) throw new Error(buildMissingMessage(missing));
}

// 校验图纸页进入下一步前必须上传图纸。
export function validateUploadStep(drawings: DrawingFile[]) {
  if (!drawings.length) throw new Error(buildMissingMessage(["设计图纸"]));
}

// 渲染带侧栏的流程页面框架。
export function FlowShell({ children, title, subtitle, current, go, projectName }: PropsWithChildren<{ title: string; subtitle: string; current?: 1 | 2 | 3 | 4; projectName?: string } & PageProps>) {
  useEffect(() => {
    preloadFixedFlowImages();
  }, []);
  return (
    <div className="relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} creating projectName={projectName} />
      <div className="flow-page-motion">
        <PageTitle title={title} subtitle={subtitle} />
        {current && <Steps current={current} />}
        {children}
      </div>
    </div>
  );
}

export const announcements = [
  { title: "评图报告现已支持知识库追溯", detail: "评图完成后，可在报告页查看每条建议关联的知识库依据。点击“查看”即可打开对应卡片，核对规范、案例或常见问题说明。" },
  { title: "三个阶段均支持多 Agent 协同评审", detail: "系统会按概念、方案或图纸阶段调用对应专项 Agent，再汇总为完整报告。等待页会同步显示真实执行进度。" },
  { title: "历史版本对比功能已开放", detail: "每次完成评图后，系统会保存当前报告。你可以在报告页进入“历史版本对比”，查看总分和各维度变化。" },
  { title: "图纸上传规则说明", detail: "当前支持 PNG、JPG、WEBP 和 GIF 图片。请优先上传清晰的平面图、分析图和效果图，以便系统获得更准确的判断。" },
  { title: "报告追问功能已接入", detail: "报告生成后，可以在右侧对话区继续追问扣分原因、定位图纸问题，或让系统生成下一轮优化动作。" },
  { title: "项目版本归档规则更新", detail: "同名项目会按提交时间自动归档为 V1、V2 等版本，便于在侧栏中快速回看每次评图结果。" },
  { title: "暂停评图入口已开放", detail: "等待评图过程中可点击暂停评图，系统会保留当前项目信息和已上传图纸，方便之后继续提交。" },
  { title: "任务书会参与评分", detail: "系统会读取任务书正文，根据课程要求和年级调整各专项评分占比，并随报告保存本次评分依据。" },
];

export const guideItems = [
  { title: "操作指引：完成第一次 AI 评图", detail: "点击“+ 新建评图”，填写项目信息，选择项目阶段与 Agent，上传图纸并确认提交。报告生成后，可继续查看问题详情和知识库依据。" },
  { title: "常见问题：为什么报告仍在生成？", detail: "真实模型需要依次读取图纸并完成专项分析。请在等待页查看进度；如果暂时不需要继续，可点击“暂停评图”。" },
  { title: "常见问题：如何继续下一轮修改？", detail: "可以从已有项目继承资料，复用项目信息、最近一次图纸和 Agent 设置，再上传调整后的图纸继续评图。" },
  { title: "操作指引：查看历史版本", detail: "在报告页点击历史版本对比，可以查看同一项目的多次提交，比较总分和各维度变化。" },
  { title: "常见问题：知识库依据从哪里来？", detail: "系统会根据项目类型、阶段、图纸内容和设计说明，从本地知识库中筛选最相关的规范、案例和常见问题。" },
  { title: "操作指引：从旧项目继续评图", detail: "新建评图时可以选择继承已有项目，复用基础资料和最近一次图纸，再上传修改后的版本。" },
  { title: "常见问题：草稿项目如何处理？", detail: "未提交评图的项目会显示为草稿，点击项目后可继续补充信息、上传图纸并确认提交。" },
];

export interface InformationItem {
  title: string;
  detail: string;
}
