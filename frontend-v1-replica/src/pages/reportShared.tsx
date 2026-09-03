// 报告展示组件：集中处理真实分项、反馈依据、评分色阶和详情弹窗。
import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { apiUrl } from "../api/client";
import { ZoomableImageStage } from "../components";
import { useWorkspace } from "../state/workspace";
import type { AgentEvaluation, DrawingFile, FeedbackItem, KnowledgeImage, KnowledgeReference, OverallReport, Submission } from "../types/api";
import { ReportKnowledgeContent, useReportKnowledgeDetail } from "./reportKnowledgeCard";

export const schemeDimensionSpecs = [
  { agent: "function_agent", label: "功能与流线", aliases: ["功能与流线"] },
  { agent: "site_agent", label: "场地与回应", aliases: ["场地与回应", "场地回应"] },
  { agent: "form_agent", label: "几何形式", aliases: ["几何形式", "形式与构图", "形式与沟通"] },
  { agent: "structure_agent", label: "结构与构造", aliases: ["结构与构造", "结构与可行性"] },
  { agent: "concept_agent", label: "设计概念", aliases: ["设计概念", "概念与立意"] },
  { agent: "drawing_agent", label: "图面表达", aliases: ["图面表达", "图纸表达"] },
];

export type IssueLevel = "must_fix" | "should_improve" | "optional_improvements" | "strengths";
export const MAX_REFERENCE_LINKS = 3;

export interface ReportIssue {
  level: IssueLevel;
  label: string;
  text: string;
  summary: string;
  referenceIds: string[];
}

// 历史版本列表优先显示用户重命名后的版本名；默认名称与左侧栏保持一致。
export function summarizeIssue(text: string) {
  const clean = text.replace(/\s+/g, " ").replace(/\[(K\d+)\]/gi, "").trim();
  const firstPunctuation = clean.search(/[：:。！？!?；;]/);
  const firstSentence = firstPunctuation > 0 ? clean.slice(0, firstPunctuation) : clean;
  return firstSentence.length > 58 ? `${firstSentence.slice(0, 58)}...` : firstSentence;
}

