// 评图报告页：展示本次真实评分、任务书权重、图纸资料和继续追问。
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import type { PageProps } from "../App";
import { Button, Card, PageTitle, Sidebar, ZoomableImageStage } from "../components";
import { apiUrl } from "../api/client";
import { getCachedProjectGroups, loadProjectGroups, type ProjectGroup } from "../state/projectGroups";
import { useProfile } from "../state/profile";
import { useWorkspace } from "../state/workspace";
import type { AgentEvaluation, Attachment, DrawingFile, KnowledgeReference, OverallReport, Project, Submission, SubmissionHistory } from "../types/api";
import { getCachedGroupHistory, getCurrentReportVersionLabel, loadProjectGroupHistory } from "./reportHistoryData";
import { buildChatSuggestions, buildDrilldownDimensions, buildReportIssues, buildSchemeDimensions, DimensionSummaryText, displayDrawingName, drawingTypeLabel, findReviewEvaluation, getDimensionPanelRadius, getReportAgentLabel, getReportEvaluationSnapshot, getReportModelLabel, getReportScoreGradeForMax, hasSubScores, isImageDrawing, IssueOverlay, type ReportIssue, ReportOverlay, renderChatText, ScoreRing, splitReadableParagraphs, TraceRow } from "./reportShared";

export function ReportPage(props: PageProps) {
  const { report } = useWorkspace();
  if (!report) return <ReportUnavailablePage {...props} />;
  if (!buildSchemeDimensions(report.agent_evaluations ?? []).length) return <ReportUnavailablePage {...props} invalid />;
  return <ReportContent {...props} />;
}
function ReportUnavailablePage({ go, invalid = false }: PageProps & { invalid?: boolean }) {
  return <><Sidebar go={go} /><main className="absolute left-[307px] top-[54px] w-[1206px]"><PageTitle title="评图报告" subtitle="当前提交还没有可显示的真实报告。" /><Card className="mt-16 flex h-[320px] items-center justify-center"><div className="text-center"><h2 className="text-[22px] font-bold">{invalid ? "报告数据不完整" : "暂无评图结果"}</h2><p className="mt-3 text-[13px] text-[#9a9ea7]">{invalid ? "这份报告没有有效的专项评分，请返回工作台重新评图。" : "请返回评图工作台完成评图，系统不会使用示例分数补充空白。"}</p><Button kind="dark" className="mt-7" onClick={() => go("processing")}>返回评图工作台</Button></div></Card></main></>;
}

