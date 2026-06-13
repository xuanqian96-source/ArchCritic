// 流程页面：复刻项目首页、新建表单、上传图纸、Agent 选择、确认和等待页。
import { useEffect, useRef, useState, type ChangeEvent, type PropsWithChildren } from "react";
import type { PageProps, Route } from "./App";
import { apiUrl } from "./api/client";
import { Button, Card, FigmaScrollbar, FlowActions, FlowErrorCard, PageTitle, PlanThumb, Sidebar, Steps } from "./components";
import { readSubmissionRoute, rememberSubmissionRoute } from "./state/flowRoutes";
import { useProfile } from "./state/profile";
import { getCachedProjectGroups, getLatestVersion, loadProjectGroups, PINNED_PROJECTS_CHANGED_EVENT, readPinnedProjectIds, sortPinnedProjectGroups, type ProjectGroup, type ProjectVersion } from "./state/projectGroups";
import { useWorkspace } from "./state/workspace";
import type { Attachment, DrawingFile } from "./types/api";

const drawingNames = ["总平面图.pdf", "首层平面图.jpg", "二层平面图.jpg", "总平面图.pdf", "首层平面图.jpg", "二层平面图.jpg", "总平面图.pdf", "首层平面图.jpg", "二层平面图.jpg"];
interface AgentCardSpec {
  type: string;
  name: string;
  display: string;
  desc: string;
  cardDesc: string;
  image: string;
}
const agentCards: AgentCardSpec[] = [
  { type: "site_agent", name: "场地 Agent", display: "场地", desc: "分析建筑与城市、场地和环境的关系", cardDesc: "分析基地、交通、城市界面与环境响应。", image: "/assets/v1/agent-site.png" },
  { type: "function_agent", name: "功能与流线 Agent", display: "功能与流线", desc: "检查空间组织、使用路径和流线关系", cardDesc: "检查功能组织、动线效率和公共性。", image: "/assets/v1/agent-flow.png" },
  { type: "form_agent", name: "几何形式 Agent", display: "几何形式", desc: "识别体量、秩序、比例和空间形式", cardDesc: "评价体量、立面逻辑和空间表达。", image: "/assets/v1/agent-form.png" },
  { type: "structure_agent", name: "结构 Agent", display: "结构", desc: "核对结构逻辑、跨度和构造合理性", cardDesc: "发现影响落地的结构和尺度问题。", image: "/assets/v1/agent-structure.png" },
  { type: "concept_agent", name: "设计概念 Agent", display: "设计概念", desc: "评估概念立意、空间叙事和方案生成逻辑", cardDesc: "检查概念是否清晰，并能转化为空间策略。", image: "/assets/v1/agent-concept.png" },
  { type: "drawing_agent", name: "图面表达 Agent", display: "图面表达", desc: "检查图纸完整度、表达清晰度和信息层级", cardDesc: "核对图纸表达、标注、排版和阅读效率。", image: "/assets/v1/agent-drawing.png" },
  { type: "review_agent", name: "综合评审 Agent", display: "综合评审", desc: "汇总各专项判断，生成最终反馈报告", cardDesc: "整合专项结论，形成总分、问题和修改建议。", image: "/assets/v1/agent-review.png" },
];
const agentByType = new Map(agentCards.map((agent) => [agent.type, agent]));
const stageAgentTypes: Record<string, string[]> = {
  概念阶段: ["site_agent", "form_agent", "concept_agent", "review_agent"],
  方案阶段: ["function_agent", "site_agent", "form_agent", "structure_agent", "review_agent"],
  图纸阶段: ["drawing_agent", "function_agent", "site_agent", "form_agent", "structure_agent", "review_agent"],
};
function getStageAgentTypes(stage: string) {
  return stageAgentTypes[stage] ?? stageAgentTypes["方案阶段"];
}
function getAgentSpecs(types: string[]) {
  return types.map((type) => agentByType.get(type)).filter(Boolean) as AgentCardSpec[];
}
const buildingTypeOptions = ["博物馆建筑", "学校建筑", "酒店建筑", "社区活动中心", "办公建筑", "居住建筑", "商业建筑"];
const gradeOptions = ["大一", "大二", "大三", "大四", "大五"];
const modelOptions = [
  { value: "dashscope|qwen3.6-plus", label: "qwen3.6-plus" },
  { value: "gemini|gemini-2.5-flash", label: "gemini-2.5-flash" },
];
const drawingTypeOptions = [
  { value: "site", label: "总平面图" },
  { value: "plan", label: "首层平面图" },
  { value: "floor-plan", label: "非首层平面图" },
  { value: "section", label: "剖面图" },
  { value: "elevation", label: "立面图" },
  { value: "analysis", label: "分析图" },
  { value: "render", label: "效果图" },
];
const floorPlanOptions = Array.from({ length: 6 }, (_, index) => {
  const floor = index + 2;
  return { value: `plan-${floor}`, label: `${floorText(floor)}层平面图` };
});
interface PendingUpload {
  id: string;
  name: string;
}
interface ReplacingUpload {
  drawingId: number | null;
  name: string;
}

// 在本地记录草稿当前停留步骤，方便从首页查看详情时回到原页面。
function useRememberFlowRoute(route: Route) {
  const { submission } = useWorkspace();
  useEffect(() => {
    rememberSubmissionRoute(submission?.id, route);
  }, [route, submission?.id]);
}

// 保存草稿后立刻记录当前步骤，避免用户返回首页时再次触发未保存提醒。
async function saveDraftAtRoute(saveDraft: () => Promise<{ id: number }>, route: Route) {
  const savedSubmission = await saveDraft();
  rememberSubmissionRoute(savedSubmission.id, route);
}

// 把缺失字段转换成统一的弹窗提示。
function buildMissingMessage(items: string[]) {
  return `请先补充完整以下内容：${items.join("、")}。`;
}