// 整理待修改问题，优先读取后端返回的知识库引用关系。
export function buildReportIssues(report: ReturnType<typeof useWorkspace>["report"]): ReportIssue[] {
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
export function normalizeReferenceIds(referenceIds: string[], text: string, references: KnowledgeReference[]) {
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
export function getReferenceMatchScore(text: string, reference: KnowledgeReference) {
  const source = `${reference.title} ${reference.dimension} ${reference.excerpt} ${reference.display_content}`.toLowerCase();
  const normalizedText = text.toLowerCase();
  const words = Array.from(new Set(normalizedText.match(/[a-zA-Z0-9]{3,}/g) ?? []));
  const cnChars = Array.from(new Set((text.match(/[\u4e00-\u9fa5]/g) ?? [])));
  const wordScore = words.reduce((score, keyword) => source.includes(keyword) ? score + Math.min(keyword.length, 6) : score, 0);
  const charScore = cnChars.reduce((score, char) => source.includes(char) ? score + 1 : score, 0);
  return wordScore + charScore;
}

// 按重要等级返回低饱和颜色，和当前黑白紫界面保持一致。
export function getIssueTone(level: IssueLevel) {
  const tones = {
    must_fix: { badge: "bg-[#fff1f1] text-[#b44747] border-[#f1d0d0]", rail: "bg-[#d86464]" },
    should_improve: { badge: "bg-[#fff6e8] text-[#a86514] border-[#efd8b4]", rail: "bg-[#d99a42]" },
    optional_improvements: { badge: "bg-[#f0f4ff] text-[#526aa3] border-[#d8e0f5]", rail: "bg-[#7b8fcb]" },
    strengths: { badge: "bg-[#edf8f2] text-[#2f7f55] border-[#cde8d8]", rail: "bg-[#5eaa7b]" },
  } satisfies Record<IssueLevel, { badge: string; rail: string }>;
  return tones[level];
}

// 根据知识编号读取本次报告快照中的知识卡片。
export function findReference(references: KnowledgeReference[], referenceId: string) {
  return references.find((item) => item.reference_id.toUpperCase() === referenceId.toUpperCase()) ?? null;
}

// 优先展示知识库真实编号；长编号仅在界面中省略中段，完整值保留在悬停提示中。
export function getReferenceDisplay(referenceId: string, references: KnowledgeReference[]) {
  const reference = findReference(references, referenceId);
  const fullId = reference?.library_item_id?.trim() || referenceId.toUpperCase();
  const label = fullId.length > 14 ? `${fullId.slice(0, 8)}…${fullId.slice(-4)}` : fullId;
  return { fullId, label, title: reference?.title ?? "知识库依据" };
}

// 把模型回答中的 Markdown 加粗转换为真实粗体显示。
export function renderChatText(content: string) {
  const text = content.trim();
  const parts = text.split(/(\*\*[^*]+\*\*|__[^_]+__)/g).filter(Boolean);
  return parts.map((part, index) => {
    const boldMatch = part.match(/^\*\*([^*]+)\*\*$|^__([^_]+)__$/);
    if (boldMatch) {
      return <strong className="font-bold text-[#171719]" key={`${part}-${index}`}>{boldMatch[1] ?? boldMatch[2]}</strong>;
    }
    return part;
  });
}

// 根据本次报告生成更贴近当前问题的三个追问建议。
export function buildChatSuggestions(report: OverallReport | null): string[] {
  const dimensions = buildSchemeDimensions(report?.agent_evaluations ?? []);
  const weakest = dimensions.length ? dimensions.reduce((current, item) => item.score < current.score ? item : current, dimensions[0]) : null;
  const issues = buildReportIssues(report);
  const primaryIssue = issues.find((item) => item.level === "must_fix") ?? issues[0];
  return [
    weakest ? `为什么${weakest.dimension}只有${Math.round(weakest.score)}分？` : "本次扣分主要原因是什么？",
    primaryIssue ? `这个问题怎么改：${primaryIssue.summary}` : "下一步最应该先改哪里？",
    "请按优先级列出三步修改建议",
  ];
}

// 把报告长段落切成更容易阅读的小段。
export function splitReadableParagraphs(text: string) {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return ["暂无说明。"];
  const sentences = clean.match(/[^。！？；;.!?]+[。！？；;.!?]?/g)?.map((item) => item.trim()).filter(Boolean) ?? [clean];
  const paragraphs: string[] = [];
  for (let index = 0; index < sentences.length; index += 2) {
    paragraphs.push(sentences.slice(index, index + 2).join(""));
  }
  return paragraphs.length ? paragraphs : [clean];
}

export function floorText(floor: number): string {
  return ["零", "一", "二", "三", "四", "五", "六", "七"][floor] ?? String(floor);
}

export function displayDrawingName(name: string): string {
  return name.replace(/\.[^.\\/]+$/, "");
}

export function drawingTypeLabel(type: string): string {
  const floorMatch = /^plan-(\d+)$/.exec(type);
  if (floorMatch) return `${floorText(Number(floorMatch[1]))}层平面图`;
  return { site: "总平面图", plan: "首层平面图", section: "剖面图", elevation: "立面图", analysis: "分析图", render: "效果图" }[type] ?? "待识别";
}

export function isImageDrawing(drawing: DrawingFile) {
  return drawing.mime_type.startsWith("image/");
}

export function getReportModelLabel(submission: Submission | null, draft: ReturnType<typeof useWorkspace>["draft"]) {
  return submission?.selected_model_name || draft.modelLabel || draft.modelName || "qwen3.8-max";
}

export const reportAgentLabels: Record<string, string> = {
  site_agent: "场地 Agent",
  function_agent: "功能与流线 Agent",
  form_agent: "几何形式 Agent",
  structure_agent: "结构 Agent",
  concept_agent: "设计概念 Agent",
  drawing_agent: "图面表达 Agent",
  review_agent: "综合评审 Agent",
};

export function getReportAgentLabel(type: string) {
  return reportAgentLabels[type] ?? type;
}

// 读取报告保存时的真实 Agent 和任务书权重，避免后来修改草稿后显示错位。
export function getReportEvaluationSnapshot(report: OverallReport | null) {
  const context = report?.evaluation_context ?? {};
  const enabledAgents = Array.isArray(context.enabled_agents)
    ? context.enabled_agents.filter((item): item is string => typeof item === "string")
    : [];
  const rawWeights = context.dimension_weights;
  const weights = rawWeights && typeof rawWeights === "object"
    ? Object.entries(rawWeights).flatMap(([agent, value]) => typeof value === "number" ? [{ agent, value }] : [])
    : [];
  const rawTaskBook = context.task_book;
  const taskBook = rawTaskBook && typeof rawTaskBook === "object" ? rawTaskBook as Record<string, unknown> : {};
  const taskBookSources = Array.isArray(taskBook.source_files)
    ? taskBook.source_files.filter((item): item is string => typeof item === "string")
    : [];
  return { enabledAgents, taskBookSources, weights };
}

// 渲染完整评图报告。
export function buildSchemeDimensions(evaluations: AgentEvaluation[]) {
  return schemeDimensionSpecs.flatMap((spec) => {
    const matched = evaluations.find((item) => {
      const agentMatched = item.agent_type === spec.agent;
      const labelMatched = spec.aliases.includes(item.dimension);
      const subAgent = item.agent_type.startsWith("function_agent_");
      return !subAgent && (agentMatched || labelMatched);
    });
    if (matched) {
      return [{ ...matched, dimension: spec.label }];
    }
    return [];
  });
}

// 提取综合评审结果，作为上方整体评价的正文来源。
export function findReviewEvaluation(evaluations: AgentEvaluation[]) {
  return evaluations.find((item) => item.agent_type === "review_agent" || item.dimension === "综合评审");
}

// 评分维度标签和黑色内容块需要像同一个整体，选中边缘处不留圆角空隙。
export function getDimensionPanelRadius(selectedIndex: number, total: number) {
  if (selectedIndex === 0) return "rounded-b-[12px] rounded-tr-[12px]";
  if (selectedIndex === total - 1) return "rounded-b-[12px] rounded-tl-[12px]";
  return "rounded-[12px]";
}

// 评分卡片摘要最多显示五行，只有真实超过五行时才显示滚动条。
export function DimensionSummaryText({ selected }: { selected: AgentEvaluation }) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [scrollable, setScrollable] = useState(false);
  const contentKey = `${selected.agent_type}-${selected.dimension}-${selected.summary}`;
  useLayoutEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    const checkOverflow = () => {
      const lineHeight = 20;
      const paragraphGap = 4;
      const visibleParagraphs = Math.max(0, splitReadableParagraphs(selected.summary).length - 1);
      const fiveLineHeight = lineHeight * 5 + Math.min(visibleParagraphs, 1) * paragraphGap;
      setScrollable(node.scrollHeight > fiveLineHeight + 1);
    };
    checkOverflow();
    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(checkOverflow);
    resizeObserver?.observe(node);
    window.addEventListener("resize", checkOverflow);
    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("resize", checkOverflow);
    };
  }, [contentKey]);
  return (
    <div ref={scrollRef} className={`report-hover-scroll report-hover-scroll-on-dark absolute left-4 top-[20px] h-[116px] w-[575px] pr-4 ${scrollable ? "overflow-y-auto" : "overflow-hidden"}`}>
      <div className="space-y-1 text-[12px] leading-5">
        {splitReadableParagraphs(selected.summary).map((paragraph, index) => <p key={`${selected.agent_type}-${index}`}>{paragraph}</p>)}
      </div>
    </div>
  );
}

