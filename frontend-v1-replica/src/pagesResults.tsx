// 结果页面：复刻完整评图报告和历史版本对比页。
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { PageProps } from "./App";
import { Button, Card, PageTitle, Sidebar } from "./components";
import { getProjectHistory } from "./api/projects";
import { useProfile } from "./state/profile";
import { useWorkspace } from "./state/workspace";
import type { AgentEvaluation, FeedbackItem, KnowledgeReference, Project, Submission, SubmissionHistory } from "./types/api";

const fallbackDimensions: AgentEvaluation[] = [
  { agent_type: "function_agent", dimension: "功能与流线", score: 82, summary: "主要问题集中在主入口与公共空间的联系、后勤路径和消防疏散距离校核。建议优先减少人车交叉与局部回折。", strengths: [], issues: [], suggestions: [], details: {} },
  { agent_type: "site_agent", dimension: "场地与回应", score: 76, summary: "场地回应具备基础合理性，仍需继续校核周边关系。", strengths: [], issues: [], suggestions: [], details: {} },
  { agent_type: "form_agent", dimension: "几何形式", score: 72, summary: "几何形式表达仍需强化秩序与空间逻辑。", strengths: [], issues: [], suggestions: [], details: {} },
  { agent_type: "structure_agent", dimension: "结构与构造", score: 84, summary: "结构构造总体可行，局部节点仍需复核。", strengths: [], issues: [], suggestions: [], details: {} },
];

const schemeDimensionSpecs = [
  { agent: "function_agent", label: "功能与流线", aliases: ["功能与流线"] },
  { agent: "site_agent", label: "场地与回应", aliases: ["场地与回应", "场地回应"] },
  { agent: "form_agent", label: "几何形式", aliases: ["几何形式", "形式与构图", "形式与沟通"] },
  { agent: "structure_agent", label: "结构与构造", aliases: ["结构与构造", "结构与可行性"] },
];

type IssueLevel = "must_fix" | "should_improve" | "optional_improvements" | "strengths";
const MAX_REFERENCE_LINKS = 3;

interface ReportIssue {
  level: IssueLevel;
  label: string;
  text: string;
  summary: string;
  referenceIds: string[];
}

// 判断版本是否仍使用系统默认标题。
function isDefaultSubmissionTitle(title?: string) {
  return !title?.trim() || title.trim().endsWith("提交");
}

// 历史版本列表优先显示用户重命名后的版本名。
function getHistoryVersionLabel(item: SubmissionHistory, index: number) {
  return isDefaultSubmissionTitle(item.title) ? `V${index + 1} ${item.design_stage}` : item.title.trim();
}

// 报告页标题右侧显示当前版本名，默认标题则回退为 V 序号。
function getCurrentReportVersionLabel(
  submission: Submission | null,
  history: SubmissionHistory[],
  project: Project | null,
  projects: Project[],
) {
  if (!submission) return "V1";
  if (!isDefaultSubmissionTitle(submission.title)) return submission.title.trim();
  if (project) {
    const relatedProjects = projects
      .filter((item) => item.name.trim() === project.name.trim())
      .sort((a, b) => {
        const aTime = new Date(a.created_at ?? "").getTime() || 0;
        const bTime = new Date(b.created_at ?? "").getTime() || 0;
        return aTime - bTime || a.id - b.id;
      });
    if (relatedProjects.length > 1) {
      const projectIndex = relatedProjects.findIndex((item) => item.id === project.id);
      if (projectIndex >= 0) return `V${projectIndex + 1}`;
    }
  }
  const sorted = [...history].sort((a, b) => {
    const aTime = new Date(a.created_at ?? "").getTime() || 0;
    const bTime = new Date(b.created_at ?? "").getTime() || 0;
    return aTime - bTime || a.id - b.id;
  });
  const index = sorted.findIndex((item) => item.id === submission.id);
  return `V${index >= 0 ? index + 1 : 1}`;
}

// 从完整反馈中提取第一个标点前的短标题，避免截断造成断句生硬。
function summarizeIssue(text: string) {
  const clean = text.replace(/\s+/g, " ").replace(/\[(K\d+)\]/gi, "").trim();
  const firstPunctuation = clean.search(/[：:。！？!?；;]/);
  const firstSentence = firstPunctuation > 0 ? clean.slice(0, firstPunctuation) : clean;
  return firstSentence.length > 58 ? `${firstSentence.slice(0, 58)}...` : firstSentence;
}