// 把确认页长文本压成连续段落，避免展示态和编辑态换行不一致。
function collapseConfirmText(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

// 校验项目信息页进入下一步前必须填写的内容。
function validateProjectInfoStep(draft: { name: string; buildingType: string; grade: string; siteLocation: string; description: string }, attachments: Attachment[]) {
  const missing: string[] = [];
  if (!draft.name.trim()) missing.push("项目名称");
  if (!draft.siteLocation.trim()) missing.push("基地位置");
  if (!draft.buildingType.trim()) missing.push("建筑类型");
  if (!draft.grade.trim()) missing.push("设计年级");
  if (!draft.description.trim()) missing.push("设计说明");
  if (!attachments.length) missing.push("任务书");
  if (missing.length) throw new Error(buildMissingMessage(missing));
}

// 校验阶段和 Agent 页进入下一步前必须选择的内容。
function validateAgentStep(draft: { designStage: string; enabledAgents: string[] }) {
  const missing: string[] = [];
  if (!draft.designStage.trim()) missing.push("项目阶段");
  if (!draft.enabledAgents.length) missing.push("至少一个 AI Agent");
  if (missing.length) throw new Error(buildMissingMessage(missing));
}

// 校验图纸页进入下一步前必须上传图纸。
function validateUploadStep(drawings: DrawingFile[]) {
  if (!drawings.length) throw new Error(buildMissingMessage(["设计图纸"]));
}

// 渲染带侧栏的流程页面框架。
function FlowShell({ children, title, subtitle, current, go, projectName }: PropsWithChildren<{ title: string; subtitle: string; current?: 1 | 2 | 3 | 4; projectName?: string } & PageProps>) {
  return (
    <div className="relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} creating projectName={projectName} />
      <PageTitle title={title} subtitle={subtitle} />
      {current && <Steps current={current} />}
      {children}
    </div>
  );
}

const announcements = [
  { title: "评图报告现已支持知识库追溯", detail: "评图完成后，可在报告页查看每条建议关联的知识库依据。点击“查看”即可打开对应卡片，核对规范、案例或常见问题说明。" },
  { title: "方案阶段支持多 Agent 协同评审", detail: "方案阶段会由场地、功能与流线、几何形式和结构 Agent 依次分析，再由系统汇总为完整报告。等待页会同步显示当前进度。" },
  { title: "历史版本对比功能已开放", detail: "每次完成评图后，系统会保存当前报告。你可以在报告页进入“历史版本对比”，查看总分和各维度变化。" },
  { title: "图纸上传规则说明", detail: "当前支持 PNG、JPG、WEBP 和 GIF 图片。请优先上传清晰的平面图、分析图和效果图，以便系统获得更准确的判断。" },
  { title: "报告追问功能已接入", detail: "报告生成后，可以在右侧对话区继续追问扣分原因、定位图纸问题，或让系统生成下一轮优化动作。" },
  { title: "项目版本归档规则更新", detail: "同名项目会按提交时间自动归档为 V1、V2 等版本，便于在侧栏中快速回看每次评图结果。" },
  { title: "暂停评图入口已开放", detail: "等待评图过程中可点击暂停评图，系统会保留当前项目信息和已上传图纸，方便之后继续提交。" },
  { title: "任务书上传说明", detail: "新建评图时可上传任务书或课程要求文件，系统会把这些信息作为报告生成依据。" },
];

const guideItems = [
  { title: "操作指引：完成第一次 AI 评图", detail: "点击“+ 新建评图”，填写项目信息，选择项目阶段与 Agent，上传图纸并确认提交。报告生成后，可继续查看问题详情和知识库依据。" },
  { title: "常见问题：为什么报告仍在生成？", detail: "真实模型需要依次读取图纸并完成专项分析。请在等待页查看进度；如果暂时不需要继续，可点击“暂停评图”。" },
  { title: "常见问题：如何继续下一轮修改？", detail: "可以从已有项目继承资料，复用项目信息、最近一次图纸和 Agent 设置，再上传调整后的图纸继续评图。" },
  { title: "操作指引：查看历史版本", detail: "在报告页点击历史版本对比，可以查看同一项目的多次提交，比较总分和各维度变化。" },
  { title: "常见问题：知识库依据从哪里来？", detail: "系统会根据项目类型、阶段、图纸内容和设计说明，从本地知识库中筛选最相关的规范、案例和常见问题。" },
  { title: "操作指引：从旧项目继续评图", detail: "新建评图时可以选择继承已有项目，复用基础资料和最近一次图纸，再上传修改后的版本。" },
  { title: "常见问题：草稿项目如何处理？", detail: "未提交评图的项目会显示为草稿，点击项目后可继续补充信息、上传图纸并确认提交。" },
];

interface InformationItem {
  title: string;
  detail: string;
}

// 渲染项目首页。
export function DashboardPage({ go }: PageProps) {
  return <DashboardLayout go={go} />;
}

// 渲染项目首页主体，供新建方式弹窗背景复用。
function DashboardLayout({ go }: PageProps) {
  const { projects, project: activeProject, evaluation, openProject, openSubmission } = useWorkspace();
  const { profile } = useProfile();
  const [dashboardProjects, setDashboardProjects] = useState<ProjectGroup[]>(() => getCachedProjectGroups(projects));
  const [detail, setDetail] = useState<InformationItem | null>(null);
  const [listTitle, setListTitle] = useState("");
  const [listItems, setListItems] = useState<InformationItem[]>([]);
  const [pinnedProjectIds, setPinnedProjectIds] = useState<number[]>(() => readPinnedProjectIds());
  const visibleDashboardProjects = sortPinnedProjectGroups(dashboardProjects, pinnedProjectIds).slice(0, 6);

  useEffect(() => {
    let mounted = true;
    setDashboardProjects(getCachedProjectGroups(projects));
    void loadProjectGroups(projects).then((groups) => mounted && setDashboardProjects(groups));
    return () => { mounted = false; };
  }, [projects]);

  useEffect(() => {
    const syncPinnedProjects = () => setPinnedProjectIds(readPinnedProjectIds());
    window.addEventListener(PINNED_PROJECTS_CHANGED_EVENT, syncPinnedProjects);
    window.addEventListener("storage", syncPinnedProjects);
    return () => {
      window.removeEventListener(PINNED_PROJECTS_CHANGED_EVENT, syncPinnedProjects);
      window.removeEventListener("storage", syncPinnedProjects);
    };
  }, []);

  // 打开首页中的项目，并进入当前状态对应页面。
  const openDashboardProject = async (item: ProjectGroup) => {
    const latest = getLatestVersion(item);
    if (!latest) {
      await openProject(item.latestProject.id);
      go("info");
      return;
    }
    await openSubmission(latest.submission.id);
    if (latest.history?.overall_score != null || latest.submission.status === "completed") go("report");
    else if (latest.submission.status === "evaluating") go("processing");
    else go(readSubmissionRoute(latest.submission.id, "info"));
  };

  return (
    <div className="font-chat relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} />
      <PageTitle title={`欢迎回来，${profile.displayName}`} subtitle="继续提交图纸，或查看历史评图趋势。" />
      <section className="figma-shadow absolute left-[307px] top-[183px] h-[624px] w-[803px] rounded-[18px] border border-[#e8ebef] bg-white">
        <h2 className="absolute left-[23px] top-[23px] text-[18px] font-bold leading-6">最近评图项目</h2>
        <p className="absolute left-[23px] top-[51px] text-[12px] text-[#6b7280]">查看正在进行、待确认和已完成的设计评图。</p>
        {visibleDashboardProjects.length === 0 ? <DashboardEmpty /> : (
          <>
            <div className="absolute left-[24px] top-[92px] grid grid-cols-2 gap-x-[24px] gap-y-[24px]">
              {visibleDashboardProjects.map((item) => <DashboardProjectCard item={item} progress={item.projects.some((project) => project.id === activeProject?.id) ? evaluation.progress : 0} key={item.key} onOpen={() => void openDashboardProject(item)} />)}
            </div>
            <div className="absolute bottom-[14px] left-[24px] flex h-[34px] w-[756px] items-center rounded-[10px] bg-[#f7f8fa] px-4 text-[12px] text-[#6b7280]">
              最近更新：{visibleDashboardProjects[0]?.name ?? "正在读取项目状态"} {getLatestVersion(visibleDashboardProjects[0]) ? projectState(visibleDashboardProjects[0]).description : "尚未提交评图资料"}
            </div>
          </>
        )}
      </section>
      <DashboardInformationCard title="公告" subtitle="展示系统能力更新和使用提醒。" items={announcements.slice(0, 4)} className="top-[181px] h-[330px]" onDetail={setDetail} onMore={() => { setListTitle("历史公告"); setListItems(announcements); }} />
      <DashboardInformationCard title="新手引导" subtitle="提供首次评图流程和常见问题。" items={guideItems.slice(0, 3)} className="top-[532px] h-[275px]" onDetail={setDetail} onMore={() => { setListTitle("操作指引与常见问题"); setListItems(guideItems); }} />
      {listItems.length > 0 && <InformationListModal title={listTitle} items={listItems} onDetail={setDetail} onClose={() => setListItems([])} />}
      {detail && <InformationDetailModal item={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

// 渲染首页无项目状态。
function DashboardEmpty() {
  return (
    <>
      <h3 className="absolute left-[299px] top-[266px] text-[28px] font-bold leading-9">还没有评图项目</h3>
      <p className="absolute left-[225px] top-[309px] w-[354px] text-center text-[14px] leading-[15px] text-[#9a9ea7]">创建你的第一个评图项目，上传图纸并选择 AI Agent，让 AI 为你的设计提供专业的评估和建议</p>
    </>
  );
}

// 渲染首页项目卡片。
function DashboardProjectCard({ item, progress, onOpen }: { item: ProjectGroup; progress: number; onOpen: () => void }) {
  const state = projectState(item, progress);
  const latest = getLatestVersion(item);
  return (
    <article className="figma-shadow relative h-[140px] w-[366px] rounded-[12px] border border-[#e8ebef] bg-[#fafbfc]">
      <span className={`absolute left-[18px] top-[20px] flex h-8 w-8 items-center justify-center rounded-full ${state.markerBackground}`}><span className={`project-status-dot h-[10px] w-[10px] rounded-full ${state.markerDot}`} /></span>
      <h3 className="project-card-title-text absolute left-[64px] top-[17px] max-w-[202px] truncate">{item.name}</h3>
      <p className="absolute left-[64px] top-[43px] max-w-[202px] truncate text-[11px] font-medium leading-4 text-[#6b7280]">{latest?.submission.design_stage ?? "尚未选择阶段"} · {formatDate(latest?.submission.updated_at ?? latest?.submission.created_at ?? item.latestProject.created_at)}</p>
      <span className={`absolute right-[18px] top-[18px] flex h-6 min-w-[62px] items-center justify-center rounded-full px-3 text-[11px] font-bold ${state.badgeClass}`}>{state.label}</span>
      <span className="absolute left-[18px] top-[82px] text-[12px] font-medium text-[#6b7280]">{state.description}</span>
      <b className={`absolute left-[18px] top-[101px] text-[20px] leading-6 ${state.valueClass}`}>{state.value}</b>
      <button type="button" className="absolute bottom-[18px] right-[18px] flex h-[30px] w-[96px] items-center justify-center rounded-[8px] border border-[#e8ebef] bg-white text-[#111318]" onClick={onOpen}><span className="project-detail-button-text">查看详情</span></button>
    </article>
  );
}

// 根据最新提交和报告生成首页状态文字。
function projectState(item: ProjectGroup, progress = 0) {
  const latest = getLatestVersion(item);
  if (latest?.history?.overall_score != null || latest?.submission.status === "completed") return { label: "已完成", description: "报告完成", value: String(Math.round(latest.history?.overall_score ?? 0)), badgeClass: "bg-[#eaf8ef] text-[#16a34a]", valueClass: "text-[#16a34a]", markerBackground: "bg-[#eaf8ef]", markerDot: "bg-[#16a34a]" };
  if (latest?.submission.status === "evaluating") return { label: "进行中", description: "评图中", value: `${progress || 70}%`, badgeClass: "bg-[#f1eeff] text-[#6c4dff]", valueClass: "text-[#6c4dff]", markerBackground: "bg-[#f1eeff]", markerDot: "bg-[#6c4dff]" };
  return { label: "草稿", description: "等待提交", value: "草稿", badgeClass: "bg-[#f1f5f9] text-[#64748b]", valueClass: "text-[#64748b]", markerBackground: "bg-[#f1f5f9]", markerDot: "bg-[#64748b]" };
}

// 把后端时间转换为首页简短日期。
function formatDate(date?: string | null) {
  return date?.slice(0, 10).replace(/-/g, "/") ?? "最近编辑";
}

// 渲染首页公告或新手引导卡片。
function DashboardInformationCard({ title, subtitle, items, className, onDetail, onMore }: { title: string; subtitle: string; items: InformationItem[]; className: string; onDetail: (item: InformationItem) => void; onMore: () => void }) {
  return (
    <Card className={`absolute right-[23px] w-[367px] ${className}`}>
      <h2 className="absolute left-7 top-[24px] text-[18px] font-bold leading-6">{title}</h2>
      <p className="absolute left-7 top-[53px] text-[12px] leading-4 text-[#6b7280]">{subtitle}</p>
      <div className="absolute left-7 right-7 top-[80px] space-y-2">
        {items.map((item) => (
          <button type="button" className="flex h-[42px] w-full items-center rounded-[10px] border-b border-[#eef0f3] text-left hover:bg-[#f4f6f8]" key={item.title} onClick={() => onDetail(item)}>
            <b className="information-row-text max-w-[248px] truncate">{item.title}</b>
            <span className="detail-link-text ml-auto">详情</span>
          </button>
        ))}
      </div>
      <button type="button" className="detail-link-text absolute bottom-[18px] right-7" onClick={onMore}>查看更多</button>
    </Card>
  );
}

// 渲染公告或引导详情弹窗。
function InformationDetailModal({ item, onClose }: { item: InformationItem; onClose: () => void }) {
  return (
    <div className="absolute inset-0 z-40 bg-[#171719]/30" onClick={onClose}>
      <section className="figma-shadow absolute left-[476px] top-[156px] h-[508px] w-[584px] rounded-[22px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        <h2 className="pr-9 text-[22px] font-bold leading-8">{item.title}</h2>
        <button type="button" className="absolute right-6 top-6 flex h-7 w-7 items-center justify-center rounded-full border border-[#e8ebef] text-[18px] text-[#9a9ea7]" onClick={onClose}>×</button>
        <p className="mt-5 text-[14px] leading-7 text-[#53565e]">{item.detail}</p>
      </section>
    </div>
  );
}

// 渲染全部公告或引导条目。
function InformationListModal({ title, items, onDetail, onClose }: { title: string; items: InformationItem[]; onDetail: (item: InformationItem) => void; onClose: () => void }) {
  return (
    <div className="absolute inset-0 z-30 bg-[#171719]/30" onClick={onClose}>
      <section className="figma-shadow absolute left-[476px] top-[156px] h-[508px] w-[584px] rounded-[22px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        <h2 className="ml-2 text-[22px] font-bold">{title}</h2>
        <button type="button" className="absolute right-6 top-6 flex h-7 w-7 items-center justify-center rounded-full border border-[#e8ebef] text-[18px] text-[#9a9ea7]" onClick={onClose}>×</button>
        <div className="information-list-scroll absolute bottom-7 left-7 right-7 top-[86px] overflow-y-auto pr-2">
          {items.map((item) => (
            <button type="button" className="flex h-[52px] w-full items-center rounded-[10px] border-b border-[#eef0f3] px-2 text-left hover:bg-[#f4f6f8]" onClick={() => onDetail(item)} key={item.title}>
              <span className="information-row-text max-w-[420px] truncate">{item.title}</span>
              <span className="detail-link-text ml-auto">查看详情</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

// 渲染新建方式浮层。
export function CreateModalPage({ go }: PageProps) {
  const { projects, inheritProject, resetDraft } = useWorkspace();
  const [mode, setMode] = useState<"choice" | "inherit">("choice");
  const [projectGroups, setProjectGroups] = useState<ProjectGroup[]>(() => getCachedProjectGroups(projects));
  const [versionMenuKey, setVersionMenuKey] = useState<string | null>(null);
  useEffect(() => {
    let mounted = true;
    setProjectGroups(getCachedProjectGroups(projects));
    void loadProjectGroups(projects).then((groups) => mounted && setProjectGroups(groups));
    return () => { mounted = false; };
  }, [projects]);
  const startBlank = () => {
    resetDraft();
    go("info");
  };
  const getCompletedVersionEntries = (group: ProjectGroup) => group.versions
    .filter((version) => version.history?.overall_score != null)
    .map((version, index) => ({ version, displayNumber: index + 1 }));
  const getSelectedVersion = (group: ProjectGroup) => {
    const completed = getCompletedVersionEntries(group);
    const latestCompleted = completed[completed.length - 1];
    const latest = getLatestVersion(group);
    return latestCompleted ?? (latest ? { version: latest, displayNumber: null } : null);
  };
  const inheritVersion = async (group: ProjectGroup, targetVersion?: ProjectVersion | null) => {
    const selected = getSelectedVersion(group);
    const version = targetVersion ?? selected?.version ?? null;
    await inheritProject(version?.project.id ?? group.latestProject.id, version?.submission.id);
    go("info");
  };
  return (
    <div className="relative h-full w-full">
      <ProjectsDashboard go={go} />
      <div className="absolute left-[-240px] top-[-64px] z-20 h-[940px] w-[2040px] bg-[#171719]/30" onClick={() => go("dashboard")} />
      <section className="figma-shadow absolute left-[474px] top-[168px] z-30 h-[474px] w-[588px] rounded-[24px] border border-[#e8ebef] bg-white px-8 py-7">
        <h2 className="text-[22px] font-bold leading-8">{mode === "inherit" ? "选择继承版本" : "选择新建评图方式"}</h2>
        {mode === "inherit"
          ? <button type="button" className="create-return-button absolute right-8 top-7 text-[#6c4dff]" onClick={() => { setVersionMenuKey(null); setMode("choice"); }}>返回</button>
          : <button className="absolute right-8 top-7 flex h-7 w-7 items-center justify-center rounded-full border border-[#e8ebef] bg-[#fafbfc] text-[18px] font-bold text-[#9a9ea7]" onClick={() => go("dashboard")}>×</button>}
        <p className="mt-1 text-[13px] leading-5 text-[#53565e]">{mode === "inherit" ? "选择任一历史项目的任一版本，系统会带入该版本已填写的项目资料。" : "可以从零创建一个空白项目，也可以继承已有项目资料继续评图。"}</p>
        {mode === "choice" ? (
          <>
            <button className="absolute left-8 top-[115px] h-[210px] w-[250px] rounded-[16px] border-2 border-[#e8ebef] bg-[#fafbfc] p-5 text-left hover:border-[#6c4dff]" onClick={startBlank}>
              <span className="flex h-12 w-12 items-center justify-center rounded-[14px] bg-transparent text-[42px] font-light leading-none text-[#6c4dff]">＋</span>
              <b className="mt-4 block text-[17px]">新建项目</b>
              <span className="mt-2 block text-[12px] leading-5 text-[#53565e]">从空白表单开始，录入项目资料、上传图纸并选择评图 Agent。</span>
            </button>
            <button className="absolute right-8 top-[115px] h-[210px] w-[250px] rounded-[16px] border-2 border-[#e8ebef] bg-[#fafbfc] p-5 text-left hover:border-[#6c4dff]" onClick={() => setMode("inherit")}>
              <span className="flex h-12 w-12 items-center justify-center rounded-[14px] bg-transparent text-[#6c4dff]"><BranchIcon background="#fafbfc" /></span>
              <b className="mt-4 block text-[17px]">继承已有项目</b>
              <span className="mt-2 block text-[12px] leading-5 text-[#53565e]">从历史项目版本中选择一项，带入基础信息、图纸和评图设置。</span>
            </button>
          </>
        ) : (
          <>
            <div className="report-light-scroll absolute bottom-8 left-8 right-8 top-[118px] space-y-2 overflow-y-auto pr-2">
              {projectGroups.length ? projectGroups.map((group) => {
                const selected = getSelectedVersion(group);
                const version = selected?.version ?? null;
                const olderVersions = getCompletedVersionEntries(group)
                  .filter((item) => item.version.submission.id !== version?.submission.id)
                  .reverse();
                const score = version?.history?.overall_score;
                const expanded = versionMenuKey === group.key;
                return (
                <div key={group.key}>
                  <div role="button" tabIndex={0} className={`flex min-h-[64px] w-full cursor-pointer items-center rounded-[12px] border border-[#e8ebef] px-4 text-left ${expanded ? "bg-[#eef0f4]" : "bg-white hover:bg-[#f4f6f8]"}`} onClick={() => void inheritVersion(group, version)} onKeyDown={(event) => event.key === "Enter" && void inheritVersion(group, version)}>
                    <span className="min-w-0 flex-1">
                      <b className="block truncate text-[13px] leading-5 text-[#171719]">{group.name}</b>
                      <span className="block text-[11px] leading-4 text-[#9a9ea7]">{version ? `${selected?.displayNumber ? `V${selected.displayNumber}` : "草稿"} · ${version.submission.design_stage}${score != null ? ` · ${Math.round(score)}分` : ""}` : "基础资料"}</span>
                    </span>
                    {olderVersions.length > 0 && (
                      <button type="button" aria-label="选择历史版本" className="ml-3 flex h-8 w-8 items-center justify-center rounded-[9px] hover:bg-[#eef0f4]" onClick={(event) => { event.stopPropagation(); setVersionMenuKey(versionMenuKey === group.key ? null : group.key); }}>
                        <span className={`h-2 w-2 rotate-45 border-b-2 border-r-2 border-[#6b7385] ${versionMenuKey === group.key ? "rotate-[225deg]" : ""}`} />
                      </button>
                    )}
                  </div>
                  {expanded && olderVersions.map((item) => (
                    <button type="button" className="mt-2 flex min-h-[54px] w-full items-center rounded-[12px] border border-[#e8ebef] bg-[#f7f8fa] px-4 text-left hover:bg-[#eef0f4]" key={item.version.submission.id} onClick={() => void inheritVersion(group, item.version)}>
                      <span className="min-w-0 flex-1">
                        <b className="block truncate text-[13px] leading-5 text-[#171719]">{group.name}</b>
                        <span className="block text-[11px] leading-4 text-[#9a9ea7]">V{item.displayNumber} · {item.version.submission.design_stage}{item.version.history?.overall_score != null ? ` · ${Math.round(item.version.history.overall_score)}分` : ""}</span>
                      </span>
                    </button>
                  ))}
                </div>
                );
              }) : <p className="rounded-[12px] bg-[#fafbfc] px-4 py-4 text-[13px] text-[#9a9ea7]">暂无可继承的历史项目。</p>}
            </div>
          </>
        )}
      </section>
    </div>
  );
}

// 渲染新建浮层背后的项目工作台。
function ProjectsDashboard({ go }: PageProps) {
  return <DashboardLayout go={go} />;
}

// 渲染项目信息表单。
export function ProjectInfoPage({ go }: PageProps) {
  useRememberFlowRoute("info");
  const taskbookRef = useRef<HTMLInputElement>(null);
  const { attachments, deleteTaskbook, draft, setDraftField, saveDraft, uploadTaskbook } = useWorkspace();
  const [editingTaskbook, setEditingTaskbook] = useState(false);
  const [openSelect, setOpenSelect] = useState<"building" | "grade" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Attachment | null>(null);
  useEffect(() => {
    if (!openSelect) return;
    const closeSelect = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("[data-info-select]")) return;
      setOpenSelect(null);
    };
    document.addEventListener("pointerdown", closeSelect);
    return () => document.removeEventListener("pointerdown", closeSelect);
  }, [openSelect]);
  const chooseGrade = (value: string) => {
    setDraftField("grade", value);
    setDraftField("courseName", `建筑设计课 · ${value}`);
    setOpenSelect(null);
  };
  const saveAndContinue = async () => {
    validateProjectInfoStep(draft, attachments);
    await saveDraft();
  };
  return (
    <FlowShell go={go} title="新建评图" subtitle="填写项目基础信息，并上传任务书。" current={1} projectName="未命名">
      <FlowActions go={go} next="agents" onSave={() => saveDraftAtRoute(saveDraft, "info")} beforeNext={saveAndContinue} />
      <Card className="absolute left-[307px] top-[220px] h-[584px] w-[1206px] px-8 py-7">
        <h2 className="text-[22px] font-bold leading-7">项目基础信息</h2>
        <div className="mt-7 grid grid-cols-4 gap-4">
          <InfoTextField label="项目名称" value={draft.name} onChange={(value) => setDraftField("name", value)} />
          <InfoTextField label="基地位置" value={draft.siteLocation} onChange={(value) => setDraftField("siteLocation", value)} />
          <SelectField label="建筑类型" value={draft.buildingType} placeholder="请选择类型" open={openSelect === "building"} options={buildingTypeOptions} onToggle={() => setOpenSelect(openSelect === "building" ? null : "building")} onSelect={(value) => { setDraftField("buildingType", value); setOpenSelect(null); }} />
          <SelectField label="设计年级" value={draft.grade} placeholder="请选择年级" open={openSelect === "grade"} options={gradeOptions} onToggle={() => setOpenSelect(openSelect === "grade" ? null : "grade")} onSelect={chooseGrade} />
        </div>
        <label className="mt-5 block w-full">
          <b className="mb-2 block text-[14px] font-bold leading-5 text-[#171719]">设计说明</b>
          <textarea value={draft.description} onChange={(event) => setDraftField("description", event.target.value)} placeholder="请尽量详细描述你的设计概念、功能布局、流线组织、场地回应和希望重点评估的问题。说明越具体，评图结果越准确。" className="h-[194px] w-full resize-none rounded-[12px] border border-[#e8ebef] bg-white px-[13px] py-[11px] text-[13px] leading-6 text-[#171719] outline-none placeholder:text-[#c2c7d0]" />
        </label>
        <div className="mt-5 flex h-[112px] items-center rounded-[14px] border border-[#e8ebef] bg-white px-5">
          <div className="mr-6 flex h-11 w-11 items-center justify-center rounded-[12px] border border-[#e8ebef] bg-[#fafbfc] text-[20px]">▤</div>
          <div className="w-[310px]"><h3 className="text-[14px] font-bold">上传任务书</h3><p className="mt-1 text-[12px] text-[#9a9ea7]">支持 PDF、Word 或 TXT 文档，不支持图片文件。</p></div>
          <div className="flex min-w-0 flex-1 gap-4">
            {attachments.length ? attachments.slice(0, 2).map((item) => <FileRow name={item.original_name} meta="已保存" status="已上传" editing={editingTaskbook} onDelete={() => setDeleteTarget(item)} key={item.id} />) : <span className="self-center text-[12px] text-[#9a9ea7]">暂未上传任务书</span>}
          </div>
          <input ref={taskbookRef} className="hidden" type="file" accept=".pdf,.doc,.docx,.txt,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" onChange={(event) => event.target.files?.[0] && void uploadTaskbook(event.target.files[0])} />
          <div className="ml-5 flex gap-3">
            <Button kind="white" className="report-top-action-button w-[108px]" onClick={() => setEditingTaskbook((current) => !current)}><span className="text-[#171719]"><EditIcon /></span>{editingTaskbook ? "完成编辑" : "编辑"}</Button>
            <Button kind="dark" className="report-top-action-button w-[126px]" onClick={() => taskbookRef.current?.click()}><span className="text-white"><UploadIcon /></span>上传文件</Button>
          </div>
        </div>
      </Card>
      {deleteTarget && <TaskbookDeleteCard fileName={deleteTarget.original_name} onClose={() => setDeleteTarget(null)} onConfirm={async () => {
        await deleteTaskbook(deleteTarget.id);
        setDeleteTarget(null);
      }} />}
    </FlowShell>
  );
}

// 渲染项目信息页的一行普通输入。
function InfoTextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <b className="mb-2 block text-[14px] font-bold leading-5 text-[#171719]">{label}</b>
      <input value={value} onChange={(event) => onChange(event.target.value)} className="h-10 w-full rounded-[12px] border border-[#e8ebef] bg-white px-[13px] py-[9px] text-[13px] leading-[18px] text-[#171719] outline-none" />
    </label>
  );
}

// 渲染项目信息页的下拉选择输入。
function SelectField({ label, value, placeholder, options, open, onToggle, onSelect }: { label: string; value: string; placeholder: string; options: string[]; open: boolean; onToggle: () => void; onSelect: (value: string) => void }) {
  return (
    <div className="relative" data-info-select>
      <b className="mb-2 block text-[14px] font-bold leading-5 text-[#171719]">{label}</b>
      <button type="button" className="flex h-10 w-full items-center rounded-[12px] border border-[#e8ebef] bg-white px-[13px] py-[9px] text-left text-[13px] leading-[18px] text-[#171719]" onClick={onToggle}>
        <span className={value ? "" : "text-[#c2c7d0]"}>{value || placeholder}</span>
        <span className={`ml-auto h-2 w-2 rotate-45 border-b-2 border-r-2 border-[#6b7385] transition-transform ${open ? "rotate-[225deg]" : ""}`} />
      </button>
      {open && (
        <div className="report-light-scroll figma-shadow absolute left-0 right-0 top-[68px] z-20 max-h-[184px] overflow-y-auto rounded-[12px] border border-[#e8ebef] bg-white p-1 pr-2">
          {options.map((option) => (
            <button type="button" className={`h-9 w-full rounded-[9px] px-3 text-left text-[13px] font-bold ${value === option ? "bg-[#efe9ff] text-[#6c4dff]" : "text-[#171719] hover:bg-[#f4f6f8]"}`} key={option} onClick={() => onSelect(option)}>{option}</button>
          ))}
        </div>
      )}
    </div>
  );
}

// 渲染任务书文件行。
function FileRow({ name, meta, status, editing, onDelete }: { name: string; meta: string; status: string; editing?: boolean; onDelete?: () => void }) {
  return (
    <div className="relative h-[77px] w-[210px] shrink-0 rounded-[12px] border border-[#e8ebef] bg-[#fafbfc] px-3 py-3 text-[12px]">
      {editing && <button type="button" aria-label="删除附件" className="absolute -right-3 -top-3 flex h-7 w-7 items-center justify-center rounded-full border border-[#d9dde3] bg-white text-[18px] font-bold leading-none text-[#171719] hover:bg-[#eef0f4]" onClick={onDelete}>×</button>}
      <b className="block">{name} <span className="float-right rounded-full bg-[#e6f8ed] px-2 py-1 text-[10px] text-[#22c55e]">{status}</span></b><span className="mt-1 block text-[#9a9ea7]">{meta}</span>
    </div>
  );
}

// 渲染任务书删除确认卡片。
function TaskbookDeleteCard({ fileName, onClose, onConfirm }: { fileName: string; onClose: () => void; onConfirm: () => Promise<void> }) {
  const [submitting, setSubmitting] = useState(false);

  // 删除前先二次确认，避免误删任务书。
  const confirm = async () => {
    setSubmitting(true);
    try {
      await onConfirm();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="absolute inset-0 z-[70] bg-[#171719]/30" onClick={onClose} />
      <section className="figma-shadow font-chat absolute left-[472px] top-[270px] z-[80] h-[238px] w-[592px] rounded-[20px] border border-[#d9dde3] bg-white p-7">
        <h2 className="text-[24px] font-bold leading-8">删除文件</h2>
        <p className="mt-6 text-[16px] leading-6 text-[#171719]">确定删除“{fileName}”吗？删除后需要重新上传。</p>
        <div className="absolute bottom-6 right-7 flex gap-4">
          <button type="button" disabled={submitting} className="app-action-button h-10 w-[82px] rounded-[12px] border border-[#d9dde3] bg-white text-[#171719] disabled:opacity-60" onClick={onClose}>取消</button>
          <button type="button" disabled={submitting} className="app-action-button h-10 w-[112px] rounded-[12px] bg-[#171719] text-white disabled:opacity-60" onClick={() => void confirm()}>{submitting ? "删除中" : "确认删除"}</button>
        </div>
      </section>
    </>
  );
}

// 渲染继承项目卡片中的分支图标。
function BranchIcon({ background = "white" }: { background?: string }) {
  return (
    <svg viewBox="0 0 48 48" className="h-12 w-12 fill-none stroke-current stroke-[3]" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M17 14v20" />
      <path d="M17 22h10c4.2 0 7 2.8 7 7" />
      <circle cx="17" cy="11" r="4" fill={background} />
      <circle cx="17" cy="37" r="4" fill={background} />
      <circle cx="34" cy="29" r="4" fill={background} />
    </svg>
  );
}

// 渲染任务书编辑按钮图标。
function EditIcon() {
  return <svg viewBox="0 0 20 20" className="mr-2 h-4 w-4 fill-none stroke-current stroke-[1.8]"><path d="m4 13.8-.6 2.8 2.8-.6 8.4-8.4-2.2-2.2L4 13.8z" /><path d="m11.4 6.4 2.2 2.2" /></svg>;
}

// 渲染任务书上传按钮图标。
function UploadIcon() {
  return <svg viewBox="0 0 20 20" className="mr-2 h-4 w-4 fill-none stroke-current stroke-[1.8]"><path d="M10 14V4" /><path d="m6.5 7.5 3.5-3.5 3.5 3.5" /><path d="M4 15.5h12" /></svg>;
}

// 渲染删除按钮图标。
function TrashIcon() {
  return <svg viewBox="0 0 20 20" className="mr-2 h-4 w-4 fill-none stroke-current stroke-[1.8]"><path d="M4 6h12" /><path d="M8 6V4h4v2" /><path d="m6 8 .5 8h7l.5-8" /><path d="M9 10v4" /><path d="M11 10v4" /></svg>;
}

// 渲染阶段与 Agent 选择页。
export function AgentsPage({ go }: PageProps) {
  useRememberFlowRoute("agents");
  const { draft, setDraftField, saveDraft } = useWorkspace();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const selectStage = (stage: string) => {
    setDraftField("designStage", stage);
    setDraftField("enabledAgents", getStageAgentTypes(stage));
  };
  const nextPage = async () => {
    setSaving(true);
    setError("");
    try {
      validateAgentStep(draft);
      await saveDraft();
      go("upload");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "草稿保存失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  };
  return (
    <FlowShell go={go} title="选择设计阶段" subtitle="系统会根据项目阶段自动调整评价重点与 Agent 协作方式。" current={2}>
      <div className="absolute right-[23px] top-[156px] flex gap-5"><Button kind="white" disabled={saving} className="report-top-action-button w-[109px]" onClick={() => go("info")}>上一步</Button><Button kind="purple" disabled={saving} className="report-top-action-button w-[110px] rounded-[16px]" onClick={() => void nextPage()}>{saving ? "保存中" : "下一步"}</Button></div>
      <Card className="absolute left-[307px] top-[224px] h-[579px] w-[521px] p-7">
        <h2 className="text-[22px] font-bold">选择项目阶段</h2>
        <div className="mt-7 space-y-9">
          <StageCard title="概念阶段" desc="概念立意、空间构想、场地阅读" active={draft.designStage === "概念阶段"} onClick={() => selectStage("概念阶段")} />
          <StageCard title="方案阶段" desc="场地回应、功能流线、形式构图、结构可行性" active={draft.designStage === "方案阶段"} onClick={() => selectStage("方案阶段")} />
          <StageCard title="图纸阶段" desc="图面表达、排版质量、方案完整度" active={draft.designStage === "图纸阶段"} onClick={() => selectStage("图纸阶段")} />
        </div>
      </Card>
      <Card className="absolute left-[858px] top-[224px] h-[579px] w-[655px] p-7">
        <h2 className="text-[22px] font-bold">启用的 Agent</h2>
        <div className="report-light-scroll mt-6 grid max-h-[470px] grid-cols-2 gap-6 overflow-y-auto pr-3">
          {agentCards.map((agent) => <AgentTile key={agent.type} agent={agent} active={draft.enabledAgents.includes(agent.type)} />)}
        </div>
      </Card>
      {error && <FlowErrorCard message={error} onClose={() => setError("")} />}
    </FlowShell>
  );
}

// 渲染阶段选项。
function StageCard({ title, desc, active, onClick }: { title: string; desc: string; active?: boolean; onClick?: () => void }) {
  return <button type="button" onClick={onClick} className={`relative block h-[130px] w-full rounded-[18px] border p-5 text-left ${active ? "border-[#6c4dff] bg-[#efe9ff]" : "border-[#e8ebef] bg-white"}`}><b className="text-[18px]">{title}</b><p className="mt-2 text-[13px] text-[#53565e]">{desc}</p>{active && <span className="absolute right-6 top-[30px] rounded-full px-4 py-2 text-[12px] font-bold text-[#6c4dff]">当前选择</span>}</button>;
}

// 渲染 Agent 选项。
function AgentTile({ agent, active }: { agent: AgentCardSpec; active: boolean }) {
  return <article className={`relative h-[220px] overflow-hidden rounded-[18px] border p-4 text-left ${active ? "border-[#6c4dff] bg-[#efe9ff]" : "border-[#e8ebef] bg-white"}`}><b className={`text-[12px] ${active ? "text-[#6c4dff]" : "text-[#9a9ea7]"}`}>{active ? "已启用" : "未启用"}</b><h3 className="mt-5 text-[18px] font-bold">{agent.display}</h3><p className="mt-2 w-[118px] text-[12px] leading-[18px] text-[#53565e]">{agent.cardDesc}</p><img className="absolute bottom-0 right-1 h-[132px] w-[132px] object-contain" src={agent.image} /></article>;
}

// 渲染上传图纸页。
export function UploadPage({ go }: PageProps) {
  useRememberFlowRoute("upload");
  const inputRef = useRef<HTMLInputElement>(null);
  const replaceInputRef = useRef<HTMLInputElement>(null);
  const { drawings, selectedDrawingId, selectDrawing, uploadFiles, replaceSelectedDrawing, saveDraft, updateSelectedDrawing, deleteDrawingIds } = useWorkspace();
  const [batchEditing, setBatchEditing] = useState(false);
  const [checkedDrawingIds, setCheckedDrawingIds] = useState<number[]>([]);
  const [deleteBatchOpen, setDeleteBatchOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [replacingUpload, setReplacingUpload] = useState<ReplacingUpload | null>(null);
  const [error, setError] = useState("");
  const selected = drawings.find((item) => item.id === selectedDrawingId) ?? drawings[0];
  const selectedReplacing = Boolean(replacingUpload && selected?.id === replacingUpload.drawingId);
  const pendingDetail = !selected && pendingUploads[0] ? pendingUploads[0] : null;
  const detailName = selectedReplacing ? replacingUpload?.name : selected?.original_name ?? pendingDetail?.name ?? "总平面图.pdf";
  const detailPending = selectedReplacing || Boolean(pendingDetail);
  const visibleDrawings = drawings.length || pendingUploads.length ? drawings : drawingNames;
  const selectedIndex = selected ? drawings.findIndex((item) => item.id === selected.id) : 0;
  const previewSrc = selected ? apiUrl(selected.file_url) : "/assets/v1/upload-plan.svg";
  const toggleBatchEditing = () => {
    setBatchEditing((current) => !current);
    if (batchEditing) setCheckedDrawingIds([]);
  };
  const toggleDrawingChecked = (fileId: number) => {
    setCheckedDrawingIds((current) => current.includes(fileId) ? current.filter((id) => id !== fileId) : [...current, fileId]);
  };
  const handleUploadChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.currentTarget.files ?? []);
    if (files.length) {
      const pending = files.map((file, index) => ({ id: `${file.name}-${file.lastModified}-${index}`, name: file.name }));
      setPendingUploads((current) => [...current, ...pending]);
      void uploadFiles(files).catch((caught) => setError(caught instanceof Error ? caught.message : "图纸上传失败。")).finally(() => {
        setPendingUploads((current) => current.filter((item) => !pending.some((pendingItem) => pendingItem.id === item.id)));
      });
    }
    event.currentTarget.value = "";
  };
  const handleReplaceChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (file) {
      const replacingId = selected?.id ?? null;
      setReplacingUpload({ drawingId: replacingId, name: file.name });
      void replaceSelectedDrawing(file).catch((caught) => setError(caught instanceof Error ? caught.message : "图纸替换失败。")).finally(() => setReplacingUpload(null));
    }
    event.currentTarget.value = "";
  };
  return (
    <FlowShell go={go} title="上传设计图纸" subtitle="上传您的设计图纸，AI 将基于多维度为您提供专业评审建议。" current={3}>
      <FlowActions go={go} previous="agents" next="confirm" onSave={() => saveDraftAtRoute(saveDraft, "upload")} beforeNext={async () => { validateUploadStep(drawings); await saveDraft(); }} />
      <Card className="absolute left-[307px] top-[202px] h-[601px] w-[793px] overflow-hidden">
        <div id="upload-scroll-area" className="report-light-scroll absolute inset-0 overflow-y-auto p-[19px]">
          <div className="flex items-center"><Button className="report-top-action-button w-[126px]" onClick={() => inputRef.current?.click()}><span className="text-white"><UploadIcon /></span>上传文件</Button>
          <input ref={inputRef} className="hidden" type="file" accept="image/*,.pdf,application/pdf" multiple onChange={handleUploadChange} />
          <input ref={replaceInputRef} className="hidden" type="file" accept="image/*,.pdf,application/pdf" onChange={handleReplaceChange} />
          <Button kind="white" className="report-top-action-button ml-[29px] w-[126px]" onClick={toggleBatchEditing}><span className="text-[#171719]"><EditIcon /></span>{batchEditing ? "完成编辑" : "批量编辑"}</Button>
          {batchEditing && <Button className="report-top-action-button ml-[29px] w-[126px]" disabled={!checkedDrawingIds.length} onClick={() => checkedDrawingIds.length && setDeleteBatchOpen(true)}><span className="text-white"><TrashIcon /></span>删除</Button>}
          <span className="ml-auto text-[12px] text-[#9a9ea7]">{drawings.length || pendingUploads.length ? `已上传 ${drawings.length} 张图纸${pendingUploads.length ? `，${pendingUploads.length} 张正在上传` : ""}` : "已上传 6 张图纸，1 张正在上传"}</span></div>
          <div className="mt-4 grid grid-cols-3 gap-[14px]">
            {visibleDrawings.map((item, index) => typeof item === "string"
              ? <DrawingCard key={`${item}-${index}`} name={item} index={index} />
              : <DrawingCard key={item.id} name={replacingUpload?.drawingId === item.id ? replacingUpload.name : item.original_name} index={index} drawing={item} selected={!batchEditing && item.id === (selected?.id ?? drawings[0]?.id)} editing={batchEditing} checked={checkedDrawingIds.includes(item.id)} uploading={replacingUpload?.drawingId === item.id} onCheck={() => toggleDrawingChecked(item.id)} onClick={() => batchEditing ? toggleDrawingChecked(item.id) : selectDrawing(item.id)} />)}
            {pendingUploads.map((item, index) => <DrawingCard key={item.id} name={item.name} index={drawings.length + index} uploading />)}
          </div>
        </div>
      </Card>
      <Card className="absolute left-[1124px] top-[202px] h-[601px] w-[389px] overflow-hidden p-0">
        <div className="report-light-scroll absolute inset-y-[19px] left-0 right-2 overflow-y-auto overflow-x-hidden pl-[27px] pr-5">
          <button type="button" className="group relative block w-full overflow-hidden bg-white text-left" onClick={() => !detailPending && setPreviewOpen(true)}>
            {detailPending ? <UploadPendingPreview className="h-[210px]" /> : selected && isPdfDrawing(selected) ? <PdfPreview src={previewSrc} className="h-[210px]" /> : <img className="block w-full rounded-[6px] object-contain" src={previewSrc} />}
            {!detailPending && <span className="absolute inset-0 hidden items-center justify-center bg-black/18 group-hover:flex"><span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/92 text-[#171719] shadow-[0_8px_24px_rgba(0,0,0,0.18)]"><EyeViewIcon /></span></span>}
          </button>
          <h2 className="mt-4 break-all text-[20px] font-bold leading-[28px]">{displayDrawingName(detailName ?? "总平面图.pdf")}</h2>
          <p className="mt-1 text-[12px] text-[#9a9ea7]">上传时间 <span className="float-right">{formatDrawingTime(selected?.created_at)}</span></p>
          <b className="mt-4 block text-[12px] text-[#9a9ea7]">图纸类型</b>
          <DrawingTypeSelect value={selected?.drawing_type ?? "site"} onChange={(value) => void updateSelectedDrawing({ drawing_type: value })} />
          <b className="mt-3 block text-[12px] text-[#9a9ea7]">图纸说明</b>
          <label className="relative mt-2 block h-[112px] rounded-[12px] border border-[#e8ebef] bg-white px-3 py-[11px] text-[13px] text-[#9a9ea7]"><textarea value={selected?.description ?? ""} placeholder="添加图纸说明信息" onChange={(event) => void updateSelectedDrawing({ description: event.target.value })} className="h-[82px] w-full resize-none bg-transparent outline-none placeholder:text-[#9a9ea7]" /><span className="absolute bottom-2 right-3 text-[11px]">{selected?.description?.length ?? 0}/200</span></label>
          <div className="mt-4 flex justify-start gap-4 pb-3"><Button kind="white" className="report-top-action-button h-10 w-[118px] px-2" onClick={() => replaceInputRef.current?.click()}>重新选择</Button><Button kind="white" className="report-top-action-button h-10 w-[92px] px-2" onClick={() => drawings[selectedIndex - 1] && selectDrawing(drawings[selectedIndex - 1].id)}>上一张</Button><Button kind="white" className="report-top-action-button h-10 w-[92px] px-2" onClick={() => drawings[selectedIndex + 1] && selectDrawing(drawings[selectedIndex + 1].id)}>下一张</Button></div>
        </div>
      </Card>
      {previewOpen && <DrawingPreviewOverlay src={previewSrc} alt={selected?.original_name ?? "图纸预览"} pdf={selected ? isPdfDrawing(selected) : false} onClose={() => setPreviewOpen(false)} />}
      {deleteBatchOpen && <TaskbookDeleteCard fileName={`选中的 ${checkedDrawingIds.length} 张图纸`} onClose={() => setDeleteBatchOpen(false)} onConfirm={async () => {
        await deleteDrawingIds(checkedDrawingIds);
        setCheckedDrawingIds([]);
        setBatchEditing(false);
        setDeleteBatchOpen(false);
      }} />}
      {error && <FlowErrorCard message={error} onClose={() => setError("")} />}
    </FlowShell>
  );
}

// 渲染上传图纸卡片。
function DrawingCard({ name, index, drawing, selected = index === 0, editing = false, checked = false, uploading = false, onClick }: { name: string; index: number; drawing?: DrawingFile; selected?: boolean; editing?: boolean; checked?: boolean; uploading?: boolean; onCheck?: () => void; onClick?: () => void }) {
  const uploaded = index < 2;
  const label = drawing ? drawingTypeLabel(drawing.drawing_type) : index === 0 ? "总平面图" : index === 1 ? "首层平面图" : index === 2 ? "二层平面图" : "待识别";
  const mutedForBatch = editing && !checked;
  return (
    <article onClick={onClick} className={`relative h-[220px] cursor-pointer rounded-[12px] border p-[13px] transition-all ${selected ? "border-[#6c4dff] bg-[#f4f0ff] shadow-[0_10px_22px_rgba(108,77,255,0.12)]" : "border-[#e8ebef] bg-white hover:border-[#cfd5de]"} ${mutedForBatch ? "opacity-45 grayscale" : "opacity-100 grayscale-0"}`}>
      {editing && <span className={`absolute left-[9px] top-[9px] z-10 flex h-3 w-3 items-center justify-center rounded-[3px] border text-[9px] ${checked ? "border-[#171719] bg-[#171719] text-white" : "border-[#171719] bg-white"}`}>{checked ? "✓" : ""}</span>}
      {uploading ? <UploadPendingPreview className="mt-[14px] h-[116px]" compact /> : drawing ? (isPdfDrawing(drawing) ? <PdfPreview src={apiUrl(drawing.file_url)} className="mt-[14px] h-[116px]" compact /> : <img className="mt-[14px] h-[116px] w-full rounded-[12px] object-cover" src={apiUrl(drawing.file_url)} />) : <PlanThumb muted={index > 1} className="mt-[14px] h-[116px] w-full" />}
      <div className="mt-2 flex min-w-0 items-center justify-between gap-2"><b className="min-w-0 flex-1 truncate text-[14px]" title={name}>{displayDrawingName(name)}</b><span className="max-w-[92px] shrink-0 truncate rounded-full bg-[#171719] px-3 py-1 text-[10px] font-bold text-white" title={label}>{label}</span></div>
      <p className={`mt-2 border-t border-[#e8ebef] pt-2 text-[12px] ${uploading ? "text-[#6c4dff]" : drawing || uploaded ? "text-[#22c55e]" : "text-[#9a9ea7]"}`}>{uploading ? <>正在上传中<LoadingDots /></> : drawing || uploaded ? "上传成功" : "等待处理"}</p>
    </article>
  );
}

// 渲染 PDF 图纸内容预览。
function PdfPreview({ src, className = "", compact = false }: { src?: string; className?: string; compact?: boolean }) {
  if (!src) return <div className={`flex w-full items-center justify-center rounded-[12px] border border-[#e8ebef] bg-[#f7f8fa] ${className}`}><div className="text-center"><span className={`mx-auto flex items-center justify-center rounded-[10px] bg-[#171719] font-bold text-white ${compact ? "h-9 w-9 text-[11px]" : "h-12 w-12 text-[13px]"}`}>PDF</span><span className={`mt-2 block text-[#9a9ea7] ${compact ? "text-[10px]" : "text-[12px]"}`}>图纸文件</span></div></div>;
  return <div className={`flex w-full items-center justify-center rounded-[12px] border border-[#e8ebef] bg-[#f7f8fa] ${className}`}><div className="px-4 text-center"><span className={`mx-auto flex items-center justify-center rounded-[10px] bg-[#171719] font-bold text-white ${compact ? "h-9 w-9 text-[11px]" : "h-12 w-12 text-[13px]"}`}>PDF</span><span className={`mt-2 block text-[#9a9ea7] ${compact ? "text-[10px]" : "text-[12px]"}`}>{compact ? "重新上传生成预览" : "请重新上传 PDF 生成图片预览"}</span></div></div>;
}

// 渲染上传中省略号动效。
function LoadingDots() {
  return <span className="inline-flex w-5 align-baseline"><span className="upload-loading-dots">...</span></span>;
}

// 渲染图纸上传或替换时的等待占位。
function UploadPendingPreview({ className = "", compact = false }: { className?: string; compact?: boolean }) {
  return (
    <div className={`flex w-full items-center justify-center rounded-[12px] border border-[#e8ebef] bg-white ${className}`}>
      <span className={`font-bold text-[#9a9ea7] ${compact ? "text-[11px]" : "text-[13px]"}`}>图片正在赶来的路上</span>
    </div>
  );
}

// 渲染图纸类型选择栏。
function DrawingTypeSelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [showFloorOptions, setShowFloorOptions] = useState(false);
  const options = showFloorOptions ? floorPlanOptions : drawingTypeOptions;
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
      setShowFloorOptions(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  const handleOptionClick = (optionValue: string) => {
    if (optionValue === "floor-plan") {
      setShowFloorOptions(true);
      return;
    }
    onChange(optionValue);
    setOpen(false);
    setShowFloorOptions(false);
  };
  return (
    <div ref={menuRef} className="relative mt-2">
      <button type="button" className={`confirm-model-button h-10 w-full rounded-[12px] border bg-white px-3 text-left ${open ? "border-[#6c4dff]" : "border-[#e8ebef]"}`} onClick={() => setOpen((current) => !current)}>
        <span className="min-w-0 flex-1 truncate">{drawingTypeLabel(value)}</span>
        <span className="ml-2 text-[10px] text-[#171719]">▼</span>
      </button>
      {open && (
        <div className="absolute left-0 right-0 top-[44px] z-20 rounded-[14px] border border-[#e8ebef] bg-white p-1 shadow-[0_14px_34px_rgba(17,19,24,0.14)]">
          {showFloorOptions && <button type="button" className="confirm-model-option mb-1 h-8 w-full rounded-[10px] px-3 text-left text-[#9a9ea7] hover:bg-[#f7f8fa]" onClick={() => setShowFloorOptions(false)}>返回图纸类型</button>}
          {options.map((option) => (
            <button key={option.value} type="button" className={`confirm-model-option h-9 w-full rounded-[10px] px-3 text-left ${option.value === value ? "bg-[#f1f2f4] text-[#171719]" : "text-[#171719] hover:bg-[#f7f8fa]"}`} onClick={() => handleOptionClick(option.value)}>
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// 渲染图纸大图预览遮罩。
function DrawingPreviewOverlay({ src, alt, pdf = false, onClose }: { src: string; alt: string; pdf?: boolean; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/55 p-8" onClick={onClose}>
      <div className="max-h-[88vh] max-w-[88vw] overflow-hidden rounded-[12px] bg-white p-3 shadow-[0_24px_80px_rgba(0,0,0,0.3)]" onClick={(event) => event.stopPropagation()}>
        {pdf ? <PdfPreview src={src} className="h-[360px] w-[520px]" /> : <img className="max-h-[82vh] max-w-[82vw] object-contain" src={src} alt={alt} />}
      </div>
    </div>
  );
}

// 渲染图片查看图标。
function EyeViewIcon() {
  return <svg viewBox="0 0 24 24" className="h-6 w-6 fill-none stroke-current stroke-[1.8]" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z" /><circle cx="12" cy="12" r="3" /></svg>;
}

// 把楼层数字转换为中文楼层。
function floorText(floor: number): string {
  return ["零", "一", "二", "三", "四", "五", "六", "七"][floor] ?? String(floor);
}

// 去掉图纸文件名后缀，只保留用户可读名称。
function displayDrawingName(name: string): string {
  return name.replace(/\.[^.\\/]+$/, "");
}

// 格式化后端返回的真实上传时间。
function formatDrawingTime(value?: string | null): string {
  if (!value) return "未记录";
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return "未记录";
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

// 判断当前图纸是否是 PDF。
function isPdfDrawing(drawing: DrawingFile): boolean {
  return drawing.mime_type === "application/pdf";
}

// 把后端图纸类型转换为页面展示文字。
function drawingTypeLabel(type: string): string {
  const floorMatch = /^plan-(\d+)$/.exec(type);
  if (floorMatch) return `${floorText(Number(floorMatch[1]))}层平面图`;
  return { site: "总平面图", plan: "首层平面图", section: "剖面图", elevation: "立面图", analysis: "分析图", render: "效果图" }[type] ?? "待识别";
}

// 渲染提交确认页。
export function ConfirmPage({ go }: PageProps) {
  useRememberFlowRoute("confirm");
  const { attachments, draft, drawings, saveDraft, setDraftField, startEvaluation } = useWorkspace();
  const [modelOpen, setModelOpen] = useState(false);
  const [hoveredModelValue, setHoveredModelValue] = useState("");
  const [infoEditing, setInfoEditing] = useState(false);
  const [error, setError] = useState("");
  const modelValue = draft.modelProvider === "gemini" ? "gemini|gemini-2.5-flash" : "dashscope|qwen3.6-plus";
  const modelLabel = draft.modelProvider === "gemini" ? "gemini-2.5-flash" : "qwen3.6-plus";
  const enabledAgentCards = getAgentSpecs(draft.enabledAgents);
  const descriptionText = collapseConfirmText(draft.description);
  useEffect(() => {
    if (!modelOpen) return;
    const close = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("[data-confirm-model-menu]")) return;
      setModelOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [modelOpen]);
  const changeModel = (value: string) => {
    const [provider, model] = value.split("|");
    setDraftField("modelProvider", provider);
    setDraftField("modelName", model);
    setDraftField("modelLabel", model);
    setModelOpen(false);
    setHoveredModelValue("");
  };
  const toggleInfoEditing = async () => {
    if (!infoEditing) {
      setInfoEditing(true);
      return;
    }
    setError("");
    try {
      await saveDraft();
      setInfoEditing(false);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "项目信息保存失败，请稍后重试。");
    }
  };
  const confirm = async () => {
    setError("");
    try {
      validateProjectInfoStep(draft, attachments);
      validateAgentStep(draft);
      validateUploadStep(drawings);
      await saveDraft();
      go("processing");
      void startEvaluation();
    } catch (confirmError) {
      setError(confirmError instanceof Error ? confirmError.message : "请先补充完整提交信息。");
    }
  };
  return (
    <div className="relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} creating />
      <PageTitle title="确认提交" subtitle="请确认以下信息，提交后系统将开始评图分析。" />
      <Steps current={4} />
      <div className="absolute right-[23px] top-[155px] flex gap-3">
        <Button kind="white" className="report-top-action-button w-[115px]" onClick={() => go("upload")}>返回修改</Button>
        <div className="relative" data-confirm-model-menu>
          {modelOpen && (
            <div className="figma-shadow absolute bottom-[46px] right-0 z-20 w-[188px] overflow-hidden rounded-[12px] border border-[#e8ebef] bg-white p-1" onMouseLeave={() => setHoveredModelValue("")}>
              {modelOptions.map((option) => {
                const active = modelValue === option.value && !hoveredModelValue;
                const hovered = hoveredModelValue === option.value;
                return (
                  <button type="button" key={option.value} onMouseEnter={() => setHoveredModelValue(option.value)} onClick={() => changeModel(option.value)} className={`confirm-model-option flex h-9 w-full items-center rounded-[9px] pl-5 pr-3 text-left text-[#171719] ${active || hovered ? "bg-[#eef0f4]" : ""}`}>
                    {option.label}
                  </button>
                );
              })}
            </div>
          )}
          <button type="button" onClick={() => setModelOpen((current) => !current)} className="confirm-model-button relative h-10 w-[224px] rounded-[12px] border border-[#e8ebef] bg-white px-4 text-left">
            <b className="confirm-model-label text-[#171719]">模型</b><span className="confirm-model-value ml-4 text-[#171719]">{modelLabel}</span><span className={`report-model-arrow ${modelOpen ? "rotate-right" : ""}`} />
          </button>
        </div>
        <Button kind="purple" className="report-top-action-button w-[132px] rounded-[12px]" onClick={() => void confirm()}>确认提交</Button>
      </div>
      <Card className="absolute left-[307px] top-[220px] h-[161px] w-[1206px] p-5">
        <h2 className="text-[18px] font-bold">项目信息 <button type="button" className="app-action-button float-right h-6 px-0 text-[#6c4dff]" onClick={() => void toggleInfoEditing()}><span className="text-[#6c4dff]"><EditIcon /></span>{infoEditing ? "完成编辑" : "编辑"}</button></h2>
        <div className="mt-3 text-[12px] leading-5 text-[#53565e]">
          <div className="grid grid-cols-5 gap-6 pr-[120px]">
            <ConfirmInfoField editing={infoEditing} label="项目名称" value={draft.name} fallback="未命名项目" onChange={(value) => setDraftField("name", value)} />
            <ConfirmInfoField editing={infoEditing} label="建筑类型" value={draft.buildingType} fallback="未选择" onChange={(value) => setDraftField("buildingType", value)} />
            <ConfirmInfoField editing={infoEditing} label="基地位置" value={draft.siteLocation} fallback="未填写" onChange={(value) => setDraftField("siteLocation", value)} />
            <ConfirmInfoField editing={infoEditing} label="设计年级" value={draft.grade} fallback="未选择" onChange={(value) => setDraftField("grade", value)} />
            <ConfirmInfoField editing={infoEditing} label="设计阶段" value={draft.designStage} fallback="方案阶段" onChange={(value) => setDraftField("designStage", value)} />
          </div>
          <div className="mt-3 grid grid-cols-[56px_minmax(0,1fr)] gap-3 pr-[120px]">
            <b className="text-[#53565e]">设计说明</b>
            {infoEditing ? (
              <textarea value={descriptionText} onChange={(event) => setDraftField("description", event.target.value)} className="report-light-scroll h-[60px] w-full min-w-0 resize-none overflow-y-auto bg-transparent p-0 text-[12px] leading-5 text-[#53565e] outline-none" />
            ) : (
              <div className="report-light-scroll max-h-[60px] min-w-0 overflow-y-auto pr-2 leading-5 text-[#53565e]">{descriptionText || "未填写"}</div>
            )}
          </div>
        </div>
      </Card>
      <Card className="absolute left-[307px] top-[400px] h-[176px] w-[1206px] p-5">
        <h2 className="text-[18px] font-bold">已上传图纸<button type="button" className="app-action-button float-right h-6 px-0 text-[#6c4dff]" onClick={() => go("upload")}><span className="text-[#6c4dff]"><EditIcon /></span>编辑</button></h2>
        {drawings.length ? (
          <div className="mt-4 grid grid-cols-6 gap-7">
            {drawings.map((item) => (
              <div className="h-[94px] rounded-[8px] border border-[#e8ebef] bg-white p-2" key={item.id}>
                <img className="h-[50px] w-full object-cover" src={apiUrl(item.file_url)} />
                <b className="mt-2 block truncate text-[10px]">{item.original_name}</b>
              </div>
            ))}
          </div>
        ) : <p className="mt-8 text-[13px] text-[#9a9ea7]">还没有上传图纸。</p>}
      </Card>
      <Card className="absolute left-[307px] top-[594px] h-[210px] w-[1206px] p-5">
        <h2 className="text-[18px] font-bold">选择的 AI Agent</h2>
        <div className="report-light-scroll mt-3 flex gap-10 overflow-x-auto pb-2">
          {enabledAgentCards.map((agent) => (
            <div className="relative h-[128px] w-[250px] shrink-0 overflow-hidden rounded-[10px] border border-[#e8ebef] bg-[#fafbfc] p-3" key={agent.type}>
              <b className="text-[12px]">{agent.display}</b>
              <p className="mt-1 w-[112px] text-[11px] leading-4 text-[#53565e]">{agent.desc}</p>
              <img className="absolute bottom-0 right-0 h-[116px] w-[116px] object-contain" src={agent.image} />
            </div>
          ))}
        </div>
      </Card>
      {error && <FlowErrorCard message={error} onClose={() => setError("")} />}
    </div>
  );
}

// 渲染确认页内可原地编辑的一项文本。
function ConfirmInfoField({ editing, label, value, fallback, onChange }: { editing: boolean; label: string; value: string; fallback: string; onChange: (value: string) => void }) {
  return (
    <p className="grid grid-cols-[56px_minmax(0,1fr)] gap-3">
      <b className="text-[#53565e]">{label}</b>
      {editing
        ? <input value={value} onChange={(event) => onChange(event.target.value)} className="min-w-0 bg-transparent p-0 text-[12px] leading-5 text-[#53565e] outline-none" />
        : <span className="min-w-0 truncate text-[#53565e]">{value || fallback}</span>}
    </p>
  );
}

// 渲染确认信息区块。
function ConfirmBlock({ title, lines }: { title: string; lines: string[] }) {
  return (
    <section className="min-h-[174px] rounded-[16px] border border-[#e8ebef] bg-white p-4">
      <b className="text-[15px]">{title}</b>
      <div className="mt-3 space-y-2 text-[13px] text-[#53565e]">{lines.map(line => <p key={line}>· {line}</p>)}</div>
    </section>
  );
}

// 渲染 AI 评图等待页。
export function ProcessingPage({ go }: PageProps) {
  const { draft, evaluation, report, pauseEvaluation } = useWorkspace();
  const completedCount = evaluation.completedAgents.length;
  const totalAgentCount = Math.max(draft.enabledAgents.length, 1);
  const progress = evaluation.running || evaluation.progress ? evaluation.progress : 70;
  const rows = [
    ["资料校验", "8 个文件已完成读取", completedCount > 0 ? "完成" : "分析中"],
    ["基地响应分析", "正在识别周边关系与场地界面", completedCount > 1 ? "完成" : completedCount > 0 ? "分析中" : "等待"],
    ["流线与功能组织", "等待基地分析完成后接续", completedCount > 2 ? "完成" : completedCount > 1 ? "分析中" : "等待"],
    ["生成评图报告", "等待前序分析完成", report ? "完成" : completedCount > 2 ? "分析中" : "等待"],
  ];
  return (
    <div className="relative h-full w-full overflow-hidden bg-[#f4f6f8]">
      <Sidebar go={go} creating />
      <PageTitle title="正在评图" subtitle="Agent 正在围绕图纸协同工作，右侧会实时同步评图进度。" />
      <div className="font-inter absolute left-[1246px] top-[99px] flex gap-[19px]">
        <Button kind="white" className="w-[116px] font-semibold" onClick={() => void pauseEvaluation().then(() => go("confirm"))}>暂停评图</Button>
        <Button kind="purple" className="w-[132px] rounded-[12px] font-semibold" onClick={() => report ? go("report") : window.alert("报告尚未生成。")}>查看评图报告</Button>
      </div>
      <Card className="absolute left-[307px] top-[149px] h-[658px] w-[760px]">
        <h2 className="absolute left-[39px] top-[23px] text-[26px] font-bold leading-[34px]">Agent 协同评图中</h2>
        <p className="absolute left-[39px] top-[63px] text-[14px] leading-[22px] text-[#6b7280]">系统正在按当前阶段组织 Agent 协同分析你的方案。</p>
        <div className="absolute left-[39px] top-[122px] flex h-[384px] w-[680px] items-center justify-center overflow-hidden rounded-[22px] border border-[#e8ebef] bg-[#f7f7ff]"><img className="h-[336px] w-[628px] object-contain" src="/assets/v1/processing-scene.png" /></div>
        <div className="absolute left-[39px] top-[545px] grid w-[680px] grid-cols-3 gap-[22px]"><Metric value={`${progress}%`} text="总体进度" tone="purple" /><Metric value={`${completedCount || Math.min(3, totalAgentCount)} / ${totalAgentCount}`} text="已完成Agent" tone="green" /><Metric value="2:18" text="预计剩余" tone="coral" /></div>
      </Card>
      <Card className="absolute left-[1089px] top-[149px] h-[658px] w-[424px] overflow-hidden">
        <h2 className="absolute left-[23px] top-[23px] text-[22px] font-bold leading-[29px]">评图进度</h2>
        <p className="absolute left-[23px] top-[57px] text-[12px] leading-[18px] text-[#9a9ea7]">系统会在每个分析节点完成后自动更新。</p>
        <div id="processing-scroll-area" className="figma-scroll-content absolute left-[17px] top-[98px] h-[389px] w-[330px] overflow-y-auto">
          <div className="flex gap-[10px]"><img className="h-[38px] w-[38px]" src="/assets/v1/report-avatar.svg" /><p className="h-[62px] w-[270px] rounded-[14px] border border-[#e8ebef] bg-white px-[14px] py-[10px] text-[12px] leading-[19px]">已接收图纸与任务书，正在组织 {totalAgentCount} 个 Agent 分工评审。</p></div>
          <div className="ml-[14px] mt-[36px] w-[316px] space-y-3">{rows.map(([title, desc, status]) => <ProgressRow key={title} title={title} desc={desc} status={status} active={status === "分析中"} />)}</div>
        </div>
        <FigmaScrollbar className="right-[7px] top-[73px] h-[500px]" thumbClassName="top-[18px] h-[169px]" />
        <ChatInput />
      </Card>
    </div>
  );
}

// 渲染等待页统计卡。
function Metric({ value, text, tone }: { value: string; text: string; tone: "purple" | "green" | "coral" }) {
  const colors = { purple: "text-[#6c4dff]", green: "text-[#22c55e]", coral: "text-[#ff5570]" };
  return <div className="font-inter h-[74px] rounded-[12px] border border-[#e8ebef] bg-[#fafbfc] px-4 py-3"><b className={`text-[20px] leading-[26px] ${colors[tone]}`}>{value}</b><p className="text-[12px] leading-[16px] text-[#6b7280]">{text}</p></div>;
}

// 渲染等待页步骤行。
function ProgressRow({ title, desc, status, active }: { title: string; desc: string; status: string; active?: boolean }) {
  return <div className={`h-[74px] rounded-[14px] border p-3 ${active ? "border-[#d9ceff] bg-[#fbfaff]" : "border-[#e8ebef] bg-white"}`}><b className="text-[13px]">{active ? "● " : "● "}{title}</b><span className={`float-right rounded-full px-3 py-1 text-[11px] ${active ? "bg-[#efe9ff] text-[#6c4dff]" : "bg-[#f4f6f8] text-[#6b7280]"}`}>{status}</span><p className="ml-4 mt-1 text-[11px] text-[#9a9ea7]">{desc}</p></div>;
}

// 渲染等待页底部对话输入。
function ChatInput() {
  const [question, setQuestion] = useState("");
  const { draft, sendQuestion } = useWorkspace();
  const modelLabel = draft.modelProvider === "gemini" ? "gemini-2.5-flash" : "qwen3.6-plus";
  const submit = async () => {
    if (!question.trim()) return;
    setQuestion("");
    await sendQuestion(question);
  };
  return <div className="absolute left-[25px] top-[501px] h-[129px] w-[320px] rounded-[12px] border border-[#e8ebef] bg-[#f8fafc] px-[13px] py-[7px] text-[12px] text-[#8b95a1]"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="继续追问评图进度..." className="h-[62px] w-full resize-none bg-transparent outline-none placeholder:text-[#8b95a1]" /><div className="font-inter absolute bottom-[9px] left-[8px] h-[27px] w-[226px] rounded-[8px] border border-[#e8ebef] bg-white px-[15px] py-[5px] leading-4">模型　<b className="ml-1 text-[13px] text-[#171719]">{modelLabel}</b></div><Button className="font-inter absolute bottom-[9px] right-[12px] h-[27px] w-[57px] px-2 text-[13px] font-semibold" onClick={() => void submit()}>发送</Button></div>;
}
