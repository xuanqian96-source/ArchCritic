// 分数等级工具：为首页、报告页和历史页提供统一的分数段颜色。
export type ScoreLevelKey = "bronze" | "silver" | "gold" | "platinum" | "diamond";

export interface ScoreLevelStyle {
  key: ScoreLevelKey;
  name: string;
  min: number;
  color: string;
  darkColor: string;
  softColor: string;
  tooltipColor: string;
}

export const scoreLevelStyles: ScoreLevelStyle[] = [
  { key: "diamond", name: "钻石", min: 90, color: "#6c4dff", darkColor: "#4d35c8", softColor: "#efeaff", tooltipColor: "#4d35c8" },
  { key: "platinum", name: "铂金", min: 80, color: "#7f68f2", darkColor: "#5f49c8", softColor: "#f1eeff", tooltipColor: "#5f49c8" },
  { key: "gold", name: "黄金", min: 70, color: "#9483e8", darkColor: "#6f5ac5", softColor: "#f3f0ff", tooltipColor: "#6f5ac5" },
  { key: "silver", name: "白银", min: 60, color: "#a99bd6", darkColor: "#7c6daf", softColor: "#f5f2ff", tooltipColor: "#7c6daf" },
  { key: "bronze", name: "青铜", min: 0, color: "#b8acd8", darkColor: "#887aa9", softColor: "#f6f3ff", tooltipColor: "#887aa9" },
];

// 根据分数返回当前段位，异常分数按最低段处理。
export function getScoreLevel(score: number) {
  const safeScore = Number.isFinite(score) ? score : 0;
  return scoreLevelStyles.find((item) => safeScore >= item.min) ?? scoreLevelStyles[scoreLevelStyles.length - 1];
}