// 整理待修改问题，优先读取后端返回的知识库引用关系。
function buildReportIssues(report: ReturnType<typeof useWorkspace>["report"]): ReportIssue[] {
  const levels: Array<{ key: IssueLevel; label: string; fallback: string[] }> = [
    { key: "must_fix", label: "必须修改", fallback: report?.must_fix ?? [] },
    { key: "should_improve", label: "重点优化", fallback: report?.should_improve ?? [] },
    { key: "optional_improvements", label: "建议关注", fallback: report?.optional_improvements ?? [] },
    { key: "strengths", label: "当前优势", fallback: report?.strengths ?? [] },
  ];
  return levels.flatMap(({ key, label, fallback }) => {
    const feedback = report?.feedback?.[key] as FeedbackItem[] | undefined;
    const items = feedback?.length ? feedback : fallback.map((text) => ({ text, reference_ids: [] }));
    return items.map((item) => ({
      level: key,
      label,
      text: item.text,
      summary: summarizeIssue(item.text),
      referenceIds: normalizeReferenceIds(item.reference_ids ?? [], item.text, report?.references ?? []),
    }));
  });
}

// 有显式 [K] 时完整保留；旧报告没有编号时，才按关键词保守补充少量链接。
function normalizeReferenceIds(referenceIds: string[], text: string, references: KnowledgeReference[]) {
  const explicitIds = Array.from(new Set(referenceIds.map((item) => item.toUpperCase())));
  if (explicitIds.length || !references.length) return explicitIds;
  const matched = references
    .map((reference) => ({ id: reference.reference_id.toUpperCase(), score: getReferenceMatchScore(text, reference) }))
    .filter((item) => item.id && item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, MAX_REFERENCE_LINKS)
    .map((item) => item.id);
  return matched;
}

// 轻量关键词匹配，只在没有知识编号时补链，不替代模型判断。
function getReferenceMatchScore(text: string, reference: KnowledgeReference) {
  const source = `${reference.title} ${reference.dimension} ${reference.excerpt} ${reference.display_content}`.toLowerCase();
  const normalizedText = text.toLowerCase();
  const words = Array.from(new Set(normalizedText.match(/[a-zA-Z0-9]{3,}/g) ?? []));
  const cnChars = Array.from(new Set((text.match(/[\u4e00-\u9fa5]/g) ?? [])));
  const wordScore = words.reduce((score, keyword) => source.includes(keyword) ? score + Math.min(keyword.length, 6) : score, 0);
  const charScore = cnChars.reduce((score, char) => source.includes(char) ? score + 1 : score, 0);
  return wordScore + charScore;
}

// 按重要等级返回低饱和颜色，和当前黑白紫界面保持一致。
function getIssueTone(level: IssueLevel) {
  const tones = {
    must_fix: { badge: "bg-[#fff1f1] text-[#b44747] border-[#f1d0d0]", rail: "bg-[#d86464]" },
    should_improve: { badge: "bg-[#fff6e8] text-[#a86514] border-[#efd8b4]", rail: "bg-[#d99a42]" },
    optional_improvements: { badge: "bg-[#f0f4ff] text-[#526aa3] border-[#d8e0f5]", rail: "bg-[#7b8fcb]" },
    strengths: { badge: "bg-[#edf8f2] text-[#2f7f55] border-[#cde8d8]", rail: "bg-[#5eaa7b]" },
  } satisfies Record<IssueLevel, { badge: string; rail: string }>;
  return tones[level];
}

// 根据知识编号读取本次报告快照中的知识卡片。
function findReference(references: KnowledgeReference[], referenceId: string) {
  return references.find((item) => item.reference_id.toUpperCase() === referenceId.toUpperCase()) ?? null;
}

// 把 Markdown 知识卡片转成适合弹窗阅读的短段落。
function formatKnowledgeLines(reference: KnowledgeReference) {
  const raw = reference.display_content || reference.excerpt || reference.content || "当前知识卡片暂无详细内容。";
  return raw
    .split(/\n+/)
    .map((line) => line
      .replace(/^#{1,6}\s*/, "")
      .replace(/^\s*[-*]\s*/, "")
      .replace(/\*\*/g, "")
      .replace(/\[\[([^\]|]+)(?:\|[^\]]+)?\]\]/g, "$1")
      .replace(/!\[\[[^\]]+\]\]/g, "")
      .trim())
    .filter(Boolean)
    .slice(0, 14);
}