function ReportContent({ go }: PageProps) {
  const { attachments, chatMessages, downloadCurrentReport, draft, drawings, history, project, projects, report, sendQuestion, submission } = useWorkspace();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [drilldownSource, setDrilldownSource] = useState<AgentEvaluation | null>(null);
  const [drilldownSourceIndex, setDrilldownSourceIndex] = useState<number | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedIssue, setSelectedIssue] = useState<ReportIssue | null>(null);
  const [projectInfoOpen, setProjectInfoOpen] = useState(false);
  const [historyNoticeOpen, setHistoryNoticeOpen] = useState(false);
  const [scoredReportVersionCount, setScoredReportVersionCount] = useState(() => history.filter((item) => item.overall_score != null).length);
  const [historyOpening, setHistoryOpening] = useState(false);
  const [projectGroups, setProjectGroups] = useState<ProjectGroup[]>(() => getCachedProjectGroups(projects));
  const reviewEvaluation = useMemo(() => findReviewEvaluation(report?.agent_evaluations ?? []), [report]);
  const schemeDimensions = useMemo(() => buildSchemeDimensions(report?.agent_evaluations ?? []), [report]);
  const dimensions = drilldownSource ? buildDrilldownDimensions(drilldownSource) : schemeDimensions;
  const activeIndex = Math.min(selectedIndex, dimensions.length - 1);
  const selected = dimensions[activeIndex];
  const focusEvaluation = drilldownSource ?? null;
  const scoreValue = Math.round(focusEvaluation?.score ?? report?.overall_score ?? 0);
  const scoreLabel = focusEvaluation?.dimension ?? "综合评分";
  const dimensionMaxScore = drilldownSource ? 25 : 100;
  const selectedScoreGrade = getReportScoreGradeForMax(selected.score, dimensionMaxScore);
  const summaryTitle = focusEvaluation ? `${focusEvaluation.dimension}评价` : "综合评审结果";
  const summaryText = focusEvaluation?.summary ?? reviewEvaluation?.summary ?? report?.summary ?? "当前报告没有返回整体评价。";
  const reportProjectName = project?.name || draft.name;
  const reportVersionName = getCurrentReportVersionLabel(submission, history, projectGroups);
  const issues = useMemo(() => {
    const reportIssues = buildReportIssues(report);
    return reportIssues;
  }, [report]);
  const openDimensionDetail = () => {
    if (drilldownSource) {
      setDrilldownSource(null);
      setSelectedIndex(drilldownSourceIndex ?? 0);
      setDrilldownSourceIndex(null);
      return;
    }
    if (!drilldownSource && hasSubScores(selected)) {
      setDrilldownSource(selected);
      setDrilldownSourceIndex(activeIndex);
      setSelectedIndex(0);
      return;
    }
    setDetailOpen(true);
  };
  const openHistory = async () => {
    const cachedHistory = getCachedGroupHistory(project, history);
    const cachedScoredCount = cachedHistory.filter((item) => item.overall_score != null).length;
    if (cachedScoredCount >= 2) {
      go("history");
      return;
    }
    setHistoryOpening(true);
    const fullHistory = await loadProjectGroupHistory(project, projects, history);
    const fullScoredCount = fullHistory.filter((item) => item.overall_score != null).length;
    setScoredReportVersionCount(fullScoredCount);
    setHistoryOpening(false);
    if (fullScoredCount < 2) {
      setHistoryNoticeOpen(true);
      return;
    }
    go("history");
  };
  useEffect(() => {
    let mounted = true;
    const currentScoredCount = history.filter((item) => item.overall_score != null).length;
    setScoredReportVersionCount(currentScoredCount);
    void loadProjectGroupHistory(project, projects, history).then((items) => {
      if (!mounted) return;
      const scoredCount = items.filter((item) => item.overall_score != null).length;
      setScoredReportVersionCount(Math.max(currentScoredCount, scoredCount));
    });
    return () => { mounted = false; };
  }, [history, project, projects]);
  useEffect(() => {
    let mounted = true;
    setProjectGroups(getCachedProjectGroups(projects));
    void loadProjectGroups(projects).then((groups) => {
      if (mounted) setProjectGroups(groups);
    });
    return () => { mounted = false; };
  }, [projects]);
  return (
    <div className="relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} creating />
      <h1 className="absolute left-[307px] top-[53px] text-[34px] font-bold leading-[44px]">评图报告 {reportProjectName} <span className="text-[24px] text-[#6b7385]">{reportVersionName}</span></h1>
      <p className="absolute left-[309px] top-[107px] text-[14px] leading-[22px] text-[#53565e]">多维度评分体系</p>
      <div className="font-inter absolute left-[833px] top-[99px] flex gap-[14px]">
        <Button kind="white" className="report-top-action-button w-[114px]" onClick={() => setProjectInfoOpen(true)}>查看项目信息</Button>
        <Button className="report-top-action-button w-[102px]" onClick={downloadCurrentReport}>下载报告</Button>
      </div>
      <div className="font-inter absolute left-[1378px] top-[99px] flex gap-[14px]">
        <Button kind="purple" className="report-top-action-button w-[132px] rounded-[12px]" disabled={historyOpening} onClick={() => void openHistory()}>历史版本对比</Button>
      </div>
      <Card className="font-inter absolute left-[307px] top-[149px] h-[176px] w-[756px] rounded-[16px]">
        <ScoreRing score={String(scoreValue)} label={scoreLabel} />
        <div className="absolute left-[145px] top-[29px]">
          <h2 className="text-[16px] font-bold leading-[22px]">{summaryTitle}</h2>
          <div className="report-light-scroll mt-2 h-[82px] w-[590px] overflow-y-auto pr-5">
            <p className="text-[12px] leading-5 text-[#53565e]">{summaryText}</p>
          </div>
        </div>
      </Card>
      <section className="font-inter white-panel figma-shadow absolute left-[307px] top-[354px] h-[453px] w-[756px] overflow-hidden rounded-[24px]">
        <h2 className="absolute left-[22px] top-[14px] text-[16px] font-bold">评分维度</h2>
        <span className="absolute left-[98px] top-[17px] text-[11px] text-[#9a9ea7]">点击切换查看对应问题与建议</span>
        <div className="absolute left-[22px] top-[44px] z-10 grid w-[712px] gap-[8px]" style={{ gridTemplateColumns: `repeat(${Math.max(1, dimensions.length)}, minmax(0, 1fr))` }}>
          {dimensions.map((item, index) => {
            const itemGrade = getReportScoreGradeForMax(item.score, dimensionMaxScore);
            const active = index === activeIndex;
            return (
              <button
                onClick={() => setSelectedIndex(index)}
                className={`report-dimension-tab grid h-[36px] grid-cols-[1fr_auto] items-center gap-2 px-[12px] text-[12px] font-bold ${active ? "rounded-t-[10px] text-white" : "rounded-[10px] bg-[#fafbfc] text-[#53565e]"}`}
                style={active ? { backgroundColor: itemGrade.panelColor } : undefined}
                key={`${item.agent_type}-${item.dimension}`}
              >
                <span className="truncate">{item.dimension}</span>
                <span className="text-[12px] leading-4">{Math.round(item.score)}</span>
              </button>
            );
          })}
        </div>
        <div
          className={`absolute left-[22px] top-[80px] h-[156px] w-[712px] px-4 py-[14px] text-white ${getDimensionPanelRadius(activeIndex, dimensions.length)}`}
          style={{ backgroundColor: selectedScoreGrade.panelColor }}
        >
          <b className="absolute right-[25px] top-[22px] text-[48px] leading-[54px]">{Math.round(selected.score)}</b>
          <DimensionSummaryText selected={selected} />
          <Button kind="white" className="report-top-action-button absolute bottom-4 right-4 h-[34px] w-[106px]" onClick={openDimensionDetail}>{drilldownSource ? "返回总评" : "查看详情"}</Button>
        </div>
        <h3 className="absolute left-[22px] top-[252px] text-[16px] font-bold leading-[22px]">反馈要点</h3>
        <div className="report-light-scroll absolute left-[22px] top-[281px] h-[147px] w-[712px] overflow-y-auto">
          <div className="space-y-2">
            {issues.map((issue, index) => <TraceRow key={`${issue.text}-${index}`} issue={issue} onClick={() => setSelectedIssue(issue)} />)}
          </div>
        </div>
      </section>
      <ChatPanel messages={chatMessages} report={report} sendQuestion={sendQuestion} />
      {detailOpen && <ReportOverlay title={selected.dimension} subtitle="专项评图详情" onClose={() => setDetailOpen(false)} lines={[...selected.issues, ...selected.suggestions]} fallback={selected.summary} />}
      {selectedIssue && <IssueOverlay issue={selectedIssue} references={report?.references ?? []} onClose={() => setSelectedIssue(null)} />}
      {projectInfoOpen && <ReportProjectInfoModal attachments={attachments} draft={draft} drawings={drawings} modelLabel={getReportModelLabel(submission, draft)} project={project} report={report} submission={submission} onClose={() => setProjectInfoOpen(false)} />}
      {historyNoticeOpen && <HistoryUnavailableModal onClose={() => setHistoryNoticeOpen(false)} />}
    </div>
  );
}

