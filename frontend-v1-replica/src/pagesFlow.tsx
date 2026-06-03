// 流程页面：复刻项目首页、新建表单、上传图纸、Agent 选择、确认和等待页。
import { useEffect, useRef, useState, type PropsWithChildren } from "react";
import type { PageProps } from "./App";
import { apiUrl } from "./api/client";
import { Badge, Button, Card, Field, FigmaScrollbar, FlowActions, PageTitle, PlanThumb, Sidebar, Steps } from "./components";
import { useProfile } from "./state/profile";
import { getCachedProjectGroups, getLatestVersion, loadProjectGroups, type ProjectGroup } from "./state/projectGroups";
import { useWorkspace } from "./state/workspace";
import type { DrawingFile } from "./types/api";

const drawingNames = ["总平面图.pdf", "首层平面图.jpg", "二层平面图.jpg", "总平面图.pdf", "首层平面图.jpg", "二层平面图.jpg", "总平面图.pdf", "首层平面图.jpg", "二层平面图.jpg"];
const agentCards = [
  ["场地 Agent", "分析建筑与城市、场地和环境的关系", "/assets/v1/agent-site.png"],
  ["功能与流线 Agent", "检查空间组织、使用路径和流线关系", "/assets/v1/agent-flow.png"],
  ["几何形式 Agent", "识别体量、秩序、比例和空间形式", "/assets/v1/agent-form.png"],
  ["结构 Agent", "核对结构逻辑、跨度和构造合理性", "/assets/v1/agent-structure.png"],
];

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
];

