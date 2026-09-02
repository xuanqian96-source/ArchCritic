// 评图报告页：展示本次真实评分、任务书权重、图纸资料和继续追问。
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { PageProps } from "../App";
import { AppPromptOverlay, Button, Card, PageTitle, Sidebar, ZoomableImageStage } from "../components";
import { apiUrl } from "../api/client";
import { getCachedProjectGroups, loadProjectGroups, type ProjectGroup } from "../state/projectGroups";
import { useWorkspace } from "../state/workspace";
import type { Attachment, DrawingFile, OverallReport, Project, Submission, SubmissionHistory } from "../types/api";
import { getCachedGroupHistory, getCurrentReportVersionLabel, loadProjectGroupHistory } from "./reportHistoryData";
import { ReportAssistant } from "./reportAssistant";
import { buildReportIssues, buildReportSubScores, buildSchemeDimensions, DimensionSummaryText, displayDrawingName, drawingTypeLabel, findReviewEvaluation, getDimensionPanelRadius, getIssueTone, getReferenceDisplay, getReportAgentLabel, getReportEvaluationSnapshot, getReportModelLabel, getReportScoreGradeForMax, isImageDrawing, IssueOverlay, type ReportIssue, ScoreRing, splitReadableParagraphs } from "./reportShared";

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
  const { attachments, chatMessages, downloadCurrentReport, draft, drawings, history, project, projects, refreshChatMessages, report, sendQuestion, submission } = useWorkspace();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [selectedIssue, setSelectedIssue] = useState<ReportIssue | null>(null);
  const [projectInfoOpen, setProjectInfoOpen] = useState(false);
  const [historyNoticeOpen, setHistoryNoticeOpen] = useState(false);
  const [scoredReportVersionCount, setScoredReportVersionCount] = useState(() => history.filter((item) => item.overall_score != null).length);
  const [historyOpening, setHistoryOpening] = useState(false);
  const [projectGroups, setProjectGroups] = useState<ProjectGroup[]>(() => getCachedProjectGroups(projects));
  const reviewEvaluation = useMemo(() => findReviewEvaluation(report?.agent_evaluations ?? []), [report]);
  const schemeDimensions = useMemo(() => buildSchemeDimensions(report?.agent_evaluations ?? []), [report]);
  const dimensions = schemeDimensions;
  const activeIndex = Math.min(selectedIndex, dimensions.length - 1);
  const selected = dimensions[activeIndex];
  const scoreValue = Math.round(report?.overall_score ?? 0);
  const selectedScoreGrade = getReportScoreGradeForMax(selected.score, 100);
  const summaryText = reviewEvaluation?.summary ?? report?.summary ?? "当前报告没有返回整体评价。";
  const reportProjectName = project?.name || draft.name;
  const reportVersionName = getCurrentReportVersionLabel(submission, history, projectGroups);
  const issues = useMemo(() => {
    const reportIssues = buildReportIssues(report);
    return reportIssues;
  }, [report]);
  const pendingChatKey = chatMessages[chatMessages.length - 1]?.role === "user"
    ? `${submission?.id ?? 0}:${chatMessages[chatMessages.length - 1]?.id ?? chatMessages.length}:${chatMessages[chatMessages.length - 1]?.content}`
    : "";
  useEffect(() => {
    if (!submission || !pendingChatKey) return;
    let active = true;
    let timer = 0;
    const refreshPendingAnswer = async () => {
      const saved = await refreshChatMessages().catch(() => null);
      if (!active || (saved && saved[saved.length - 1]?.role !== "user")) return;
      timer = window.setTimeout(refreshPendingAnswer, 2000);
    };
    // 等后端先保存本轮用户消息，避免首次轮询用旧历史覆盖前端即时消息。
    timer = window.setTimeout(refreshPendingAnswer, 2000);
    return () => { active = false; window.clearTimeout(timer); };
  }, [pendingChatKey, refreshChatMessages, submission]);
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
        <ScoreRing score={String(scoreValue)} label="综合评分" />
        <div className="absolute left-[145px] top-[29px]">
          <h2 className="text-[16px] font-bold leading-[22px]">综合评审结果</h2>
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
            const itemGrade = getReportScoreGradeForMax(item.score, 100);
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
        </div>
        <div className="absolute left-[22px] top-[252px] grid h-[176px] w-[712px] grid-cols-4">
          {buildReportSubScores(selected).map((item) => (
            <article className="report-sub-score-card" key={item.name}>
              <span>{item.name}</span>
              <b>{Math.round(item.score)}<small> / {Math.round(item.maxScore)}</small></b>
              <div className="report-sub-score-copy report-hover-scroll">
                {splitReadableParagraphs(item.reason).map((paragraph, index) => <p key={`${item.name}-${index}`}>{paragraph}</p>)}
              </div>
            </article>
          ))}
        </div>
      </section>
      <FeedbackPanel issues={issues} references={report?.references ?? []} onSelect={setSelectedIssue} />
      {submission && <ReportAssistant submissionId={submission.id} messages={chatMessages} report={report} sendQuestion={sendQuestion} go={go} />}
      {selectedIssue && <IssueOverlay issue={selectedIssue} references={report?.references ?? []} onClose={() => setSelectedIssue(null)} />}
      {projectInfoOpen && <ReportProjectInfoModal attachments={attachments} draft={draft} drawings={drawings} modelLabel={getReportModelLabel(submission, draft)} project={project} report={report} submission={submission} onClose={() => setProjectInfoOpen(false)} />}
      {historyNoticeOpen && <HistoryUnavailableModal onClose={() => setHistoryNoticeOpen(false)} />}
    </div>
  );
}

