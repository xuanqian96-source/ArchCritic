// 项目建立流程：项目首页、新建方式和任务书信息录入。
import { useEffect, useRef, useState, type ChangeEvent, type CSSProperties } from "react";
import type { PageProps } from "../App";
import { Button, Card, FlowActions, FlowErrorCard, PageTitle, Sidebar } from "../components";
import { readSubmissionRoute } from "../state/flowRoutes";
import { useProfile } from "../state/profile";
import { getCachedProjectGroups, getLatestVersion, loadProjectGroups, PINNED_PROJECTS_CHANGED_EVENT, readPinnedProjectIds, sortPinnedProjectGroups, type ProjectGroup, type ProjectVersion } from "../state/projectGroups";
import { getScoreLevel } from "../scoreLevels";
import { useWorkspace } from "../state/workspace";
import type { Attachment } from "../types/api";
import { announcements, buildingTypeOptions, FlowShell, gradeOptions, guideItems, type InformationItem, saveDraftAtRoute, useRememberFlowRoute, validateProjectInfoStep, validateUniqueProjectName } from "./flowShared";

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

interface DashboardProjectState {
  label: string;
  description: string;
  value: string;
  badgeClass: string;
  valueClass: string;
  markerBackground: string;
  markerDot: string;
  badgeStyle?: CSSProperties;
  valueStyle?: CSSProperties;
  markerBackgroundStyle?: CSSProperties;
  markerDotStyle?: CSSProperties;
}

// 渲染首页项目卡片。
function DashboardProjectCard({ item, progress, onOpen }: { item: ProjectGroup; progress: number; onOpen: () => void }) {
  const state = projectState(item, progress);
  const latest = getLatestVersion(item);
  return (
    <article className="figma-shadow relative h-[140px] w-[366px] rounded-[12px] border border-[#e8ebef] bg-[#fafbfc]">
      <span className={`absolute left-[18px] top-[20px] flex h-8 w-8 items-center justify-center rounded-full ${state.markerBackground}`} style={state.markerBackgroundStyle}><span className={`project-status-dot h-[10px] w-[10px] rounded-full ${state.markerDot}`} style={state.markerDotStyle} /></span>
      <h3 className="project-card-title-text absolute left-[64px] top-[17px] max-w-[202px] truncate">{item.name}</h3>
      <p className="absolute left-[64px] top-[43px] max-w-[202px] truncate text-[11px] font-medium leading-4 text-[#6b7280]">{latest?.submission.design_stage ?? "尚未选择阶段"} · {formatDate(latest?.submission.updated_at ?? latest?.submission.created_at ?? item.latestProject.created_at)}</p>
      <span className={`absolute right-[18px] top-[18px] flex h-6 min-w-[62px] items-center justify-center rounded-full px-3 text-[11px] font-bold ${state.badgeClass}`} style={state.badgeStyle}>{state.label}</span>
      <span className="absolute left-[18px] top-[82px] text-[12px] font-medium text-[#6b7280]">{state.description}</span>
      <b className={`absolute left-[18px] top-[101px] text-[20px] leading-6 ${state.valueClass}`} style={state.valueStyle}>{state.value}</b>
      <button type="button" className="absolute bottom-[18px] right-[18px] flex h-[30px] w-[96px] items-center justify-center rounded-[8px] border border-[#e8ebef] bg-white text-[#111318]" onClick={onOpen}><span className="project-detail-button-text">查看详情</span></button>
    </article>
  );
}