// 历史版本不足时，用明确提示替代空白等待。
function HistoryUnavailableModal({ onClose }: { onClose: () => void }) {
  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-[#171719]/30" onClick={onClose}>
      <section className="figma-shadow font-chat relative h-[238px] w-[592px] rounded-[20px] border border-[#d9dde3] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        <h2 className="text-[24px] font-bold leading-8 text-[#171719]">暂时没有历史版本对比</h2>
        <p className="mt-6 text-[16px] leading-6 text-[#171719]">这个项目目前只有一份已评分报告。等完成第二次评图后，就可以查看分数变化和版本差异。</p>
        <button type="button" className="app-action-button absolute bottom-6 right-7 h-10 w-[96px] rounded-[12px] bg-[#171719] text-white" onClick={onClose}>知道了</button>
      </section>
    </div>,
    document.body,
  );
}

// 报告页内展示本次评图对应的项目资料。
function ReportProjectInfoModal({
  attachments,
  draft,
  drawings,
  modelLabel,
  onClose,
  project,
  report,
  submission,
}: {
  attachments: Attachment[];
  draft: ReturnType<typeof useWorkspace>["draft"];
  drawings: DrawingFile[];
  modelLabel: string;
  onClose: () => void;
  project: Project | null;
  report: OverallReport | null;
  submission: Submission | null;
}) {
  const [previewDrawing, setPreviewDrawing] = useState<DrawingFile | null>(null);
  const snapshot = getReportEvaluationSnapshot(report);
  const agents = snapshot.enabledAgents.length ? snapshot.enabledAgents : submission?.enabled_agents?.length ? submission.enabled_agents : draft.enabledAgents;
  const infoItems = [
    ["项目名称", project?.name || draft.name || "未填写"],
    ["建筑类型", project?.building_type || draft.buildingType || "未填写"],
    ["基地位置", project?.site_location || draft.siteLocation || "未填写"],
    ["设计年级", project?.grade || draft.grade || "未填写"],
    ["项目阶段", submission?.design_stage || draft.designStage || "未填写"],
  ];
  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-[#171719]/30" onClick={onClose}>
      {previewDrawing ? (
        <ZoomableImageStage src={apiUrl(previewDrawing.file_url)} alt={displayDrawingName(previewDrawing.original_name)} onClose={() => setPreviewDrawing(null)} />
      ) : (
        <section className="figma-shadow relative h-[620px] w-[820px] rounded-[24px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
          <button type="button" aria-label="关闭" onClick={onClose} className="absolute right-6 top-6 flex h-10 w-10 items-center justify-center rounded-full border border-[#e8ebef] bg-white text-[24px] leading-none text-[#9a9ea7] hover:bg-[#f4f6f8]">×</button>
          <p className="text-[13px] font-bold text-[#6c4dff]">项目信息</p>
          <h2 className="mt-2 text-[26px] font-bold text-[#171719]">{project?.name || draft.name || "当前项目"}</h2>
          <div className="report-light-scroll mt-6 h-[500px] overflow-y-auto pr-4">
            <section>
              <h3 className="text-[16px] font-bold">基础信息</h3>
              <div className="mt-3 grid grid-cols-3 gap-3">
                {infoItems.map(([label, value]) => (
                  <div className="rounded-[12px] bg-[#fafbfc] px-4 py-3" key={label}>
                    <p className="text-[11px] text-[#9a9ea7]">{label}</p>
                    <p className="mt-1 truncate text-[13px] font-bold text-[#171719]" title={value}>{value}</p>
                  </div>
                ))}
              </div>
            </section>
            <section className="mt-6">
              <h3 className="text-[16px] font-bold">设计说明</h3>
              <div className="mt-3 rounded-[14px] bg-[#fafbfc] px-4 py-3 text-[13px] leading-7 text-[#53565e]">
                {splitReadableParagraphs(submission?.description || draft.description || "未填写设计说明。").map((paragraph, index) => <p className="mb-2 last:mb-0" key={`description-${index}`}>{paragraph}</p>)}
              </div>
            </section>
            <section className="mt-6">
              <h3 className="text-[16px] font-bold">任务书</h3>
              <div className="mt-3 grid grid-cols-2 gap-3">
                {attachments.length ? attachments.map((attachment) => (
                  <a className="truncate rounded-[12px] border border-[#e8ebef] bg-white px-4 py-3 text-[13px] font-bold text-[#171719] hover:bg-[#f4f6f8]" href={apiUrl(attachment.file_url)} target="_blank" rel="noreferrer" key={attachment.id}>{attachment.original_name}</a>
                )) : <p className="rounded-[12px] bg-[#fafbfc] px-4 py-3 text-[13px] text-[#9a9ea7]">暂无任务书。</p>}
              </div>
            </section>
            <section className="mt-6">
              <h3 className="text-[16px] font-bold">图纸</h3>
              <div className="mt-3 grid grid-cols-3 gap-3">
                {drawings.length ? drawings.map((drawing) => (
                  <button
                    type="button"
                    className="overflow-hidden rounded-[14px] border border-[#e8ebef] bg-white text-left hover:bg-[#f4f6f8]"
                    onClick={() => isImageDrawing(drawing) && setPreviewDrawing(drawing)}
                    key={drawing.id}
                  >
                    <div className="flex h-[120px] items-center justify-center bg-[#fafbfc]">
                      {isImageDrawing(drawing) ? <img className="h-full w-full object-cover" src={apiUrl(drawing.file_url)} alt={displayDrawingName(drawing.original_name)} /> : <span className="text-[12px] font-bold text-[#9a9ea7]">PDF 图纸</span>}
                    </div>
                    <div className="px-3 py-3">
                      <p className="truncate text-[13px] font-bold text-[#171719]">{displayDrawingName(drawing.original_name)}</p>
                      <p className="mt-1 text-[11px] text-[#9a9ea7]">{drawingTypeLabel(drawing.drawing_type)}</p>
                    </div>
                  </button>
                )) : <p className="rounded-[12px] bg-[#fafbfc] px-4 py-3 text-[13px] text-[#9a9ea7]">暂无图纸。</p>}
              </div>
            </section>
            <section className="mt-6">
              <h3 className="text-[16px] font-bold">评图设置</h3>
              <div className="mt-3 rounded-[14px] bg-[#fafbfc] px-4 py-3">
                <p className="text-[13px] text-[#53565e]">模型：<b className="text-[#171719]">{modelLabel}</b></p>
                <p className="mt-3 text-[13px] text-[#53565e]">
                  调用 Agent：<b className="text-[#171719]">{agents.map((agent) => getReportAgentLabel(agent)).join("、") || "未设置"}</b>
                </p>
                <p className="mt-3 text-[13px] text-[#53565e]">
                  最终评分占比：<b className="text-[#171719]">{snapshot.weights.length ? snapshot.weights.map((item) => `${getReportAgentLabel(item.agent)} ${item.value}%`).join("、") : "旧报告未保存权重"}</b>
                </p>
                {snapshot.taskBookSources.length > 0 && <p className="mt-3 text-[13px] text-[#53565e]">评分读取任务书：<b className="text-[#171719]">{snapshot.taskBookSources.join("、")}</b></p>}
              </div>
            </section>
          </div>
        </section>
      )}
    </div>,
    document.body,
  );
}

// 渲染报告右侧继续对话区。
function ChatPanel({ messages, report, sendQuestion }: { messages: { role: "user" | "assistant"; content: string }[]; report: OverallReport | null; sendQuestion: (content: string) => Promise<void> }) {
  const { draft, setDraftField } = useWorkspace();
  const { profile } = useProfile();
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [modelOpen, setModelOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const openingMessage = "报告已生成。我可以继续解释扣分原因、定位图纸问题，或生成下一轮优化动作。";
  const displayMessages = [{ role: "assistant" as const, content: openingMessage }, ...messages];
  const suggestions = useMemo(() => buildChatSuggestions(report), [report]);
  const modelValue = draft.modelProvider === "gemini" ? "gemini|gemini-2.5-flash" : "dashscope|qwen3.6-plus";
  const modelLabel = draft.modelProvider === "gemini" ? "gemini-2.5-flash" : "qwen3.6-plus";
  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, sending]);
  useEffect(() => {
    if (!modelOpen) return;
    const close = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("[data-chat-model-menu]")) return;
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
  };
  const submit = async (content = question) => {
    if (!content.trim()) return;
    setSending(true);
    setSendError("");
    setQuestion("");
    try {
      await sendQuestion(content);
    } catch {
      setSendError("发送失败，请确认后端服务和当前报告状态。");
    } finally {
      setSending(false);
    }
  };
  const handleInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.nativeEvent.isComposing || event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    void submit();
  };
  return (
    <section className="font-inter white-panel figma-shadow absolute left-[1089px] top-[149px] h-[658px] w-[424px] overflow-hidden rounded-[22px] px-[22px] py-[20px]">
      <h2 className="text-[18px] font-bold">继续与系统对话</h2>
      <div ref={scrollRef} className="report-chat-scroll absolute left-[22px] right-[22px] top-[70px] bottom-[182px] overflow-y-auto pr-2">
        <div className="space-y-3">
          {displayMessages.map((message, index) => message.role === "user" ? (
            <div className="flex justify-end gap-2" key={`${message.role}-${index}-${message.content}`}>
              <p className="max-w-[286px] whitespace-pre-wrap rounded-[12px] border border-[#e8ebef] bg-[#f4f6f8] px-3 py-3 text-[12px] leading-5 text-[#171719]">{renderChatText(message.content)}</p>
              {profile.avatarDataUrl ? <img className="h-9 w-9 rounded-full object-cover" src={profile.avatarDataUrl} /> : <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#171719] text-[12px] font-bold text-white">我</span>}
            </div>
          ) : (
            <div className="flex gap-2" key={`${message.role}-${index}-${message.content}`}>
              <img className="h-9 w-9 rounded-full object-cover" src="/assets/v1/头像.png" />
              <p className="max-w-[286px] whitespace-pre-wrap rounded-[12px] border border-[#e8ebef] bg-white px-3 py-3 text-[12px] leading-5 text-[#171719]">{renderChatText(message.content)}</p>
            </div>
          ))}
        </div>
        {!messages.length && <div className="mt-4">
          <p className="text-[12px] text-[#171719]">你可以继续追问</p>
          <div className="mt-2 grid grid-cols-3 gap-2 text-[11px]">
            {suggestions.map((item) => (
              <button type="button" title={item} disabled={sending} className="h-9 min-w-0 truncate rounded-[10px] border border-[#e8ebef] px-2 text-left hover:bg-[#f4f6f8] disabled:opacity-60" onClick={() => setQuestion(item)} key={item}>{item}</button>
            ))}
          </div>
        </div>}
        <span className="mt-1 block h-4 text-[11px] text-[#9a9ea7]">{sending ? "正在调用系统回答..." : sendError}</span>
      </div>
      <div className="absolute bottom-6 left-[22px] h-[126px] w-[380px] rounded-[14px] border border-[#e8ebef] bg-[#fafbfc] text-[12px] text-[#9a9ea7]">
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={handleInputKeyDown} placeholder="输入你想继续追问的问题..." className="report-chat-scroll absolute left-3 right-2 top-2 h-[62px] resize-none overflow-y-auto bg-transparent pr-2 text-[#171719] outline-none placeholder:text-[#9a9ea7]" />
        <div className="absolute bottom-2 left-2" data-chat-model-menu>
          {modelOpen && (
            <div className="figma-shadow absolute bottom-[34px] left-0 z-20 w-[280px] overflow-hidden rounded-[12px] border border-[#e8ebef] bg-white p-1">
              {[
                { value: "dashscope|qwen3.6-plus", label: "qwen3.6-plus" },
                { value: "gemini|gemini-2.5-flash", label: "gemini-2.5-flash" },
              ].map((option) => (
                <button
                  type="button"
                  key={option.value}
                  onClick={() => changeModel(option.value)}
                  className={`flex h-9 w-full items-center justify-between rounded-[9px] px-3 text-left text-[12px] font-bold ${modelValue === option.value ? "bg-[#efe9ff] text-[#6c4dff]" : "text-[#171719] hover:bg-[#f4f6f8]"}`}
                >
                  {option.label}
                  {modelValue === option.value && <span>✓</span>}
                </button>
              ))}
            </div>
          )}
          <button type="button" onClick={() => setModelOpen((current) => !current)} className="h-[27px] w-[280px] rounded-[8px] border border-[#e8ebef] bg-white px-3 py-1.5 text-left">
            <span className="text-[#9a9ea7]">模型</span><b className="ml-4 text-[#171719]">{modelLabel}</b><span className={`report-model-arrow ${modelOpen ? "rotate-right" : ""}`} />
          </button>
        </div>
        <Button className="report-chat-send-button absolute bottom-2 right-2 h-[27px] w-[55px] text-[12px]" disabled={sending} onClick={() => void submit()}>{sending ? <span className="flex h-[27px] items-center justify-center text-[15px] leading-[0]">...</span> : "发送"}</Button>
      </div>
    </section>
  );
}
