// 提交与评图流程：确认资料、启动评图并展示真实 Agent 进度。
import { useEffect, useMemo, useRef, useState } from "react";
import type { PageProps } from "../App";
import { apiUrl } from "../api/client";
import { Button, Card, FlowErrorCard, PageTitle, Sidebar, Steps } from "../components";
import { useWorkspace } from "../state/workspace";
import { EditIcon } from "./flowSetup";
import { collapseConfirmText, getAgentSpecs, getStageAgentTypes, useRememberFlowRoute, validateAgentStep, validateProjectInfoStep, validateUploadStep } from "./flowShared";

export function ConfirmPage({ go }: PageProps) {
  useRememberFlowRoute("confirm");
  const { attachments, draft, drawings, saveDraft, setDraftField, startEvaluation } = useWorkspace();
  const [infoEditing, setInfoEditing] = useState(false);
  const [infoSaving, setInfoSaving] = useState(false);
  const [error, setError] = useState("");
  const enabledAgentCards = getAgentSpecs(draft.enabledAgents);
  const descriptionText = collapseConfirmText(draft.description);
  const toggleInfoEditing = () => {
    if (infoSaving) return;
    if (!infoEditing) {
      setInfoEditing(true);
      return;
    }
    setError("");
    setInfoEditing(false);
    setInfoSaving(true);
    void saveDraft()
      .catch((saveError) => {
        setError(saveError instanceof Error ? saveError.message : "项目信息保存失败，请稍后重试。");
      })
      .finally(() => setInfoSaving(false));
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
    <div className="flow-page-motion relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} creating />
      <PageTitle title="确认提交" subtitle="请确认以下信息，提交后系统将开始评图分析。" />
      <Steps current={4} />
      <div className="absolute right-[23px] top-[155px] flex gap-3">
        <Button kind="white" className="report-top-action-button w-[115px]" onClick={() => go("upload")}>返回修改</Button>
        <div className="confirm-model-button flex h-10 w-[224px] items-center rounded-[12px] border border-[#e8ebef] bg-white px-4" title="当前统一使用千问模型">
          <b className="confirm-model-label text-[#171719]">模型</b><span className="confirm-model-value ml-4 text-[#171719]">qwen3.8-max</span>
        </div>
        <Button kind="purple" className="report-top-action-button w-[132px] rounded-[12px]" onClick={() => void confirm()}>确认提交</Button>
      </div>
      <Card className="absolute left-[307px] top-[220px] h-[161px] w-[1206px] p-5">
        <h2 className="text-[18px] font-bold">项目信息 <button type="button" disabled={infoSaving} className="app-action-button float-right h-6 px-0 text-[#6c4dff] disabled:opacity-60" onClick={toggleInfoEditing}><span className="text-[#6c4dff]"><EditIcon /></span>{infoSaving ? "保存中" : infoEditing ? "完成编辑" : "编辑"}</button></h2>
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
              <textarea value={descriptionText} onChange={(event) => setDraftField("description", event.target.value)} className="confirm-info-input report-light-scroll h-[60px] w-full min-w-0 resize-none overflow-y-auto border-0 bg-transparent p-0 text-[12px] leading-5 text-[#53565e] outline-none" />
            ) : (
              <div className="report-light-scroll max-h-[60px] min-w-0 overflow-y-auto pr-2 leading-5 text-[#53565e]">{descriptionText || "未填写"}</div>
            )}
          </div>
        </div>
      </Card>
      <Card className="absolute left-[307px] top-[400px] h-[176px] w-[1206px] p-5">
        <h2 className="text-[18px] font-bold">已上传图纸</h2>
        {drawings.length ? (
          <div className="report-light-scroll mt-3 flex h-[116px] gap-7 overflow-x-auto overflow-y-hidden pb-5">
            {drawings.map((item) => (
              <div className="h-[92px] w-[178px] shrink-0 rounded-[8px] border border-[#e8ebef] bg-white p-2" key={item.id}>
                <img className="h-[60px] w-full rounded-[4px] object-cover" src={apiUrl(item.file_url)} />
                <b className="mt-1 block truncate text-[10px]">{item.original_name}</b>
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
        ? <input value={value} onChange={(event) => onChange(event.target.value)} className="confirm-info-input min-w-0 border-0 bg-transparent p-0 text-[12px] leading-5 text-[#53565e] outline-none" />
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

type ProcessingStepKind = "stage" | "agent";
type ProcessingStepStatus = "waiting" | "active" | "done" | "paused" | "error";

interface ProcessingStep {
  id: string;
  kind: ProcessingStepKind;
  title: string;
  waitingText: string;
  activeText: string;
  doneText: string;
  weight: number;
  estimatedSeconds: number;
}

const processingStageSteps: ProcessingStep[] = [
  { id: "read_inputs", kind: "stage", title: "读取提交资料", waitingText: "等待读取项目信息、任务书和图纸", activeText: "正在读取项目信息、任务书和图纸", doneText: "项目资料读取完成", weight: 8, estimatedSeconds: 18 },
  { id: "model_input", kind: "stage", title: "准备模型输入", waitingText: "等待整理模型可读取的图文输入", activeText: "正在准备模型可读取的图文输入", doneText: "模型输入准备完成", weight: 12, estimatedSeconds: 24 },
];

// 按设计阶段给整体评图一个保守预算，进度和剩余时间共用同一口径。
function getProcessingBudgetSeconds(stage: string) {
  if (stage.includes("图纸")) return 285;
  if (stage.includes("概念")) return 180;
  return 285;
}

// 根据设计阶段和已选 Agent 生成真实评图流程。
function buildProcessingSteps(stage: string, enabledAgents: string[]): ProcessingStep[] {
  const agentTypes = enabledAgents.length ? enabledAgents : getStageAgentTypes(stage);
  const agentWeight = 70 / Math.max(agentTypes.length, 1);
  const budgetSeconds = getProcessingBudgetSeconds(stage);
  const agentSeconds = Math.max(24, Math.round((budgetSeconds - 72) / Math.max(agentTypes.length, 1)));
  const agentSteps = getAgentSpecs(agentTypes).map((agent) => ({
    id: agent.type,
    kind: "agent" as const,
    title: `${agent.display} Agent 分析`,
    waitingText: `等待${agent.display}分析`,
    activeText: `${agent.name} 正在分析图纸`,
    doneText: `${agent.display}分析已完成`,
    weight: agentWeight,
    estimatedSeconds: agentSeconds,
  }));
  return [
    ...processingStageSteps,
    ...agentSteps,
    { id: "report", kind: "stage", title: "生成评图报告", waitingText: "等待前序分析完成", activeText: "正在汇总评分、问题和修改建议", doneText: "评图报告已生成", weight: 10, estimatedSeconds: 30 },
  ];
}

// 判断一个流程节点是否已经完成。
function isProcessingStepDone(step: ProcessingStep, evaluation: ReturnType<typeof useWorkspace>["evaluation"], report: unknown) {
  if (report) return true;
  if (step.kind === "agent") return evaluation.completedAgents.includes(step.id);
  return evaluation.completedStages.includes(step.id);
}

// 找到当前应该高亮的流程节点。
function getCurrentProcessingStepId(steps: ProcessingStep[], evaluation: ReturnType<typeof useWorkspace>["evaluation"], report: unknown) {
  if (report) return "";
  if (evaluation.errorStageId) return evaluation.errorStageId;
  if (evaluation.activeAgent) return evaluation.activeAgent;
  if (evaluation.activeStageId) return evaluation.activeStageId;
  return steps.find((step) => !isProcessingStepDone(step, evaluation, report))?.id ?? "";
}

// 计算真实节点驱动的总体进度：当前节点按自己的激活时间推进，未完成时停在节点尾部等待真实结果。
function calculateProcessingProgress(steps: ProcessingStep[], evaluation: ReturnType<typeof useWorkspace>["evaluation"], report: unknown, activeStepElapsedSeconds: number) {
  if (report) return 100;
  const currentId = getCurrentProcessingStepId(steps, evaluation, report);
  const progress = steps.reduce((sum, step) => {
    if (isProcessingStepDone(step, evaluation, report)) return sum + step.weight;
    if (evaluation.running && !evaluation.paused && !evaluation.error && step.id === currentId) {
      const ratio = Math.min(0.92, Math.max(0.06, activeStepElapsedSeconds / Math.max(step.estimatedSeconds, 1)));
      return sum + step.weight * ratio;
    }
    return sum;
  }, 0);
  const boundedProgress = Math.max(evaluation.running ? 3 : 0, Math.min(99, progress));
  return Number(boundedProgress.toFixed(1));
}

// 估算评图剩余时间。
function estimateRemainingSeconds(stage: string, progress: number, elapsedSeconds: number, running: boolean, paused: boolean, report: unknown, error: string) {
  if (report) return "已完成";
  if (error) return "已停止";
  if (paused) return "已暂停";
  if (!running && progress === 0) return "估算中";
  const budget = getProcessingBudgetSeconds(stage);
  return formatRemainingTime(Math.max(0, budget - elapsedSeconds));
}

// 格式化剩余时间。
function formatRemainingTime(seconds: number) {
  const safeSeconds = Math.max(0, seconds);
  const minutes = Math.floor(safeSeconds / 60);
  const rest = safeSeconds % 60;
  return `约 ${minutes}:${String(rest).padStart(2, "0")}`;
}

// 计算当前评图已用时间，暂停后不继续增加。
function getEvaluationElapsedSeconds(evaluation: ReturnType<typeof useWorkspace>["evaluation"], now: number) {
  const liveElapsed = evaluation.running && evaluation.startedAt ? now - evaluation.startedAt : 0;
  return Math.round((evaluation.elapsedBeforePause + liveElapsed) / 1000);
}

// 显示进度百分比，界面只显示整数，内部仍按小步进更新。
function formatProcessingPercent(progress: number) {
  return String(Math.round(progress));
}

// 渲染 AI 评图等待页。
export function ProcessingPage({ go }: PageProps) {
  const { draft, evaluation, report, pauseEvaluation, startEvaluation } = useWorkspace();
  const [now, setNow] = useState(Date.now());
  const [reportNoticeOpen, setReportNoticeOpen] = useState(false);
  const [displayProgress, setDisplayProgress] = useState(0);
  const [activeStepTiming, setActiveStepTiming] = useState({ id: "", startedAt: Date.now() });
  const progressScrollRef = useRef<HTMLDivElement>(null);
  const steps = useMemo(() => buildProcessingSteps(draft.designStage, draft.enabledAgents), [draft.designStage, draft.enabledAgents]);
  const currentStepId = getCurrentProcessingStepId(steps, evaluation, report);
  const elapsedSeconds = getEvaluationElapsedSeconds(evaluation, now);
  const activeStepElapsedSeconds = evaluation.running && activeStepTiming.id === currentStepId ? Math.max(0, Math.round((now - activeStepTiming.startedAt) / 1000)) : 0;
  const rawProgress = calculateProcessingProgress(steps, evaluation, report, activeStepElapsedSeconds);
  const progress = displayProgress;
  const agentSteps = steps.filter((step) => step.kind === "agent");
  const completedAgentCount = report ? agentSteps.length : agentSteps.filter((step) => evaluation.completedAgents.includes(step.id)).length;
  const remainingText = estimateRemainingSeconds(draft.designStage, progress, elapsedSeconds, evaluation.running, evaluation.paused, report, evaluation.error);
  const completedStepKey = [...evaluation.completedStages, ...evaluation.completedAgents, report ? "report" : ""].filter(Boolean).join("|");
  const logMessages = [
    ...evaluation.messages.filter(Boolean),
    ...(evaluation.error ? [evaluation.error] : []),
  ].slice(-8);

  useEffect(() => {
    if (!evaluation.running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [evaluation.running]);

  useEffect(() => {
    if (!evaluation.running || !currentStepId) return;
    setActiveStepTiming((current) => current.id === currentStepId ? current : { id: currentStepId, startedAt: Date.now() });
    setNow(Date.now());
  }, [currentStepId, evaluation.running]);

  useEffect(() => {
    if (!evaluation.startedAt && !report) {
      setDisplayProgress(0);
      return;
    }
    setDisplayProgress(rawProgress);
  }, [evaluation.startedAt, report]);

  useEffect(() => {
    if (evaluation.error) return;
    if (report) {
      setDisplayProgress(100);
      return;
    }
    if (evaluation.running || evaluation.paused) {
      setDisplayProgress((current) => Math.max(current, rawProgress));
      return;
    }
    setDisplayProgress(rawProgress);
  }, [rawProgress, evaluation.running, evaluation.paused, evaluation.error, report]);

  useEffect(() => {
    const container = progressScrollRef.current;
    if (!container) return;
    const completedIds = [...evaluation.completedStages, ...evaluation.completedAgents];
    const targetId = report ? "report" : completedIds[completedIds.length - 1];
    if (!targetId) return;
    const target = Array.from(container.querySelectorAll<HTMLElement>("[data-processing-step-id]")).find((item) => item.dataset.processingStepId === targetId);
    if (!target) return;
    const containerRect = container.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const hiddenBelow = targetRect.bottom > containerRect.bottom;
    const hiddenAbove = targetRect.top < containerRect.top;
    if (!hiddenBelow && !hiddenAbove) return;
    const nextTop = hiddenBelow
      ? container.scrollTop + targetRect.bottom - containerRect.bottom
      : container.scrollTop + targetRect.top - containerRect.top;
    container.scrollTo({ top: Math.max(0, nextTop), behavior: "smooth" });
  }, [completedStepKey, report, evaluation.completedStages, evaluation.completedAgents]);

  const toggleEvaluation = () => {
    if (evaluation.error) {
      void startEvaluation();
      return;
    }
    if (evaluation.running) {
      void pauseEvaluation();
      return;
    }
    if (evaluation.paused) void startEvaluation();
  };

  const openReport = () => {
    if (report) {
      go("report");
      return;
    }
    setReportNoticeOpen(true);
  };

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#f4f6f8]">
      <Sidebar go={go} creating />
      <PageTitle title="评图工作台" subtitle="Agent 正在围绕图纸协同工作，右侧会实时同步评图进度。" />
      <div className="font-inter absolute left-[1246px] top-[99px] flex gap-[19px]">
        <Button kind="white" className="w-[116px] font-semibold" disabled={Boolean(report)} onClick={toggleEvaluation}>{evaluation.error ? "重新评图" : evaluation.paused ? "继续评图" : "暂停评图"}</Button>
        <Button kind="purple" className="w-[132px] rounded-[12px] font-semibold" onClick={openReport}>查看评图报告</Button>
      </div>
      <Card className="absolute left-[307px] top-[149px] h-[658px] w-[760px]">
        <h2 className="absolute left-[39px] top-[27px] text-[18px] font-bold leading-[24px]">{evaluation.paused || evaluation.error ? "Agent 协同评图暂停" : "Agent 协同评图中"}</h2>
        <p className="absolute left-[39px] top-[57px] text-[12px] leading-[18px] text-[#9a9ea7]">这里会同步显示各个 Agent 的工作状态、协作顺序和项目评图进度。</p>
        <div className="absolute left-[39px] top-[92px] flex h-[414px] w-[680px] items-center justify-center overflow-hidden rounded-[22px] border border-[#e8ebef] bg-[#f7f7ff]"><img className="h-[360px] w-[628px] object-contain" src="/assets/v1/processing-scene.png" /></div>
        <div className="absolute left-[39px] top-[545px] grid w-[680px] grid-cols-3 gap-[22px]">
          <Metric value={`${formatProcessingPercent(progress)}%`} text="总体进度" tone="purple" />
          <Metric value={`${completedAgentCount} / ${agentSteps.length}`} text="已完成Agent" tone="green" />
          <Metric value={remainingText} text="预计剩余" tone="coral" />
        </div>
      </Card>
      <Card className="absolute left-[1089px] top-[149px] h-[658px] w-[424px] overflow-hidden">
        <h2 className="absolute left-[23px] top-[27px] text-[18px] font-bold leading-[24px]">评图进度</h2>
        <p className="absolute left-[23px] top-[57px] text-[12px] leading-[18px] text-[#9a9ea7]">这里会实时显示当前评图流程和每个节点的完成情况。</p>
        <div id="processing-scroll-area" ref={progressScrollRef} className="report-light-scroll absolute left-[23px] top-[107px] h-[382px] w-[378px] overflow-y-auto pr-2">
          <div className="w-full space-y-3">{steps.map((step) => (
            <div data-processing-step-id={step.id} key={step.id}>
              <ProgressRow
                step={step}
                status={getProgressRowStatus(step, evaluation, report, currentStepId)}
              />
            </div>
          ))}</div>
        </div>
        <ProcessingLog messages={logMessages} report={Boolean(report)} error={evaluation.error} />
      </Card>
      {reportNoticeOpen && <FlowErrorCard title="评图还未完成" message="评图还未完成，请稍等。" onClose={() => setReportNoticeOpen(false)} />}
    </div>
  );
}

// 渲染等待页统计卡。
function Metric({ value, text, tone }: { value: string; text: string; tone: "purple" | "green" | "coral" }) {
  const colors = { purple: "text-[#6c4dff]", green: "text-[#22c55e]", coral: "text-[#ff5570]" };
  return <div className="font-inter h-[74px] rounded-[12px] border border-[#e8ebef] bg-[#fafbfc] px-4 py-3"><b className={`text-[20px] leading-[26px] ${colors[tone]}`}>{value}</b><p className="text-[12px] leading-[16px] text-[#6b7280]">{text}</p></div>;
}

// 判断进度行状态。
function getProgressRowStatus(step: ProcessingStep, evaluation: ReturnType<typeof useWorkspace>["evaluation"], report: unknown, currentStepId: string): ProcessingStepStatus {
  if (evaluation.error && evaluation.errorStageId === step.id) return "error";
  if (isProcessingStepDone(step, evaluation, report)) return "done";
  if (evaluation.paused && currentStepId === step.id) return "paused";
  if (currentStepId === step.id && evaluation.running) return "active";
  return "waiting";
}

// 渲染等待页步骤行，不显示大圆点。
function ProgressRow({ step, status }: { step: ProcessingStep; status: ProcessingStepStatus }) {
  const stateStyles = {
    waiting: "border-[#e8ebef] bg-white",
    active: "processing-progress-active border-[#bdaeff] bg-[#fbfaff]",
    done: "border-[#bbf7d0] bg-[#f0fdf4]",
    paused: "border-[#d9ceff] bg-[#fbfaff]",
    error: "border-[#fecaca] bg-[#fff5f5]",
  };
  const labelStyles = {
    waiting: "bg-[#f4f6f8] text-[#6b7280]",
    active: "bg-[#efe9ff] text-[#6c4dff]",
    done: "bg-[#dcfce7] text-[#16a34a]",
    paused: "bg-[#f3f0ff] text-[#6c4dff]",
    error: "bg-[#fee2e2] text-[#dc2626]",
  };
  const labels = {
    waiting: "等待",
    active: "分析中",
    done: "已完成",
    paused: "已暂停",
    error: "出错",
  };
  const desc = status === "done" ? step.doneText : status === "active" ? step.activeText : status === "paused" ? "评图已暂停，可点击继续评图恢复" : status === "error" ? "该阶段中断，请查看下方原因" : step.waitingText;
  return (
    <div className={`relative min-h-[74px] rounded-[14px] border p-3 ${stateStyles[status]}`}>
      <b className="block max-w-[200px] truncate text-[13px]">{step.title}</b>
      <span className={`absolute right-[16px] -mt-[22px] rounded-full px-3 py-1 text-[11px] ${labelStyles[status]}`}>{labels[status]}</span>
      <p className="mt-2 text-[11px] leading-4 text-[#9a9ea7]">{desc}</p>
    </div>
  );
}

// 渲染等待页底部状态日志。
function ProcessingLog({ messages, report, error }: { messages: string[]; report: boolean; error: string }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const fallback = report
    ? "评图已完成，请点击“查看评图报告”查看结果。"
    : error || "系统正在等待下一个评图节点更新。";
  const visibleMessages = messages.length ? messages : [fallback];
  const messageKey = visibleMessages.join("\n");
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
  }, [messageKey]);
  return (
    <div className="absolute left-[23px] top-[512px] h-[118px] w-[378px] rounded-[12px] border border-[#e8ebef] bg-[#f8fafc] text-[12px] text-[#8b95a1]">
      <div ref={scrollRef} className="report-light-scroll h-full overflow-y-auto px-[13px] py-[9px] pr-2 leading-[18px]">
        {visibleMessages.map((message, index) => (
          <p className={index === visibleMessages.length - 1 ? "text-[#53565e]" : ""} key={`${message}-${index}`}>{message}</p>
        ))}
      </div>
    </div>
  );
}