// 根据最新提交和报告生成首页状态文字。
function projectState(item: ProjectGroup, progress = 0): DashboardProjectState {
  const latest = getLatestVersion(item);
  if (latest?.history?.overall_score != null || latest?.submission.status === "completed") {
    const score = latest.history?.overall_score ?? 0;
    const level = getScoreLevel(score);
    return {
      label: "已完成",
      description: "报告完成",
      value: String(Math.round(score)),
      badgeClass: "",
      valueClass: "",
      markerBackground: "",
      markerDot: "",
      badgeStyle: { backgroundColor: level.softColor, color: level.darkColor },
      valueStyle: { color: level.darkColor },
      markerBackgroundStyle: { backgroundColor: level.softColor },
      markerDotStyle: { backgroundColor: level.color },
    };
  }
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
  const { attachments, deleteTaskbook, draft, project, projects, setDraftField, saveDraft, uploadTaskbook } = useWorkspace();
  const [editingTaskbook, setEditingTaskbook] = useState(false);
  const [openSelect, setOpenSelect] = useState<"building" | "grade" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Attachment | null>(null);
  const [error, setError] = useState("");
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
    setOpenSelect(null);
  };
  const validateAndContinue = () => {
    validateProjectInfoStep(draft, attachments);
    validateUniqueProjectName(draft.name, projects, project?.id);
  };
  const handleTaskbookChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    setError("");
    try {
      validateUniqueProjectName(draft.name, projects, project?.id);
      await uploadTaskbook(file);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "任务书上传失败，请稍后重试。");
    }
  };
  return (
    <FlowShell go={go} title="新建评图" subtitle="填写项目基础信息，并上传任务书。" current={1} projectName="未命名">
      <FlowActions go={go} next="agents" onSave={() => saveDraftAtRoute(saveDraft, "info")} beforeNext={validateAndContinue} />
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
          <div className="w-[310px]"><h3 className="text-[14px] font-bold">上传任务书</h3><p className="mt-1 text-[12px] text-[#9a9ea7]">支持带文字的 PDF、DOCX 或 TXT，不支持扫描图片和旧版 DOC。</p></div>
          <div className="flex min-w-0 flex-1 gap-4">
            {attachments.length ? attachments.slice(0, 2).map((item) => <FileRow name={item.original_name} meta={item.extracted_text_preview ? `已读取：${item.extracted_text_preview}` : "没有读取到文字，请重新上传可复制文字的文件"} status={item.extraction_status === "ready" ? "已读取" : "读取失败"} editing={editingTaskbook} onDelete={() => setDeleteTarget(item)} key={item.id} />) : <span className="self-center text-[12px] text-[#9a9ea7]">暂未上传任务书</span>}
          </div>
          <input ref={taskbookRef} className="hidden" type="file" accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" onChange={(event) => void handleTaskbookChange(event)} />
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
      {error && <FlowErrorCard title="项目名称已被使用" message={error} onClose={() => setError("")} />}
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
        <div className="flow-popover report-light-scroll figma-shadow absolute left-0 right-0 top-[68px] z-20 max-h-[184px] overflow-y-auto rounded-[12px] border border-[#e8ebef] bg-white p-1 pr-2">
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
  const ready = status === "已读取";
  return (
    <div className="relative h-[77px] w-[210px] shrink-0 rounded-[12px] border border-[#e8ebef] bg-[#fafbfc] px-3 py-3 text-[12px]">
      {editing && <button type="button" aria-label="删除附件" className="absolute -right-3 -top-3 flex h-7 w-7 items-center justify-center rounded-full border border-[#d9dde3] bg-white text-[18px] font-bold leading-none text-[#171719] hover:bg-[#eef0f4]" onClick={onDelete}>×</button>}
      <b className="block">{name} <span className={`float-right rounded-full px-2 py-1 text-[10px] ${ready ? "bg-[#e6f8ed] text-[#22c55e]" : "bg-[#fff0ee] text-[#d94b3d]"}`}>{status}</span></b><span className="mt-1 block text-[#9a9ea7]">{meta}</span>
    </div>
  );
}

// 渲染任务书删除确认卡片。
export function TaskbookDeleteCard({ fileName, onClose, onConfirm }: { fileName: string; onClose: () => void; onConfirm: () => Promise<void> }) {
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
export function EditIcon() {
  return <svg viewBox="0 0 20 20" className="mr-2 h-4 w-4 fill-none stroke-current stroke-[1.8]"><path d="m4 13.8-.6 2.8 2.8-.6 8.4-8.4-2.2-2.2L4 13.8z" /><path d="m11.4 6.4 2.2 2.2" /></svg>;
}

// 渲染任务书上传按钮图标。
export function UploadIcon() {
  return <svg viewBox="0 0 20 20" className="mr-2 h-4 w-4 fill-none stroke-current stroke-[1.8]"><path d="M10 14V4" /><path d="m6.5 7.5 3.5-3.5 3.5 3.5" /><path d="M4 15.5h12" /></svg>;
}

// 渲染删除按钮图标。
export function TrashIcon() {
  return <svg viewBox="0 0 20 20" className="mr-2 h-4 w-4 fill-none stroke-current stroke-[1.8]"><path d="M4 6h12" /><path d="M8 6V4h4v2" /><path d="m6 8 .5 8h7l.5-8" /><path d="M9 10v4" /><path d="M11 10v4" /></svg>;
}

// 渲染阶段与 Agent 选择页。