// 渲染完整评图报告。
export function ReportPage({ go }: PageProps) {
  const { chatMessages, downloadCurrentReport, draft, history, project, projects, report, sendQuestion, startEvaluation, submission } = useWorkspace();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [drilldownSource, setDrilldownSource] = useState<AgentEvaluation | null>(null);
  const [drilldownSourceIndex, setDrilldownSourceIndex] = useState<number | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedIssue, setSelectedIssue] = useState<ReportIssue | null>(null);
  const reviewEvaluation = useMemo(() => findReviewEvaluation(report?.agent_evaluations ?? []), [report]);
  const schemeDimensions = useMemo(() => buildSchemeDimensions(report?.agent_evaluations ?? []), [report]);
  const dimensions = drilldownSource ? buildDrilldownDimensions(drilldownSource) : schemeDimensions;
  const activeIndex = Math.min(selectedIndex, dimensions.length - 1);
  const selected = dimensions[activeIndex];
  const focusEvaluation = drilldownSource ?? null;
  const scoreValue = Math.round(focusEvaluation?.score ?? report?.overall_score ?? 78);
  const scoreLabel = focusEvaluation?.dimension ?? "综合评分";
  const summaryTitle = focusEvaluation ? `${focusEvaluation.dimension}评价` : "综合评审结果";
  const summaryText = focusEvaluation?.summary ?? reviewEvaluation?.summary ?? report?.summary ?? "方案整体完成度较高，功能与流线表现稳定，场地回应具备基础合理性。当前需要优先处理几何形式表达与结构构造定位之间的对应关系。";
  const reportProjectName = project?.name || draft.name;
  const reportVersionName = getCurrentReportVersionLabel(submission, history, project, projects);
  const issues = useMemo(() => {
    const reportIssues = buildReportIssues(report);
    return reportIssues.length ? reportIssues : [
      { level: "must_fix" as const, label: "必须修改", text: "消防疏散距离需要复核。", summary: "消防疏散距离需要复核", referenceIds: [] },
      { level: "should_improve" as const, label: "重点优化", text: "公共空间动线仍有绕行。", summary: "公共空间动线仍有绕行", referenceIds: [] },
      { level: "optional_improvements" as const, label: "建议关注", text: "局部节点缺少缓冲。", summary: "局部节点缺少缓冲", referenceIds: [] },
      { level: "strengths" as const, label: "当前优势", text: "核心功能分区具备基础清晰度。", summary: "核心功能分区具备基础清晰度", referenceIds: [] },
    ];
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
  return (
    <div className="relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} />
      <h1 className="absolute left-[307px] top-[53px] text-[34px] font-bold leading-[44px]">评图报告 {reportProjectName} <span className="text-[24px] text-[#6b7385]">{reportVersionName}</span></h1>
      <p className="absolute left-[309px] top-[107px] text-[14px] leading-[22px] text-[#53565e]">多维度评分体系</p>
      <div className="font-inter absolute left-[833px] top-[99px] flex gap-[14px]">
        <Button kind="white" className="report-top-action-button w-[114px]" onClick={() => go("confirm")}>查看项目信息</Button>
        <Button className="report-top-action-button w-[102px]" onClick={downloadCurrentReport}>下载报告</Button>
      </div>
      <div className="font-inter absolute left-[1251px] top-[99px] flex gap-[14px]">
        <Button kind="white" className="report-top-action-button w-[116px]" onClick={() => { go("processing"); void startEvaluation(); }}>重新生成</Button>
        <Button kind="purple" className="report-top-action-button w-[132px] rounded-[12px]" onClick={() => go("history")}>历史版本对比</Button>
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
        <div className="absolute left-[22px] top-[44px] z-10 grid w-[712px] grid-cols-4 gap-[8px]">
          {dimensions.map((item, index) => <button onClick={() => setSelectedIndex(index)} className={`report-dimension-tab grid h-[36px] grid-cols-[1fr_auto] items-center gap-2 px-[12px] text-[12px] font-bold ${index === activeIndex ? "rounded-t-[10px] bg-[#171719] text-white" : "rounded-[10px] bg-[#fafbfc] text-[#53565e]"}`} key={`${item.agent_type}-${item.dimension}`}><span className="truncate">{item.dimension}</span><span className="text-[12px] leading-4">{Math.round(item.score)}</span></button>)}
        </div>
        <div className={`absolute left-[22px] top-[80px] h-[156px] w-[712px] bg-[#171719] px-4 py-[14px] text-white ${getDimensionPanelRadius(activeIndex, dimensions.length)}`}>
          <b className="absolute right-[25px] top-[22px] text-[48px] leading-[54px]">{Math.round(selected.score)}</b>
          <div className="absolute left-4 top-[22px] h-[78px] w-[560px] overflow-hidden pr-3">
            <p className="text-[12px] leading-5">{selected.summary}</p>
          </div>
          <Button kind="white" className="report-top-action-button absolute bottom-4 right-4 h-[34px] w-[106px]" onClick={openDimensionDetail}>{drilldownSource ? "返回总评" : "查看详情"}</Button>
        </div>
        <h3 className="absolute left-[22px] top-[252px] text-[16px] font-bold leading-[22px]">反馈要点</h3>
        <div className="report-light-scroll absolute left-[22px] top-[281px] h-[147px] w-[712px] overflow-y-auto">
          <div className="space-y-2">
            {issues.map((issue, index) => <TraceRow key={`${issue.text}-${index}`} issue={issue} onClick={() => setSelectedIssue(issue)} />)}
          </div>
        </div>
      </section>
      <ChatPanel messages={chatMessages} sendQuestion={sendQuestion} />
      {detailOpen && <ReportOverlay title={selected.dimension} subtitle="专项评图详情" onClose={() => setDetailOpen(false)} lines={[...selected.issues, ...selected.suggestions]} fallback={selected.summary} />}
      {selectedIssue && <IssueOverlay issue={selectedIssue} references={report?.references ?? []} onClose={() => setSelectedIssue(null)} />}
    </div>
  );
}

// 按当前阶段固定报告页主维度，避免把专项子分数误显示成主维度。
function buildSchemeDimensions(evaluations: AgentEvaluation[]) {
  return schemeDimensionSpecs.map((spec, index) => {
    const matched = evaluations.find((item) => {
      const agentMatched = item.agent_type === spec.agent;
      const labelMatched = spec.aliases.includes(item.dimension);
      const subAgent = item.agent_type.startsWith("function_agent_");
      return !subAgent && (agentMatched || labelMatched);
    });
    const fallback = fallbackDimensions[index];
    if (matched) {
      return { ...matched, dimension: spec.label };
    }
    return fallback;
  });
}

// 提取综合评审结果，作为上方整体评价的正文来源。
function findReviewEvaluation(evaluations: AgentEvaluation[]) {
  return evaluations.find((item) => item.agent_type === "review_agent" || item.dimension === "综合评审");
}

// 评分维度标签和黑色内容块需要像同一个整体，选中边缘处不留圆角空隙。
function getDimensionPanelRadius(selectedIndex: number, total: number) {
  if (selectedIndex === 0) return "rounded-b-[12px] rounded-tr-[12px]";
  if (selectedIndex === total - 1) return "rounded-b-[12px] rounded-tl-[12px]";
  return "rounded-[12px]";
}

// 判断专项评价中是否包含可下钻的子评分。
function hasSubScores(evaluation: AgentEvaluation) {
  const subScores = evaluation.details?.sub_scores;
  return Boolean(subScores && typeof subScores === "object" && Object.keys(subScores as Record<string, unknown>).length);
}

// 将功能、场地、形式、结构等专项评价展开成子维度标签。
function buildDrilldownDimensions(evaluation: AgentEvaluation): AgentEvaluation[] {
  const subScores = evaluation.details?.sub_scores;
  if (!subScores || typeof subScores !== "object") return [evaluation];
  const parentDimension = normalizeMetricName(evaluation.dimension);
  const subItems = Object.entries(subScores as Record<string, unknown>).map(([name, raw], index) => {
    const item = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
    const score = typeof raw === "number" ? raw : Number(item.score ?? 0);
    const reason = String(item.reason ?? item.evidence ?? evaluation.summary);
    const evidence = item.evidence ? [String(item.evidence)] : [];
    return {
      agent_type: `${evaluation.agent_type}_sub_${index}`,
      dimension: name,
      score: Number.isFinite(score) ? score : 0,
      summary: reason,
      strengths: evidence,
      issues: [],
      suggestions: [],
      details: {},
    };
  }).filter((item) => normalizeMetricName(item.dimension) !== parentDimension);
  return subItems.length ? subItems : [evaluation];
}

// 渲染综合得分圆环。
function ScoreRing({ score, label }: { score: string; label: string }) {
  const numericScore = Number(score);
  const scoreDegree = Number.isFinite(numericScore) ? Math.max(0, Math.min(100, numericScore)) * 3.6 : 280;
  return (
    <div className="report-score-ring absolute left-[22px] top-[27px] h-[98px] w-[98px] rounded-full" style={{ "--score-degree": `${scoreDegree}deg` } as CSSProperties}>
      <div className="absolute left-[10px] top-[10px] z-[2] flex h-[78px] w-[78px] flex-col items-center justify-center rounded-full bg-white">
        <b className="text-[34px] leading-9 text-[#6c4dff]">{score}</b>
        <span className="max-w-[64px] truncate text-[9px] text-[#53565e]">{label}</span>
      </div>
      <span className="absolute left-1/2 top-[86px] z-[3] flex h-6 w-[52px] -translate-x-1/2 items-center justify-center rounded-full border border-[#6c4dff] bg-[#efe9ff] text-[11px] font-bold text-[#6c4dff]">{getScoreGrade(Number(score))}</span>
    </div>
  );
}

// 根据分数显示圆环下方等级。
function getScoreGrade(score: number) {
  if (score >= 85) return "优秀";
  if (score >= 70) return "良好";
  if (score >= 60) return "合格";
  return "待改进";
}

// 渲染反馈要点行，摘要和知识编号保持紧凑。
function TraceRow({ issue, onClick }: { issue: ReportIssue; onClick?: () => void }) {
  const tone = getIssueTone(issue.level);
  return (
    <button type="button" onClick={onClick} className="grid min-h-[38px] w-full grid-cols-[84px_1fr_auto_auto] items-center gap-2 rounded-[10px] bg-[#fafbfc] py-2 pl-0 pr-3 text-left hover:bg-[#f4f6f8]">
      <span className={`flex h-7 items-center justify-center rounded-full border px-2 text-[10px] font-bold leading-[12px] ${tone.badge}`}>{issue.label}</span>
      <b className="report-trace-text text-[12px] font-bold leading-4 text-[#171719]">{issue.summary}</b>
      <span className="flex max-w-[180px] flex-wrap justify-end gap-1">
        {issue.referenceIds.map((referenceId) => <span className="rounded-full bg-[#efe9ff] px-2 py-1 text-[10px] font-bold leading-none text-[#6c4dff]" key={referenceId}>[{referenceId}]</span>)}
      </span>
      <span className="ml-auto text-[10px] font-medium text-[#53565e]">反馈详情</span>
    </button>
  );
}

// 展示问题详情，并在同一弹窗内切换知识库卡片。
function IssueOverlay({ issue, references, onClose }: { issue: ReportIssue; references: KnowledgeReference[]; onClose: () => void }) {
  const [activeReferenceId, setActiveReferenceId] = useState<string | null>(null);
  const activeReference = activeReferenceId ? findReference(references, activeReferenceId) : null;
  const tone = getIssueTone(issue.level);
  return (
    <div className="absolute inset-0 z-20 bg-[#171719]/30" onClick={onClose}>
      <section className="figma-shadow absolute left-[462px] top-[144px] h-[530px] w-[612px] rounded-[22px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        {activeReference ? (
          <>
            <button type="button" className="issue-overlay-nav absolute right-7 top-8 text-[#6c4dff]" onClick={() => setActiveReferenceId(null)}>返回反馈详情</button>
            <p className="text-[16px] font-bold text-[#6c4dff]">知识库卡片</p>
            <h2 className="mt-3 max-w-[430px] text-[24px] font-bold">{activeReference.title}</h2>
            <div className="mt-6">
            <div className="report-light-scroll h-[344px] overflow-y-auto pr-4">
              <p className="text-[13px] font-bold text-[#9a9ea7]">{activeReference.reference_id} · {activeReference.source_type || "知识库"}</p>
              <div className="mt-5 space-y-3 text-[14px] leading-7 text-[#53565e]">
                {formatKnowledgeLines(activeReference).map((line, index) => <p key={`${activeReference.reference_id}-${index}`}>{line}</p>)}
              </div>
              {activeReference.image_urls?.length > 0 && (
                <div className="mt-4 grid grid-cols-2 gap-3">
                  {activeReference.image_urls.slice(0, 4).map((image) => <img className="h-28 w-full rounded-[12px] object-cover" src={image.url} alt={image.name ?? activeReference.title} key={image.url} />)}
                </div>
              )}
            </div>
            </div>
          </>
        ) : (
          <>
            <button type="button" aria-label="关闭" onClick={onClose} className="absolute right-6 top-6 flex h-10 w-10 items-center justify-center rounded-full border border-[#e8ebef] bg-white text-[24px] leading-none text-[#9a9ea7] hover:bg-[#f4f6f8]">×</button>
            <p className="text-[16px] font-bold text-[#6c4dff]">反馈详情</p>
            <div className="mt-3 flex max-w-[480px] items-start gap-3">
              <h2 className="min-w-0 text-[24px] font-bold leading-tight">{issue.summary}</h2>
              <span className={`mt-1 inline-flex h-8 shrink-0 items-center justify-center rounded-full border px-3 text-[12px] font-bold ${tone.badge}`}>{issue.label}</span>
            </div>
            <p className="report-light-scroll mt-8 max-h-[128px] overflow-y-auto pr-3 text-[16px] leading-8 text-[#171719]">{issue.text}</p>
            <div className="absolute bottom-7 left-7 right-7">
              <h3 className="text-[14px] font-bold">关联知识库</h3>
              <div className="report-light-scroll mt-3 h-[142px] space-y-2 overflow-y-auto pr-3">
                {issue.referenceIds.length ? issue.referenceIds.map((referenceId) => {
                  const reference = findReference(references, referenceId);
                  return (
                    <button type="button" className="knowledge-link-row grid min-h-[42px] w-full grid-cols-[52px_1fr_54px] items-center gap-3 rounded-[12px] border border-[#e8ebef] bg-white px-3 py-2 text-left hover:bg-[#f4f6f8]" onClick={() => setActiveReferenceId(referenceId)} key={referenceId}>
                      <b className="knowledge-link-text text-[#6c4dff]">[{referenceId}]</b>
                      <span className="knowledge-link-text truncate font-bold text-[#171719]">{reference?.title ?? "知识库依据"}</span>
                      <span className="knowledge-link-text justify-self-end font-bold text-[#6c4dff]">查看</span>
                    </button>
                  );
                }) : <p className="rounded-[12px] bg-[#fafbfc] px-4 py-3 text-[12px] text-[#9a9ea7]">这条问题暂未匹配到知识库编号。</p>}
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

// 在不改变主页面布局的前提下展示报告详情。
function ReportOverlay({ title, subtitle, lines, fallback, onClose }: { title: string; subtitle: string; lines: string[]; fallback: string; onClose: () => void }) {
  const visibleLines = lines.length ? lines : [fallback];
  return (
    <div className="absolute inset-0 z-20 bg-[#171719]/30" onClick={onClose}>
      <section className="figma-shadow absolute left-[482px] top-[174px] h-[470px] w-[572px] rounded-[22px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        <button type="button" aria-label="关闭" onClick={onClose} className="absolute right-6 top-6 flex h-10 w-10 items-center justify-center rounded-full border border-[#e8ebef] bg-white text-[24px] leading-none text-[#9a9ea7] hover:bg-[#f4f6f8]">×</button>
        <p className="text-[12px] text-[#6c4dff]">{subtitle}</p>
        <h2 className="mt-2 text-[24px] font-bold">{title}</h2>
        <div className="report-light-scroll mt-6 h-[304px] space-y-3 overflow-y-auto pr-4 text-[13px] leading-6 text-[#53565e]">
          {visibleLines.map((line, index) => <p className="rounded-[12px] bg-[#fafbfc] px-4 py-3" key={`${line}-${index}`}>{line}</p>)}
        </div>
      </section>
    </div>
  );
}

// 渲染报告右侧继续对话区。
function ChatPanel({ messages, sendQuestion }: { messages: { role: "user" | "assistant"; content: string }[]; sendQuestion: (content: string) => Promise<void> }) {
  const { draft, setDraftField } = useWorkspace();
  const { profile } = useProfile();
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [modelOpen, setModelOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const displayMessages = messages.length ? messages : [
    { role: "assistant" as const, content: "报告已生成。我可以继续解释扣分原因、定位图纸问题，或生成下一轮优化动作。" },
    { role: "user" as const, content: "为什么功能与流线得分相对较高？" },
    { role: "assistant" as const, content: "主要原因是功能分区清晰，公共空间与主要入口之间的关系明确。但后勤路径和消防距离仍需要复核，所以当前得分停留在 82。" },
  ];
  const modelValue = draft.modelProvider === "gemini" ? "gemini|gemini-2.5-flash" : "dashscope|qwen3.6-plus";
  const modelLabel = draft.modelProvider === "gemini" ? "gemini-2.5-flash" : "qwen3.6-plus";
  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages.length, sending]);
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
  return (
    <section className="font-inter white-panel figma-shadow absolute left-[1089px] top-[149px] h-[658px] w-[424px] overflow-hidden rounded-[22px] px-[22px] py-[20px]">
      <h2 className="text-[18px] font-bold">继续与系统对话</h2>
      <p className="mt-1 text-[12px] text-[#9a9ea7]">追问报告原因、定位问题或生成优化动作</p>
      <div ref={scrollRef} className="report-chat-scroll absolute left-[22px] right-[10px] top-[87px] bottom-[182px] overflow-y-auto pr-[14px]">
        <div className="space-y-3">
          {displayMessages.map((message, index) => message.role === "user" ? (
            <div className="flex justify-end gap-3" key={`${message.role}-${index}-${message.content}`}>
              <p className="w-[272px] rounded-[12px] border border-[#e8ebef] bg-[#fafbfc] px-3 py-3 text-[12px] leading-5"><b className="block text-[#6b7385]">你的追问</b>{message.content}</p>
              {profile.avatarDataUrl ? <img className="h-9 w-9 rounded-full object-cover" src={profile.avatarDataUrl} /> : <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#171719] text-[12px] font-bold text-white">我</span>}
            </div>
          ) : (
            <div className="flex gap-3" key={`${message.role}-${index}-${message.content}`}>
              <img className="h-9 w-9" src="/assets/v1/report-avatar.svg" />
              <p className={`w-[276px] rounded-[12px] border px-3 py-3 text-[12px] leading-5 ${index === 0 ? "border-[#e8ebef] bg-white" : "border-[#d9ceff] bg-[#fbfaff]"}`}><b className={`block ${index === 0 ? "text-[#171719]" : "text-[#6c4dff]"}`}>{index === 0 ? "" : "系统回答"}</b>{message.content}</p>
            </div>
          ))}
        </div>
        <b className="mt-4 block text-[12px]">你可以继续追问</b>
        <span className="mt-1 block h-4 text-[11px] text-[#9a9ea7]">{sending ? "正在调用系统回答..." : sendError}</span>
        <div className="mt-2 flex flex-wrap gap-2 text-[11px] font-bold">
          <button type="button" disabled={sending} className="rounded-full border border-[#e8ebef] px-3 py-2 disabled:opacity-60" onClick={() => void submit("生成人口优化方案")}>生成人口优化方案</button>
          <button type="button" disabled={sending} className="rounded-full border border-[#e8ebef] px-3 py-2 disabled:opacity-60" onClick={() => void submit("解释结构与构造扣分")}>解释结构与构造扣分</button>
          <button type="button" disabled={sending} className="rounded-full border border-[#e8ebef] px-3 py-2 disabled:opacity-60" onClick={() => void submit("列出必须修改项")}>列出必须修改项</button>
        </div>
      </div>
      <div className="absolute bottom-6 left-[22px] h-[126px] w-[380px] rounded-[14px] border border-[#e8ebef] bg-[#fafbfc] px-3 py-2 text-[12px] text-[#9a9ea7]">
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="继续追问评图进度..." className="h-[62px] w-full resize-none bg-transparent outline-none placeholder:text-[#9a9ea7]" />
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
        <Button className="report-chat-send-button absolute bottom-2 right-2 h-[27px] w-[55px] text-[12px]" disabled={sending} onClick={() => void submit()}>{sending ? "..." : "发送"}</Button>
      </div>
    </section>
  );
}

const metricAliases: Record<string, string[]> = {
  功能与流线: ["功能与流线"],
  场地与回应: ["场地与回应", "场地回应"],
  几何形式: ["几何形式", "形式与构图", "形式与沟通"],
  结构与构造: ["结构与构造", "结构与可行性"],
};

// 将历史分数和报告维度名称归一，避免旧数据命名不同导致读错分数。
function normalizeMetricName(name: string) {
  const matched = Object.entries(metricAliases).find(([, aliases]) => aliases.includes(name));
  return matched?.[0] ?? name;
}

// 读取某个历史版本在当前指标下的真实分数。
function getHistoryMetricScore(item: SubmissionHistory, metric: string) {
  if (metric === "总得分变化") return item.overall_score ?? null;
  const aliases = metricAliases[metric] ?? [metric];
  const matchedKey = aliases.find((name) => typeof item.dimension_scores?.[name] === "number");
  return matchedKey ? item.dimension_scores?.[matchedKey] ?? null : null;
}

// 渲染历史版本对比页。
export function HistoryPage({ go }: PageProps) {
  const { history, openSubmission, project, projects } = useWorkspace();
  const [metric, setMetric] = useState("总得分变化");
  const [groupHistory, setGroupHistory] = useState<SubmissionHistory[]>(history);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  useEffect(() => {
    let mounted = true;
    if (!project) {
      setGroupHistory(history);
      return () => { mounted = false; };
    }
    const projectName = project.name.trim();
    const relatedProjects = projects.filter((item) => item.name.trim() === projectName);
    void Promise.all(relatedProjects.map((item) => getProjectHistory(item.id).catch(() => []))).then((items) => {
      if (!mounted) return;
      const merged = items.flat().sort((a, b) => {
        const aTime = new Date(a.created_at ?? "").getTime() || 0;
        const bTime = new Date(b.created_at ?? "").getTime() || 0;
        return aTime - bTime || a.id - b.id;
      });
      setGroupHistory(merged.length ? merged : history);
    });
    return () => { mounted = false; };
  }, [history, project, projects]);
  const versions = groupHistory;
  const values = versions.map((item) => getHistoryMetricScore(item, metric));
  const validPoints = values.flatMap((score, index) => {
    if (score == null) return [];
    const x = versions.length === 1 ? 550 : 54 + index * (994 / Math.max(1, versions.length - 1));
    const y = 400 - (score - 50) * 7;
    return [{ x, y: Math.max(32, Math.min(400, y)), score, index, item: versions[index] }];
  });
  const firstScore = validPoints[0]?.score ?? 0;
  const latestScore = validPoints[validPoints.length - 1]?.score ?? 0;
  const hoveredPoint = hoveredIndex == null ? null : validPoints.find((point) => point.index === hoveredIndex) ?? null;
  return (
    <div className="relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} />
      <PageTitle title="历史版本对比" subtitle={`对比${project?.name ? `“${project.name}”` : "当前项目"}的版本评分与修改建议，追踪设计演变。`} />
      <Button kind="purple" className="absolute right-[23px] top-[100px] w-[132px] rounded-[12px]" onClick={() => go("report")}>返回</Button>
      <Card className="absolute left-[307px] top-[150px] h-[650px] w-[1206px] p-6">
        <h2 className="text-[20px] font-bold">版本评分趋势</h2>
        <p className="mt-1 text-[13px] text-[#6b7280]">按版本迭代顺序从左至右查看评分变化；切换上方指标即可查看不同维度折线。</p>
        <div className="mt-5 flex gap-3">{["总得分变化","功能与流线","场地与回应","几何形式","结构与构造"].map(text => <Button kind={metric === text ? "dark" : "white"} className="h-9" key={text} onClick={() => setMetric(text)}>{text}</Button>)}<div className="ml-auto h-[54px] w-[362px] rounded-[12px] border border-[#e8ebef] bg-white px-5 py-4 text-[13px] text-[#9a9ea7]">当前显示　 <b className="text-[#171719]">{metric}</b>　 <b className="float-right text-[#159447]">V1 → V{versions.length}　{latestScore - firstScore >= 0 ? "+" : ""}{Math.round(latestScore - firstScore)}</b></div></div>
        <div className="relative mt-2 h-[450px]" onMouseLeave={() => setHoveredIndex(null)}>
          <svg viewBox="0 0 1080 450" className="absolute inset-0 h-full w-full">
            {[40,100,160,220,280,340,400].map(y => <line key={y} x1="54" y1={y} x2="1050" y2={y} stroke="#d9dde3" strokeWidth="1" />)}
            {validPoints.length > 1 && <polyline points={validPoints.map((point) => `${point.x},${point.y}`).join(" ")} fill="none" stroke="#6c4dff" strokeWidth="4" />}
            {validPoints.map((point) => (
              <g key={`${point.item.id}-${point.index}`}>
                <circle
                  className={hoveredIndex === point.index ? "history-point-active" : ""}
                  cx={point.x}
                  cy={point.y}
                  r="7"
                  fill="#6c4dff"
                  stroke="white"
                  strokeWidth="2"
                  onMouseEnter={() => setHoveredIndex(point.index)}
                />
                <text x={point.x - 8} y={point.y - 22} fill="#171719" fontSize="13" fontWeight="700">{Math.round(point.score)}</text>
              </g>
            ))}
          </svg>
          <div className="absolute bottom-[4px] left-[34px] right-[22px] flex justify-between text-[12px] text-[#53565e]">{versions.map((item, index) => <button type="button" key={`${item.id}-${index}`} onClick={() => item.id && void openSubmission(item.id).then(() => go("report"))}>{getHistoryVersionLabel(item, index)}</button>)}</div>
          {!versions.length && <p className="absolute left-0 right-0 top-[170px] text-center text-[14px] text-[#9a9ea7]">暂无可对比的历史版本。</p>}
          {hoveredPoint && (
            <div
              className="absolute h-[126px] w-[248px] rounded-[12px] bg-[#6c4dff] p-4 text-[12px] leading-6 text-white"
              style={{ left: `${Math.min(78, (hoveredPoint.x / 1080) * 100 + 3)}%`, top: `${Math.max(8, (hoveredPoint.y / 450) * 100 - 14)}%` }}
            >
              <b className="text-[15px]">{getHistoryVersionLabel(hoveredPoint.item, hoveredPoint.index)} <span className="float-right">{metric === "总得分变化" ? "总分" : "得分"} {Math.round(hoveredPoint.score)}</span></b>
              <p className="mt-2 line-clamp-3">{hoveredPoint.item.summary || hoveredPoint.item.title || "该版本暂无补充说明。"}</p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
