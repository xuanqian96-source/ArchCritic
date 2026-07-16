// 历史版本页：按真实报告维度绘制版本趋势并支持回看。
import { useEffect, useRef, useState } from "react";
import type { PageProps } from "../App";
import { Button, Card, PageTitle, Sidebar } from "../components";
import { getScoreLevel } from "../scoreLevels";
import { useWorkspace } from "../state/workspace";
import type { SubmissionHistory } from "../types/api";
import { getCachedGroupHistory, getHistoryVersionLabel, loadProjectGroupHistory } from "./reportHistoryData";
import { metricAliases, schemeDimensionSpecs } from "./reportShared";

function getHistoryMetricScore(item: SubmissionHistory, metric: string) {
  if (metric === "综合评审得分") return item.overall_score ?? null;
  const aliases = metricAliases[metric] ?? [metric];
  const matchedKey = aliases.find((name) => typeof item.dimension_scores?.[name] === "number");
  return matchedKey ? item.dimension_scores?.[matchedKey] ?? null : null;
}
const historyChartConfig = {
  top: 34,
  bottom: 362,
  pointGap: 126,
  edgePadding: 42,
  plotWidth: 1086,
  height: 420,
  tooltipGap: 44,
  tooltipWidth: 360,
  tooltipHeight: 154,
};

// 历史折线按固定版本间距计算宽度，避免版本多时点位互相挤压。
function getHistoryChartWidth(versionCount: number) {
  const lastPointX = historyChartConfig.edgePadding + Math.max(0, versionCount - 1) * historyChartConfig.pointGap;
  return Math.max(historyChartConfig.plotWidth, lastPointX + historyChartConfig.edgePadding);
}

// 将 0-100 分映射到纵轴，顶部固定为 100 分。
function getHistoryScoreY(score: number) {
  const clamped = Math.max(0, Math.min(100, score));
  const range = historyChartConfig.bottom - historyChartConfig.top;
  return historyChartConfig.top + (100 - clamped) * range / 100;
}