// 判断专项评价中是否包含可下钻的子评分。
export function hasSubScores(evaluation: AgentEvaluation) {
  const subScores = evaluation.details?.sub_scores;
  return Boolean(subScores && typeof subScores === "object" && Object.keys(subScores as Record<string, unknown>).length);
}

// 将功能、场地、形式、结构等专项评价展开成子维度标签。
export function buildDrilldownDimensions(evaluation: AgentEvaluation): AgentEvaluation[] {
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

export interface ReportSubScore {
  name: string;
  score: number;
  maxScore: number;
  reason: string;
}

// 提取当前评分维度的四个具体小分，保留各项真实满分与说明。
export function buildReportSubScores(evaluation: AgentEvaluation): ReportSubScore[] {
  const subScores = evaluation.details?.sub_scores;
  if (!subScores || typeof subScores !== "object") {
    return [{ name: evaluation.dimension, score: evaluation.score, maxScore: 100, reason: evaluation.summary }];
  }
  return Object.entries(subScores as Record<string, unknown>).slice(0, 4).map(([name, raw]) => {
    const item = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
    const score = typeof raw === "number" ? raw : Number(item.score ?? 0);
    const maxScore = Number(item.max_score ?? 25);
    return {
      name,
      score: Number.isFinite(score) ? score : 0,
      maxScore: Number.isFinite(maxScore) && maxScore > 0 ? maxScore : 25,
      reason: String(item.reason ?? item.evidence ?? evaluation.summary),
    };
  });
}

// 渲染综合得分圆环。
export function ScoreRing({ score, label }: { score: string; label: string }) {
  const numericScore = Number(score);
  const scoreDegree = Number.isFinite(numericScore) ? Math.max(0, Math.min(100, numericScore)) * 3.6 : 280;
  const grade = getReportScoreGrade(numericScore);
  return (
    <div
      className="report-score-ring absolute left-[22px] top-[27px] h-[98px] w-[98px] rounded-full"
      style={{ "--score-degree": `${scoreDegree}deg`, "--score-color": grade.color, "--score-track": grade.softColor } as CSSProperties}
    >
      <div className="absolute left-[10px] top-[10px] z-[2] flex h-[78px] w-[78px] flex-col items-center justify-center rounded-full bg-white">
        <b className="text-[34px] leading-9" style={{ color: grade.darkColor }}>{score}</b>
        <span className="max-w-[64px] truncate text-[9px] text-[#53565e]">{label}</span>
      </div>
      <span
        className="absolute left-1/2 top-[86px] z-[3] flex h-6 w-[52px] -translate-x-1/2 items-center justify-center rounded-full border text-[11px] font-bold"
        style={{ borderColor: grade.color, backgroundColor: grade.softColor, color: grade.darkColor }}
      >
        {grade.name}
      </span>
    </div>
  );
}

export interface ReportScoreGrade {
  name: "不及格" | "及格" | "良好" | "优秀" | "卓越";
  min: number;
  color: string;
  darkColor: string;
  softColor: string;
  panelColor: string;
}

export const reportScoreGrades: ReportScoreGrade[] = [
  { name: "卓越", min: 90, color: "#6c4dff", darkColor: "#4d35c8", softColor: "#efeaff", panelColor: "#4d35c8" },
  { name: "优秀", min: 80, color: "#7f68f2", darkColor: "#5f49c8", softColor: "#f1eeff", panelColor: "#5f49c8" },
  { name: "良好", min: 70, color: "#9483e8", darkColor: "#6f5ac5", softColor: "#f3f0ff", panelColor: "#6f5ac5" },
  { name: "及格", min: 60, color: "#a99bd6", darkColor: "#7c6daf", softColor: "#f5f2ff", panelColor: "#7c6daf" },
  { name: "不及格", min: 0, color: "#b8acd8", darkColor: "#887aa9", softColor: "#f6f3ff", panelColor: "#6f657f" },
];

export function getReportScoreGrade(score: number) {
  const safeScore = Number.isFinite(score) ? score : 0;
  return reportScoreGrades.find((item) => safeScore >= item.min) ?? reportScoreGrades[reportScoreGrades.length - 1];
}

export function getReportScoreGradeForMax(score: number, maxScore: 25 | 100) {
  if (maxScore === 100) return getReportScoreGrade(score);
  const normalizedScore = Number.isFinite(score) ? Math.max(0, Math.min(maxScore, score)) / maxScore * 100 : 0;
  return getReportScoreGrade(normalizedScore);
}

// 渲染反馈要点行，摘要和知识编号保持紧凑。
export function TraceRow({ issue, onClick }: { issue: ReportIssue; onClick?: () => void }) {
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
export function IssueOverlay({ issue, references, onClose }: { issue: ReportIssue; references: KnowledgeReference[]; onClose: () => void }) {
  const [activeReferenceId, setActiveReferenceId] = useState<string | null>(null);
  const [activeImage, setActiveImage] = useState<KnowledgeImage | null>(null);
  const activeReference = activeReferenceId ? findReference(references, activeReferenceId) : null;
  const knowledge = useReportKnowledgeDetail(activeReference);
  const activeReferenceDisplay = activeReference ? getReferenceDisplay(activeReference.reference_id, references) : null;
  const tone = getIssueTone(issue.level);
  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-center justify-center overflow-hidden bg-[#171719]/30" onClick={onClose}>
      {activeImage ? (
        <ZoomableImageStage src={apiUrl(activeImage.url)} alt={activeImage.name ?? knowledge.title} onClose={() => setActiveImage(null)} />
      ) : (
      <section className="figma-shadow relative h-[680px] max-h-[calc(100vh-40px)] w-[760px] max-w-[calc(100vw-40px)] rounded-[22px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        {activeReference ? (
          <div className="flex h-full flex-col">
            <button type="button" className="issue-overlay-nav absolute right-7 top-8 text-[#6c4dff]" onClick={() => setActiveReferenceId(null)}>返回反馈详情</button>
            <p className="text-[13px] font-bold text-[#6c4dff]">知识库卡片</p>
            <h2 className="mt-3 max-w-[570px] text-[24px] font-bold">{knowledge.title}</h2>
            <div className="report-light-scroll mt-6 min-h-0 flex-1 overflow-y-auto pr-4">
              <p className="text-[13px] font-bold text-[#9a9ea7]" title={activeReferenceDisplay?.fullId}>{knowledge.detail?.id || activeReferenceDisplay?.label} · {knowledge.detail?.kind_label || activeReference.source_type || "知识库"}</p>
              {knowledge.loading && <p className="mt-6 text-[13px] text-[#9a9ea7]">正在读取完整知识卡内容…</p>}
              {knowledge.error && <p className="mt-6 rounded-[12px] bg-[#fff4f4] px-4 py-3 text-[12px] leading-6 text-[#b44747]">{knowledge.error} 已暂时显示评图时保存的内容。</p>}
              {!knowledge.loading && <>
                {knowledge.excerpt && knowledge.excerpt.trim() !== knowledge.content.trim() && <p className="mt-4 rounded-[12px] bg-[#fafbfc] px-4 py-3 text-[14px] leading-7 text-[#53565e]">{knowledge.excerpt}</p>}
                <div className="mt-5">
                  <ReportKnowledgeContent content={knowledge.content} images={knowledge.images} onPreview={setActiveImage} />
                </div>
              </>}
            </div>
          </div>
        ) : (
          <>
            <p className="text-[13px] font-bold text-[#6c4dff]">反馈详情</p>
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
                  const display = getReferenceDisplay(referenceId, references);
                  return (
                    <button type="button" className="knowledge-link-row grid min-h-[42px] w-full grid-cols-[100px_1fr_54px] items-center gap-3 rounded-[12px] border border-[#e8ebef] bg-white px-3 py-2 text-left hover:bg-[#f4f6f8]" onClick={() => setActiveReferenceId(referenceId)} key={referenceId}>
                      <b className="knowledge-link-text truncate text-[#6c4dff]" title={display.fullId}>[{display.label}]</b>
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
      )}
    </div>,
    document.body,
  );
}

// 在不改变主页面布局的前提下展示报告详情。
export function ReportOverlay({ title, subtitle, lines, fallback, onClose }: { title: string; subtitle: string; lines: string[]; fallback: string; onClose: () => void }) {
  const visibleLines = lines.length ? lines : [fallback];
  return createPortal(
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-[#171719]/30 p-5" onClick={onClose}>
      <section className="figma-shadow relative h-[470px] w-[572px] max-w-[calc(100vw-40px)] rounded-[22px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        <button type="button" aria-label="关闭" onClick={onClose} className="absolute right-6 top-6 flex h-10 w-10 items-center justify-center rounded-full border border-[#e8ebef] bg-white text-[24px] leading-none text-[#9a9ea7] hover:bg-[#f4f6f8]">×</button>
        <p className="text-[12px] text-[#6c4dff]">{subtitle}</p>
        <h2 className="mt-2 text-[24px] font-bold">{title}</h2>
        <div className="report-light-scroll mt-6 h-[304px] space-y-3 overflow-y-auto pr-4 text-[13px] leading-6 text-[#53565e]">
          {visibleLines.map((line, index) => <p className="rounded-[12px] bg-[#fafbfc] px-4 py-3" key={`${line}-${index}`}>{line}</p>)}
        </div>
      </section>
    </div>,
    document.body,
  );
}

// 渲染报告右侧继续对话区。
export const metricAliases: Record<string, string[]> = {
  功能与流线: ["功能与流线"],
  场地与回应: ["场地与回应", "场地回应"],
  几何形式: ["几何形式", "形式与构图", "形式与沟通"],
  结构与构造: ["结构与构造", "结构与可行性"],
  设计概念: ["设计概念", "概念与立意"],
  图面表达: ["图面表达", "图纸表达"],
};

// 将历史分数和报告维度名称归一，避免旧数据命名不同导致读错分数。
export function normalizeMetricName(name: string) {
  const matched = Object.entries(metricAliases).find(([, aliases]) => aliases.includes(name));
  return matched?.[0] ?? name;
}

// 读取某个历史版本在当前指标下的真实分数。