// 右侧固定展示报告反馈要点，报告追问改由悬浮助手承载。
function FeedbackPanel({ issues, references, onSelect }: { issues: ReportIssue[]; references: OverallReport["references"]; onSelect: (issue: ReportIssue) => void }) {
  return (
    <section className="font-inter white-panel figma-shadow absolute left-[1089px] top-[149px] h-[658px] w-[424px] overflow-hidden rounded-[22px] px-[22px] py-[20px]">
      <h2 className="text-[18px] font-bold">反馈要点</h2>
      <p className="mt-1 text-[11px] leading-5 text-[#9a9ea7]">按优先级查看本次报告中的问题、建议与优势</p>
      <div className="report-light-scroll absolute bottom-[22px] left-[22px] right-[14px] top-[76px] overflow-y-auto pr-2">
        <div className="space-y-2">
          {issues.map((issue, index) => {
            const tone = getIssueTone(issue.level);
            return (
              <button type="button" className="report-feedback-card" onClick={() => onSelect(issue)} key={`${issue.text}-${index}`}>
                <span className={`report-feedback-badge ${tone.badge}`}>{issue.label}</span>
                <b>{issue.summary}</b>
                <span className="report-feedback-meta">
                  {issue.referenceIds.length > 0 && <span className="report-feedback-references">{issue.referenceIds.map((referenceId) => {
                    const display = getReferenceDisplay(referenceId, references);
                    return <i title={`${display.fullId} · ${display.title}`} key={referenceId}>[{display.label}]</i>;
                  })}</span>}
                  <small>查看反馈详情</small>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}

// 历史版本不足时，用明确提示替代空白等待。
function HistoryUnavailableModal({ onClose }: { onClose: () => void }) {
  return (
    <AppPromptOverlay onClose={onClose}>
      <section className="app-prompt-card figma-shadow relative" onClick={(event) => event.stopPropagation()}>
        <h2 className="app-prompt-title">暂时没有历史版本对比</h2>
        <p className="app-prompt-copy">这个项目目前只有一份已评分报告。等完成第二次评图后，就可以查看分数变化和版本差异。</p>
        <div className="app-prompt-actions"><button type="button" className="app-action-button h-9 rounded-[10px] bg-[#171719] px-5 text-white" onClick={onClose}>知道了</button></div>
      </section>
    </AppPromptOverlay>
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