// 整理报告短句，悬浮卡片只保留可快速扫读的信息。
function formatHistorySnippet(text?: string) {
  const clean = (text ?? "")
    .replace(/\[(K\d+)\]/gi, "")
    .replace(/\*\*/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return clean.length > 54 ? `${clean.slice(0, 54)}...` : clean;
}

function formatHistoryItems(items?: string[], fallback = "暂无明确记录。") {
  const snippets = (items ?? []).map(formatHistorySnippet).filter(Boolean).slice(0, 2);
  return snippets.length ? snippets.join("；") : fallback;
}

function formatScoreDelta(delta: number) {
  return `${delta >= 0 ? "+" : ""}${Math.round(delta)}`;
}

// 根据相邻版本分项变化，提取提升或下降最明显的一到两项。
function buildHistoryChangeText(current: SubmissionHistory, previous: SubmissionHistory | null) {
  if (!previous || current.overall_score == null || previous.overall_score == null) {
    return { label: "主要变化", text: "首版评分记录，可作为后续版本对比基准。" };
  }
  const overallDelta = current.overall_score - previous.overall_score;
  const improved = overallDelta >= 0;
  const changes = schemeDimensionSpecs
    .map((spec) => {
      const currentScore = getHistoryMetricScore(current, spec.label);
      const previousScore = getHistoryMetricScore(previous, spec.label);
      return currentScore == null || previousScore == null ? null : {
        label: spec.label,
        delta: currentScore - previousScore,
      };
    })
    .filter((item): item is { label: string; delta: number } => item != null)
    .filter((item) => improved ? item.delta > 0 : item.delta < 0)
    .sort((a, b) => improved ? b.delta - a.delta : a.delta - b.delta)
    .slice(0, 2);
  const text = changes.length
    ? changes.map((item) => `${item.label} ${formatScoreDelta(item.delta)}`).join("、")
    : `总分 ${formatScoreDelta(overallDelta)}`;
  return { label: improved ? "主要提升" : "主要下降", text };
}

// 组合圆点悬浮卡片内容。
function buildHistoryTooltip(item: SubmissionHistory, index: number, versions: SubmissionHistory[]) {
  const change = buildHistoryChangeText(item, index > 0 ? versions[index - 1] : null);
  return {
    change,
    mustFix: formatHistoryItems(item.must_fix, "本版暂无必须修改项。"),
    strengths: formatHistoryItems(item.strengths, item.summary || "本版暂无方案优势记录。"),
  };
}

function getHistoryTooltipLeft(pointX: number, chartWidth: number) {
  const rightSideLeft = pointX + historyChartConfig.tooltipGap;
  if (rightSideLeft + historyChartConfig.tooltipWidth <= chartWidth) return rightSideLeft;
  return Math.max(0, pointX - historyChartConfig.tooltipGap - historyChartConfig.tooltipWidth);
}

// 渲染历史版本对比页。
export function HistoryPage({ go }: PageProps) {
  const { history, openSubmission, prefetchSubmission, project, projects } = useWorkspace();
  const [metric, setMetric] = useState("综合评审得分");
  const [groupHistory, setGroupHistory] = useState<SubmissionHistory[]>(() => getCachedGroupHistory(project, history));
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const historyScrollRef = useRef<HTMLDivElement | null>(null);
  const prefetchedSubmissionIds = useRef(new Set<number>());
  useEffect(() => {
    let mounted = true;
    setGroupHistory(getCachedGroupHistory(project, history));
    void loadProjectGroupHistory(project, projects, history).then((items) => {
      if (!mounted) return;
      setGroupHistory(items);
    });
    return () => { mounted = false; };
  }, [history, project, projects]);
  const versions = groupHistory;
  const availableMetrics = [
    "综合评审得分",
    ...schemeDimensionSpecs
      .map((spec) => spec.label)
      .filter((label) => versions.some((item) => getHistoryMetricScore(item, label) != null)),
  ];
  useEffect(() => {
    if (!availableMetrics.includes(metric)) setMetric("综合评审得分");
  }, [availableMetrics.join("|"), metric]);
  const versionNumbersById = new Map<number, number>();
  versions.forEach((item) => {
    if (item.overall_score == null) return;
    versionNumbersById.set(item.id, versionNumbersById.size + 1);
  });
  const scoredVersions = versions.flatMap((item) => {
    const score = getHistoryMetricScore(item, metric);
    return score == null ? [] : [{ item, score }];
  });
  const chartWidth = getHistoryChartWidth(scoredVersions.length);
  const validPoints = scoredVersions.map(({ item, score }, index) => {
    const x = historyChartConfig.edgePadding + index * historyChartConfig.pointGap;
    const y = getHistoryScoreY(score);
    return { x, y, score, level: getScoreLevel(score), index, versionNumber: versionNumbersById.get(item.id) ?? index + 1, item };
  });
  const previousScore = validPoints.length > 1 ? validPoints[validPoints.length - 2].score : validPoints[0]?.score ?? 0;
  const latestScore = validPoints[validPoints.length - 1]?.score ?? 0;
  const latestPoint = validPoints[validPoints.length - 1] ?? null;
  const previousPoint = validPoints.length > 1 ? validPoints[validPoints.length - 2] : null;
  const scoreDelta = latestScore - previousScore;
  const scoreRangeLabel = latestPoint
    ? previousPoint
      ? `${getHistoryVersionLabel(previousPoint.item, previousPoint.versionNumber)} → ${getHistoryVersionLabel(latestPoint.item, latestPoint.versionNumber)}`
      : getHistoryVersionLabel(latestPoint.item, latestPoint.versionNumber)
    : "暂无版本";
  const shouldShowScoreDelta = validPoints.length > 1;
  const chartScrollable = chartWidth > historyChartConfig.plotWidth;
  const hoveredPoint = hoveredIndex == null ? null : validPoints.find((point) => point.index === hoveredIndex) ?? null;
  const hoveredTooltip = hoveredPoint ? buildHistoryTooltip(hoveredPoint.item, hoveredPoint.index, scoredVersions.map((item) => item.item)) : null;
  const scoreTicks = [100, 80, 60, 40, 20, 0];
  const prefetchIdsKey = validPoints.map((point) => point.item.id).join(",");
  useEffect(() => {
    const scrollNode = historyScrollRef.current;
    if (!scrollNode) return;
    window.requestAnimationFrame(() => {
      scrollNode.scrollLeft = Math.max(0, scrollNode.scrollWidth - scrollNode.clientWidth);
    });
  }, [project?.id, scoredVersions.length]);
  useEffect(() => {
    const timers = validPoints.map((point, index) => window.setTimeout(() => {
      if (!point.item.id || prefetchedSubmissionIds.current.has(point.item.id)) return;
      prefetchedSubmissionIds.current.add(point.item.id);
      prefetchSubmission(point.item.id);
    }, index * 80));
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [prefetchIdsKey, prefetchSubmission]);
  const prefetchHistoryPoint = (submissionId: number) => {
    if (!submissionId || prefetchedSubmissionIds.current.has(submissionId)) return;
    prefetchedSubmissionIds.current.add(submissionId);
    prefetchSubmission(submissionId);
  };
  return (
    <div className="relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} creating />
      <PageTitle title="历史版本对比" subtitle={`对比${project?.name ? `“${project.name}”` : "当前项目"}的版本评分与修改建议，追踪设计演变。`} />
      <Button kind="purple" className="absolute right-[23px] top-[100px] w-[132px] rounded-[12px]" onClick={() => go("report")}>返回</Button>
      <Card className="absolute left-[307px] top-[150px] h-[650px] w-[1206px] p-6">
        <h2 className="text-[20px] font-bold">版本评分趋势</h2>
        <p className="mt-1 text-[13px] text-[#6b7280]">按版本迭代顺序从左至右查看评分变化；切换上方指标即可查看不同维度折线。</p>
        <div className="mt-5 flex items-center gap-3">
          {availableMetrics.map(text => <Button kind={metric === text ? "dark" : "white"} className="h-9" key={text} onClick={() => setMetric(text)}>{text}</Button>)}
          {shouldShowScoreDelta && (
            <div className="ml-auto flex h-9 max-w-[420px] items-center overflow-hidden text-[14px] font-bold leading-5">
              <span className={`min-w-0 truncate ${scoreDelta >= 0 ? "text-[#159447]" : "text-[#b44747]"}`}>{scoreRangeLabel}　{formatScoreDelta(scoreDelta)}</span>
            </div>
          )}
        </div>
        <div className="relative mt-2 h-[458px]">
          <div className="pointer-events-none absolute bottom-[96px] left-0 top-0 z-10 w-[72px] bg-white">
            <svg viewBox="0 0 72 420" className="h-[420px] w-[72px]">
              {scoreTicks.map((score) => {
                const y = getHistoryScoreY(score);
                return <text key={score} x="10" y={y + 4} fill="#53565e" fontFamily="Inter, Noto Sans SC, Microsoft YaHei, sans-serif" fontSize="13" fontWeight="700" textAnchor="start">{score}</text>;
              })}
            </svg>
          </div>
          <div ref={historyScrollRef} className={`absolute bottom-0 left-[72px] right-0 top-0 overflow-y-hidden ${chartScrollable ? "history-chart-scroll overflow-x-auto pb-5" : "overflow-x-hidden"}`} onMouseLeave={() => setHoveredIndex(null)}>
            <div className="relative h-[420px]" style={{ width: `${chartWidth}px` }}>
              <svg viewBox={`0 0 ${chartWidth} ${historyChartConfig.height}`} className="absolute inset-0 h-[420px]" style={{ width: `${chartWidth}px` }}>
                {scoreTicks.map((score) => {
                  const y = getHistoryScoreY(score);
                  return (
                    <g key={score}>
                      <line x1="0" y1={y} x2={chartWidth} y2={y} stroke="#d9dde3" strokeWidth="1" />
                    </g>
                  );
                })}
                <line x1="0" y1={historyChartConfig.bottom} x2={chartWidth} y2={historyChartConfig.bottom} stroke="#8d94a0" strokeWidth="1" />
                {validPoints.length > 1 && <polyline points={validPoints.map((point) => `${point.x},${point.y}`).join(" ")} fill="none" stroke="#9aa1ad" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />}
                {validPoints.map((point) => (
                  <g
                    className="cursor-pointer"
                    key={`${point.item.id}-${point.index}`}
                    onClick={() => point.item.id && void openSubmission(point.item.id).then(() => go("report"))}
                    onMouseEnter={() => {
                      setHoveredIndex(point.index);
                      prefetchHistoryPoint(point.item.id);
                    }}
                    onMouseLeave={() => setHoveredIndex(null)}
                  >
                    <circle cx={point.x} cy={point.y} r="18" fill="transparent" />
                    <circle
                      className={hoveredIndex === point.index ? "history-point-active" : ""}
                      cx={point.x}
                      cy={point.y}
                      r="7"
                      fill={point.level.color}
                      stroke="white"
                      strokeWidth="2"
                    />
                    <text x={point.x - 7} y={point.y - 22} fill={point.level.darkColor} fontSize="13" fontWeight="700" textAnchor="start">{Math.round(point.score)}</text>
                  </g>
                ))}
              </svg>
              {validPoints.map((point) => (
                <button
                  type="button"
                  className="font-inter absolute top-[376px] w-[92px] text-center text-[13px] font-bold leading-[18px] text-[#53565e]"
                  style={{ left: `${point.x - 46}px` }}
                  key={`${point.item.id}-${point.index}`}
                  onClick={() => point.item.id && void openSubmission(point.item.id).then(() => go("report"))}
                >
                  {getHistoryVersionLabel(point.item, point.versionNumber)}
                </button>
              ))}
              {hoveredPoint && hoveredTooltip && (
                <div
                  className="pointer-events-none absolute rounded-[14px] px-5 py-4 text-left text-[12px] leading-[19px] text-white shadow-[0_18px_46px_-24px_rgba(45,45,80,0.55)]"
                  style={{
                    left: `${getHistoryTooltipLeft(hoveredPoint.x, chartWidth)}px`,
                    top: `${Math.max(historyChartConfig.top, Math.min(historyChartConfig.bottom - historyChartConfig.tooltipHeight, hoveredPoint.y - historyChartConfig.tooltipHeight / 2))}px`,
                    width: `${historyChartConfig.tooltipWidth}px`,
                    minHeight: `${historyChartConfig.tooltipHeight}px`,
                    backgroundColor: hoveredPoint.level.tooltipColor,
                  }}
                >
                  <div className="flex items-center justify-between gap-5 text-[20px] font-bold leading-7">
                    <span className="truncate">{getHistoryVersionLabel(hoveredPoint.item, hoveredPoint.versionNumber)}</span>
                    <span className="shrink-0">{metric === "综合评审得分" ? "总分" : "得分"} {Math.round(hoveredPoint.score)}</span>
                  </div>
                  <p className="mt-3 line-clamp-2"><b>{hoveredTooltip.change.label}：</b>{hoveredTooltip.change.text}</p>
                  <p className="mt-1 line-clamp-2"><b>建议修改：</b>{hoveredTooltip.mustFix}</p>
                  <p className="mt-1 line-clamp-2"><b>方案优势：</b>{hoveredTooltip.strengths}</p>
                </div>
              )}
            </div>
          </div>
          {!versions.length && <p className="absolute left-0 right-0 top-[170px] text-center text-[14px] text-[#9a9ea7]">暂无可对比的历史版本。</p>}
        </div>
      </Card>
    </div>
  );
}