const guideItems = [
  { title: "操作指引：完成第一次 AI 评图", detail: "点击“+ 新建评图”，填写项目信息，选择项目阶段与 Agent，上传图纸并确认提交。报告生成后，可继续查看问题详情和知识库依据。" },
  { title: "常见问题：为什么报告仍在生成？", detail: "真实模型需要依次读取图纸并完成专项分析。请在等待页查看进度；如果暂时不需要继续，可点击“暂停评图”。" },
  { title: "常见问题：如何继续下一轮修改？", detail: "可以从已有项目继承资料，复用项目信息、最近一次图纸和 Agent 设置，再上传调整后的图纸继续评图。" },
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

  useEffect(() => {
    let mounted = true;
    setDashboardProjects(getCachedProjectGroups(projects));
    void loadProjectGroups(projects).then((groups) => mounted && setDashboardProjects(groups));
    return () => { mounted = false; };
  }, [projects]);

  // 打开首页中的项目，并进入当前状态对应页面。
  const openDashboardProject = async (item: ProjectGroup) => {
    const latest = getLatestVersion(item);
    if (!latest) {
      await openProject(item.latestProject.id);
      go("confirm");
      return;
    }
    await openSubmission(latest.submission.id);
    if (latest.history?.overall_score != null || latest.submission.status === "completed") go("report");
    else if (latest.submission.status === "evaluating") go("processing");
    else go("confirm");
  };

  return (
    <div className="font-chat relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} />
      <PageTitle title={`欢迎回来，${profile.displayName}`} subtitle="继续提交图纸，或查看历史评图趋势。" />
      <section className="figma-shadow absolute left-[307px] top-[183px] h-[624px] w-[803px] rounded-[18px] border border-[#e8ebef] bg-white">
        <h2 className="absolute left-[23px] top-[23px] text-[18px] font-bold leading-6">最近评图项目</h2>
        <p className="absolute left-[23px] top-[51px] text-[12px] text-[#6b7280]">查看正在进行、待确认和已完成的设计评图。</p>
        {dashboardProjects.length === 0 ? <DashboardEmpty /> : (
          <>
            <div className="absolute left-[24px] top-[92px] grid grid-cols-2 gap-x-[24px] gap-y-[24px]">
              {dashboardProjects.slice(0, 4).map((item) => <DashboardProjectCard item={item} progress={item.projects.some((project) => project.id === activeProject?.id) ? evaluation.progress : 0} key={item.key} onOpen={() => void openDashboardProject(item)} />)}
            </div>
            <div className="absolute bottom-[24px] left-[24px] flex h-[34px] w-[748px] items-center rounded-[10px] bg-[#f7f8fa] px-4 text-[12px] text-[#6b7280]">
              最近更新：{dashboardProjects[0]?.name ?? "正在读取项目状态"} {getLatestVersion(dashboardProjects[0]) ? projectState(dashboardProjects[0]).description : "尚未提交评图资料"}
            </div>
          </>
        )}
      </section>
      <DashboardInformationCard title="公告" items={announcements.slice(0, 3)} className="top-[181px] h-[330px]" onDetail={setDetail} onMore={() => { setListTitle("历史公告"); setListItems(announcements); }} />
      <DashboardInformationCard title="新手引导" items={guideItems.slice(0, 2)} className="top-[532px] h-[275px]" onDetail={setDetail} onMore={() => { setListTitle("操作指引与常见问题"); setListItems(guideItems); }} />
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
      <span className={`absolute left-[18px] top-[20px] flex h-8 w-8 items-center justify-center rounded-full ${state.markerBackground}`}><span className={`h-[10px] w-[10px] rounded-full ${state.markerDot}`} /></span>
      <h3 className="absolute left-[64px] top-[18px] max-w-[202px] truncate text-[14px] font-bold leading-5 text-[#111318]">{item.name}</h3>
      <p className="absolute left-[64px] top-[42px] max-w-[202px] truncate text-[11px] font-medium leading-4 text-[#6b7280]">{latest?.submission.design_stage ?? "尚未选择阶段"} · {formatDate(latest?.submission.updated_at ?? latest?.submission.created_at ?? item.latestProject.created_at)}</p>
      <span className={`absolute right-[18px] top-[18px] flex h-6 min-w-[62px] items-center justify-center rounded-full px-3 text-[11px] font-bold ${state.badgeClass}`}>{state.label}</span>
      <span className="absolute left-[18px] top-[82px] text-[12px] font-medium text-[#6b7280]">{state.description}</span>
      <b className={`absolute left-[18px] top-[101px] text-[20px] leading-6 ${state.valueClass}`}>{state.value}</b>
      <button type="button" className="absolute bottom-[18px] right-[18px] h-[30px] w-[96px] rounded-[8px] border border-[#e8ebef] bg-white text-[12px] font-bold text-[#111318]" onClick={onOpen}>查看详情</button>
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
function DashboardInformationCard({ title, items, className, onDetail, onMore }: { title: string; items: InformationItem[]; className: string; onDetail: (item: InformationItem) => void; onMore: () => void }) {
  return (
    <Card className={`absolute left-[1146px] w-[324px] ${className}`}>
      <h2 className="absolute left-6 top-[19px] text-[22px] font-bold">{title}</h2>
      <div className="absolute left-6 right-6 top-[67px] space-y-2">
        {items.map((item) => (
          <div className="flex h-[42px] items-center border-b border-[#eef0f3] text-[12px]" key={item.title}>
            <b className="max-w-[206px] truncate">{item.title}</b>
            <button type="button" className="ml-auto text-[11px] font-bold text-[#6c4dff]" onClick={() => onDetail(item)}>详情</button>
          </div>
        ))}
      </div>
      <button type="button" className="absolute bottom-[18px] right-6 text-[12px] font-bold text-[#6c4dff]" onClick={onMore}>查看更多</button>
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
        <h2 className="text-[22px] font-bold">{title}</h2>
        <button type="button" className="absolute right-6 top-6 flex h-7 w-7 items-center justify-center rounded-full border border-[#e8ebef] text-[18px] text-[#9a9ea7]" onClick={onClose}>×</button>
        <div className="mt-6 space-y-3">
          {items.map((item) => <button type="button" className="flex h-[58px] w-full items-center rounded-[12px] border border-[#e8ebef] bg-[#fafbfc] px-4 text-left text-[13px] font-bold" onClick={() => onDetail(item)} key={item.title}>{item.title}<span className="ml-auto text-[11px] text-[#6c4dff]">查看详情</span></button>)}
        </div>
      </section>
    </div>
  );
}

// 渲染新建方式浮层。
export function CreateModalPage({ go }: PageProps) {
  const { projects, inheritProject, resetDraft } = useWorkspace();
  return (
    <div className="relative h-full w-full">
      <ProjectsDashboard go={go} />
      <div className="absolute inset-0 bg-[#171719]/30" />
      <section className="figma-shadow absolute left-[474px] top-[188px] h-[414px] w-[588px] rounded-[24px] border border-[#e8ebef] bg-white px-8 py-7">
        <h2 className="text-[22px] font-bold leading-8">选择新建评图方式</h2>
        <button className="absolute right-8 top-7 flex h-7 w-7 items-center justify-center rounded-full border border-[#e8ebef] bg-[#fafbfc] text-[18px] font-bold text-[#9a9ea7]" onClick={() => go("dashboard")}>×</button>
        <p className="mt-1 text-[13px] leading-5 text-[#53565e]">可以从零创建一个新项目，也可以继承已有项目资料继续评图。</p>
        <button className="absolute left-8 top-[115px] h-[210px] w-[250px] rounded-[16px] border-2 border-[#6c4dff] bg-[#fafbfc] p-5 text-left" onClick={() => { resetDraft(); go("info"); }}>
          <span className="flex h-12 w-12 items-center justify-center rounded-[14px] bg-[#efe9ff] text-[34px] font-light text-[#6c4dff]">＋</span>
          <b className="mt-4 block text-[17px]">新建项目</b>
          <span className="mt-2 block text-[12px] leading-5 text-[#53565e]">从空白项目信息开始，录入项目资料、上传图纸并选择评图 Agent。</span>
        </button>
        <button className="absolute right-8 top-[115px] h-[210px] w-[250px] rounded-[16px] border border-[#e8ebef] bg-[#fafbfc] p-5 text-left" onClick={() => projects[0] && void inheritProject(projects[0].id).then(() => go("info"))}>
          <span className="flex h-12 w-12 items-center justify-center rounded-[14px] bg-white text-[26px] text-[#6c4dff]">♧</span>
          <b className="mt-4 block text-[17px]">继承已有项目</b>
          <span className="mt-2 block text-[12px] leading-5 text-[#53565e]">复用已有项目基础信息、历史图纸和评图设置，快速进入下一轮分析。</span>
        </button>
        <Button className="absolute bottom-7 right-8 h-[30px] w-[112px] rounded-[8px] text-[12px]" onClick={() => { resetDraft(); go("info"); }}>开始新建</Button>
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
  const taskbookRef = useRef<HTMLInputElement>(null);
  const { attachments, draft, setDraftField, saveDraft, uploadTaskbook } = useWorkspace();
  return (
    <FlowShell go={go} title="新建评图" subtitle="先补充项目基础信息，后续报告会按这些信息生成评价语境。" current={1} projectName="未命名">
      <FlowActions go={go} next="agents" onSave={() => void saveDraft()} beforeNext={saveDraft} />
      <Card className="absolute left-[307px] top-[220px] h-[584px] w-[1154px] px-8 py-7">
        <h2 className="text-[22px] font-bold leading-7">项目基础信息</h2>
        <div className="mt-8 flex flex-wrap justify-between gap-y-4">
          <Field label="项目名称" value={draft.name} onChange={(value) => setDraftField("name", value)} />
          <Field label="建筑类型" value={draft.buildingType} onChange={(value) => setDraftField("buildingType", value)} />
          <Field label="基地位置" value={draft.siteLocation} onChange={(value) => setDraftField("siteLocation", value)} />
          <Field label="设计课程" value={draft.courseName} onChange={(value) => setDraftField("courseName", value)} />
          <label className="block w-full">
            <b className="mb-2 block text-[12px] leading-4 text-[#9a9ea7]">设计说明</b>
            <textarea value={draft.description} onChange={(event) => setDraftField("description", event.target.value)} className="h-[135px] w-full resize-none rounded-[12px] border border-[#e8ebef] bg-white px-[13px] py-[11px] text-[13px] outline-none" />
          </label>
        </div>
        <div className="mt-5 flex h-[112px] items-center rounded-[14px] border border-[#e8ebef] bg-white px-5">
          <div className="mr-6 flex h-11 w-11 items-center justify-center rounded-[12px] border border-[#e8ebef] bg-[#fafbfc] text-[20px]">▤</div>
          <div className="w-[290px]"><h3 className="text-[14px] font-bold">上传任务书</h3><p className="mt-1 text-[12px] text-[#9a9ea7]">用于补充设计任务、评图重点和课程要求</p></div>
          <FileRow name={attachments[0]?.original_name ?? "设计任务书.pdf"} meta="2.4 MB" status="已上传" />
          <FileRow name={attachments[1]?.original_name ?? "任务书补充.docx"} meta="上传中 68%" status={attachments[1] ? "已上传" : "上传中"} />
          <input ref={taskbookRef} className="hidden" type="file" accept=".pdf,.doc,.docx,.txt" onChange={(event) => event.target.files?.[0] && void uploadTaskbook(event.target.files[0])} />
          <Button className="ml-6 w-[136px]" onClick={() => taskbookRef.current?.click()}>上传/替换</Button>
        </div>
      </Card>
    </FlowShell>
  );
}

// 渲染任务书文件行。
function FileRow({ name, meta, status }: { name: string; meta: string; status: string }) {
  return (
    <div className="mr-5 h-[77px] w-[210px] rounded-[12px] border border-[#e8ebef] bg-[#fafbfc] px-3 py-3 text-[12px]">
      <b className="block">{name} <span className="float-right rounded-full bg-[#e6f8ed] px-2 py-1 text-[10px] text-[#22c55e]">{status}</span></b><span className="mt-1 block text-[#9a9ea7]">{meta}</span>
    </div>
  );
}

// 渲染阶段与 Agent 选择页。
export function AgentsPage({ go }: PageProps) {
  const { draft, setDraftField, toggleAgent, saveDraft } = useWorkspace();
  return (
    <FlowShell go={go} title="选择阶段与 Agent" subtitle="系统会根据项目阶段自动调整评价重点与 Agent 协作方式。" current={2}>
      <div className="absolute right-[106px] top-[156px] flex gap-5"><Button kind="white" className="w-[109px]" onClick={() => go("info")}>上一步</Button><Button kind="purple" className="w-[110px] rounded-[16px]" onClick={() => void saveDraft().then(() => go("upload"))}>下一步</Button></div>
      <Card className="absolute left-[307px] top-[224px] h-[579px] w-[521px] p-7">
        <h2 className="text-[22px] font-bold">选择项目阶段</h2>
        <div className="mt-7 space-y-9">
          <StageCard title="概念阶段" desc="概念立意、空间构想、场地阅读" active={draft.designStage === "概念阶段"} onClick={() => setDraftField("designStage", "概念阶段")} />
          <StageCard title="方案阶段" desc="场地回应、功能流线、形式构图、结构可行性" active={draft.designStage === "方案阶段"} onClick={() => setDraftField("designStage", "方案阶段")} />
          <StageCard title="图纸阶段" desc="图面表达、排版质量、方案完整度" active={draft.designStage === "图纸阶段"} onClick={() => setDraftField("designStage", "图纸阶段")} />
        </div>
      </Card>
      <Card className="absolute left-[858px] top-[224px] h-[579px] w-[571px] p-7">
        <h2 className="text-[22px] font-bold">选择 Agent</h2>
        <div className="mt-6 grid grid-cols-2 gap-6">
          {agentCards.map(([name, desc, image], index) => <AgentTile key={name} name={name} desc={desc} image={image} active={draft.enabledAgents.includes(DEFAULT_AGENT_TYPES[index])} onClick={() => toggleAgent(DEFAULT_AGENT_TYPES[index])} />)}
        </div>
      </Card>
    </FlowShell>
  );
}

// 渲染阶段选项。
function StageCard({ title, desc, active, onClick }: { title: string; desc: string; active?: boolean; onClick?: () => void }) {
  return <button type="button" onClick={onClick} className={`relative block h-[130px] w-full rounded-[18px] border p-5 text-left ${active ? "border-[#6c4dff] bg-[#efe9ff]" : "border-[#e8ebef] bg-white"}`}><b className="text-[18px]">{title}</b><p className="mt-2 text-[13px] text-[#53565e]">{desc}</p><span className={`absolute right-6 top-[30px] rounded-full px-4 py-2 text-[12px] font-bold ${active ? "text-[#6c4dff]" : "bg-[#e6f0ff] text-[#3b82f6]"}`}>{active ? "当前选择" : "可选"}</span></button>;
}

// 渲染 Agent 选项。
const DEFAULT_AGENT_TYPES = ["site_agent", "function_agent", "form_agent", "structure_agent"];

function AgentTile({ name, desc, image, active = true, onClick }: { name: string; desc: string; image: string; active?: boolean; onClick?: () => void }) {
  const display = name === "场地 Agent" ? "场地与回应" : name === "功能与流线 Agent" ? "功能与流线" : name === "几何形式 Agent" ? "形式与构图" : "结构与可行性";
  return <button type="button" onClick={onClick} className={`relative h-[220px] overflow-hidden rounded-[18px] border p-4 text-left ${active ? "border-[#6c4dff] bg-[#efe9ff]" : "border-[#e8ebef] bg-white"}`}><b className={`text-[12px] ${active ? "text-[#6c4dff]" : "text-[#9a9ea7]"}`}>{active ? "已启用" : "可选"}</b><h3 className="mt-5 text-[18px] font-bold">{display}</h3><p className="mt-2 w-[118px] text-[12px] leading-[18px] text-[#53565e]">{desc.replace("分析建筑与城市、场地和环境的关系", "分析基地、交通、城市界面与环境响应。").replace("检查空间组织、使用路径和流线关系", "检查功能组织、动线效率和公共性。").replace("识别体量、秩序、比例和空间形式", "评价体量、立面逻辑和空间表达。").replace("核对结构逻辑、跨度和构造合理性", "发现影响落地的结构和尺度问题。")}</p><img className="absolute bottom-0 right-1 h-[132px] w-[132px] object-contain" src={image} /></button>;
}

// 渲染上传图纸页。
export function UploadPage({ go }: PageProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const { drawings, selectedDrawingId, selectDrawing, uploadFiles, saveDraft, updateSelectedDrawing, deleteSelectedDrawing, deleteAllDrawings } = useWorkspace();
  const selected = drawings.find((item) => item.id === selectedDrawingId) ?? drawings[0];
  const visibleDrawings = drawings.length ? drawings : drawingNames;
  const selectedIndex = selected ? drawings.findIndex((item) => item.id === selected.id) : 0;
  return (
    <FlowShell go={go} title="上传设计图纸" subtitle="上传您的设计图纸，AI 将基于多维度为您提供专业评审建议。" current={3}>
      <FlowActions go={go} previous="agents" next="confirm" onSave={() => void saveDraft()} beforeNext={saveDraft} />
      <Card className="absolute left-[315px] top-[202px] h-[601px] w-[730px] overflow-hidden">
        <div id="upload-scroll-area" className="figma-scroll-content absolute inset-0 overflow-y-auto p-[19px]">
          <div className="flex items-center"><Button className="w-[117px]" onClick={() => inputRef.current?.click()}>上传文件　⌄</Button>
          <input ref={inputRef} className="hidden" type="file" accept="image/*" multiple onChange={(event) => event.target.files && void uploadFiles(event.target.files)} />
          <Button kind="white" className="ml-[29px] w-[104px]" onClick={() => drawings.length && window.confirm("确认删除全部已上传图纸？") && void deleteAllDrawings()}>批量删除</Button>
          <span className="ml-auto text-[12px] text-[#9a9ea7]">{drawings.length ? `已上传 ${drawings.length} 张图纸` : "已上传 6 张图纸，1 张正在上传"}</span></div>
          <div className="mt-4 grid grid-cols-3 gap-[14px]">
            {visibleDrawings.map((item, index) => typeof item === "string"
              ? <DrawingCard key={`${item}-${index}`} name={item} index={index} />
              : <DrawingCard key={item.id} name={item.original_name} index={index} drawing={item} selected={item.id === (selected?.id ?? drawings[0]?.id)} onClick={() => selectDrawing(item.id)} />)}
          </div>
        </div>
        <FigmaScrollbar className="right-[10px] top-[75px] h-[589px]" thumbClassName="h-[168px]" />
      </Card>
      <Card className="absolute left-[1080px] top-[202px] h-[601px] w-[390px] px-[27px] py-[19px]">
        <p className="text-[12px] text-[#9a9ea7]">已选中 1 张图纸</p>
        <img className="mt-4 h-[186px] w-[334px] object-cover" src={selected ? apiUrl(selected.file_url) : "/assets/v1/upload-plan.svg"} />
        <h2 className="mt-4 text-[20px] font-bold">{selected?.original_name ?? "总平面图.pdf"}</h2>
        <p className="mt-1 text-[12px] text-[#9a9ea7]">上传时间 <span className="float-right">2026/5/14</span></p>
        <b className="mt-4 block text-[12px] text-[#9a9ea7]">图纸类型</b>
        <label className="relative mt-2 block h-10 rounded-[12px] border border-[#e8ebef] bg-white px-3 py-[9px] text-[13px]">{drawingTypeLabel(selected?.drawing_type ?? "site")} <span className="float-right">▾</span><select value={selected?.drawing_type ?? "site"} onChange={(event) => void updateSelectedDrawing({ drawing_type: event.target.value })} className="absolute inset-0 cursor-pointer opacity-0"><option value="site">总平面图</option><option value="plan">首层平面图</option><option value="analysis">分析图</option><option value="render">效果图</option></select></label>
        <div className="mt-2 flex gap-6"><Button kind="white" className="w-[154px]" onClick={() => inputRef.current?.click()}>重新选择</Button><Button className="w-[155px]" onClick={() => selected && window.confirm("确认删除当前图纸？") && void deleteSelectedDrawing()}>删除</Button></div>
        <b className="mt-3 block text-[12px] text-[#9a9ea7]">图纸信息</b>
        <label className="relative mt-2 block h-[75px] rounded-[12px] border border-[#e8ebef] bg-white px-3 py-[11px] text-[13px] text-[#9a9ea7]"><textarea value={selected?.description ?? ""} placeholder="添加图纸说明信息" onChange={(event) => void updateSelectedDrawing({ description: event.target.value })} className="h-[48px] w-full resize-none bg-transparent outline-none placeholder:text-[#9a9ea7]" /><span className="absolute bottom-2 right-3 text-[11px]">{selected?.description?.length ?? 0}/200</span></label>
        <div className="mt-3 flex justify-end gap-2"><Button kind="ghost" className="h-7 w-[81px] px-2" onClick={() => drawings[selectedIndex - 1] && selectDrawing(drawings[selectedIndex - 1].id)}>上一张</Button><Button className="h-7 w-[81px] px-2" onClick={() => drawings[selectedIndex + 1] && selectDrawing(drawings[selectedIndex + 1].id)}>下一张</Button></div>
      </Card>
    </FlowShell>
  );
}

// 渲染上传图纸卡片。
function DrawingCard({ name, index, drawing, selected = index === 0, onClick }: { name: string; index: number; drawing?: DrawingFile; selected?: boolean; onClick?: () => void }) {
  const uploaded = index < 2;
  const uploading = index === 2;
  const label = drawing ? drawingTypeLabel(drawing.drawing_type) : index === 0 ? "总平面图" : index === 1 ? "首层平面图" : index === 2 ? "二层平面图" : "待识别";
  return (
    <article onClick={onClick} className="relative h-[220px] cursor-pointer rounded-[12px] border border-[#e8ebef] bg-white p-[13px]">
      <span className={`absolute left-[9px] top-[9px] flex h-3 w-3 items-center justify-center rounded-[3px] border text-[9px] ${selected ? "border-[#171719] bg-[#171719] text-white" : "border-[#171719] bg-white"}`}>{selected ? "✓" : ""}</span>
      <PlanThumb muted={index > 1} className="mt-[14px] h-[116px] w-[190px]" />
      <div className="mt-2 flex items-center justify-between"><b className="text-[14px]">{name}</b><span className="rounded-full bg-[#171719] px-3 py-1 text-[10px] font-bold text-white">{label}</span></div>
      <p className={`mt-2 border-t border-[#e8ebef] pt-2 text-[12px] ${drawing || uploaded ? "text-[#22c55e]" : uploading ? "text-[#3b82f6]" : "text-[#9a9ea7]"}`}>{drawing || uploaded ? "上传成功" : uploading ? "上传中 · 45%" : "等待处理"}</p>
    </article>
  );
}

// 把后端图纸类型转换为页面展示文字。
function drawingTypeLabel(type: string): string {
  return { site: "总平面图", plan: "首层平面图", analysis: "分析图", render: "效果图" }[type] ?? "待识别";
}

// 渲染提交确认页。
export function ConfirmPage({ go }: PageProps) {
  const { draft, drawings, setDraftField, startEvaluation } = useWorkspace();
  const confirm = () => {
    go("processing");
    void startEvaluation();
  };
  return (
    <div className="relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} creating />
      <PageTitle title="确认提交" subtitle="请确认以下信息，提交后系统将开始评图分析。" />
      <Steps current={4} order="confirm" />
      <div className="absolute right-[67px] top-[155px] flex gap-3"><Button kind="white" className="w-[115px]" onClick={() => go("upload")}>返回修改</Button><label className="relative h-10 w-[224px] rounded-[12px] border border-[#e8ebef] bg-white px-4 py-[10px] text-[12px] text-[#9a9ea7]">模型　<b className="text-[#171719]">ArchCritic Pro</b>　⌄<select value={`${draft.modelProvider}|${draft.modelName}`} onChange={(event) => { const [provider, model] = event.target.value.split("|"); setDraftField("modelProvider", provider); setDraftField("modelName", model); }} className="absolute inset-0 cursor-pointer opacity-0"><option value="mock|demo">ArchCritic Pro</option><option value="dashscope|qwen3.6-plus">ArchCritic Pro</option><option value="gemini|gemini-2.5-flash">ArchCritic Pro</option></select></label><Button kind="purple" className="w-[132px] rounded-[12px]" onClick={confirm}>确认提交</Button></div>
      <Card className="absolute left-[307px] top-[220px] h-[161px] w-[1161px] p-5">
        <h2 className="text-[18px] font-bold">项目信息 <button type="button" className="float-right text-[12px] text-[#6c4dff]" onClick={() => go("info")}>编辑</button></h2>
        <div className="mt-3 grid grid-cols-4 gap-6 text-[12px] leading-5 text-[#53565e]"><p>项目名称　　<b>{draft.name}</b><br />设计阶段　　<b>{draft.designStage}</b><br />项目地点　　<b>{draft.siteLocation}</b></p><p>项目编号　　<b>SH-20240520-001</b><br />建筑类型　　<b>{draft.buildingType}</b><br />建设单位　　<b>上海XX置业有限公司</b></p><p>建筑面积　　<b>45,000 m²</b><br />地上层数　　<b>22 层</b><br />建筑高度　　<b>98.5 m</b></p><p>设计单位　　<b>XX建筑设计事务所</b><br />设计负责人　<b>王建筑师</b></p></div>
      </Card>
      <Card className="absolute left-[307px] top-[400px] h-[176px] w-[1161px] p-5"><h2 className="text-[18px] font-bold">上传图纸（共 {drawings.length || 6} 张）<span className="float-right cursor-pointer text-[12px] text-[#6c4dff]" onClick={() => go("upload")}>编辑</span></h2><div className="mt-4 grid grid-cols-6 gap-7">{(drawings.length ? drawings.slice(0, 6) : ["总平面图.pdf","一层平面图.jpg","立面图_南立面.jpg","立面图_东立面.jpg","剖面图_A-A.jpg","效果图_01.jpg"]).map((item) => <div className="h-[94px] rounded-[8px] border border-[#e8ebef] bg-white p-2" key={typeof item === "string" ? item : item.id}>{typeof item === "string" ? <div className="h-[50px] bg-[#f4f6f8]" /> : <img className="h-[50px] w-full object-cover" src={apiUrl(item.file_url)} />}<b className="mt-2 block truncate text-[10px]">{typeof item === "string" ? item : item.original_name}</b></div>)}</div></Card>
      <Card className="absolute left-[307px] top-[594px] h-[210px] w-[1161px] p-5"><h2 className="text-[18px] font-bold">选择的 AI Agent（4 个）</h2><div className="mt-4 grid grid-cols-4 gap-10">{agentCards.map(([name, desc, image]) => <div className="relative h-[140px] overflow-hidden rounded-[10px] border border-[#e8ebef] bg-[#fafbfc] p-3" key={name}><b className="text-[12px]">{name.replace(" Agent","")}</b><p className="mt-1 w-[112px] text-[11px] leading-4 text-[#53565e]">{desc}</p><img className="absolute bottom-0 right-0 h-[130px] w-[130px] object-contain" src={image} /></div>)}</div></Card>
    </div>
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
  const { evaluation, report, pauseEvaluation } = useWorkspace();
  const completedCount = evaluation.completedAgents.length;
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
      <div className="font-inter absolute left-[1193px] top-[99px] flex gap-[19px]">
        <Button kind="white" className="w-[116px] font-semibold" onClick={() => void pauseEvaluation().then(() => go("confirm"))}>暂停评图</Button>
        <Button kind="purple" className="w-[132px] rounded-[12px] font-semibold" onClick={() => report ? go("report") : window.alert("报告尚未生成。")}>查看评图报告</Button>
      </div>
      <Card className="absolute left-[307px] top-[149px] h-[658px] w-[760px]">
        <h2 className="absolute left-[39px] top-[23px] text-[26px] font-bold leading-[34px]">Agent 协同评图中</h2>
        <p className="absolute left-[39px] top-[63px] text-[14px] leading-[22px] text-[#6b7280]">场地、流线、形式与结构四类 Agent 正在并行分析你的方案。</p>
        <div className="absolute left-[39px] top-[122px] flex h-[384px] w-[680px] items-center justify-center overflow-hidden rounded-[22px] border border-[#e8ebef] bg-[#f7f7ff]"><img className="h-[336px] w-[628px] object-contain" src="/assets/v1/processing-scene.png" /></div>
        <div className="absolute left-[39px] top-[545px] grid w-[680px] grid-cols-3 gap-[22px]"><Metric value={`${progress}%`} text="总体进度" tone="purple" /><Metric value={`${completedCount || 3} / 4`} text="已完成Agent" tone="green" /><Metric value="2:18" text="预计剩余" tone="coral" /></div>
      </Card>
      <Card className="absolute left-[1089px] top-[149px] h-[658px] w-[371px] overflow-hidden">
        <h2 className="absolute left-[23px] top-[23px] text-[22px] font-bold leading-[29px]">评图进度</h2>
        <p className="absolute left-[23px] top-[57px] text-[12px] leading-[18px] text-[#9a9ea7]">系统会在每个分析节点完成后自动更新。</p>
        <div id="processing-scroll-area" className="figma-scroll-content absolute left-[17px] top-[98px] h-[389px] w-[330px] overflow-y-auto">
          <div className="flex gap-[10px]"><img className="h-[38px] w-[38px]" src="/assets/v1/report-avatar.svg" /><p className="h-[62px] w-[270px] rounded-[14px] border border-[#e8ebef] bg-white px-[14px] py-[10px] text-[12px] leading-[19px]">已接收图纸与任务书，正在组织 4 个 Agent 分工评审。</p></div>
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
  const { sendQuestion } = useWorkspace();
  const submit = async () => {
    if (!question.trim()) return;
    setQuestion("");
    await sendQuestion(question);
  };
  return <div className="absolute left-[25px] top-[501px] h-[129px] w-[320px] rounded-[12px] border border-[#e8ebef] bg-[#f8fafc] px-[13px] py-[7px] text-[12px] text-[#8b95a1]"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="继续追问评图进度..." className="h-[62px] w-full resize-none bg-transparent outline-none placeholder:text-[#8b95a1]" /><div className="font-inter absolute bottom-[9px] left-[8px] h-[27px] w-[226px] rounded-[8px] border border-[#e8ebef] bg-white px-[15px] py-[5px] leading-4">模型　<b className="ml-1 text-[13px] text-[#171719]">ArchCritic Pro</b></div><Button className="font-inter absolute bottom-[9px] right-[12px] h-[27px] w-[57px] px-2 text-[13px] font-semibold" onClick={() => void submit()}>发送</Button></div>;
}
