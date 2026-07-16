// 报告历史数据：归并同名项目的真实版本，并统一版本名称与缓存。
import { getProjectHistory } from "../api/projects";
import { getProjectVersionLabel, type ProjectGroup } from "../state/projectGroups";
import type { Project, Submission, SubmissionHistory } from "../types/api";

export function getHistoryVersionLabel(item: SubmissionHistory, versionNumber: number) {
  return !item.title?.trim() || item.title.trim().endsWith("提交") ? `V${versionNumber}` : item.title.trim();
}

// 报告页标题复用左侧栏同一套版本编号，避免同一提交在两处显示不同 V 号。
export function getCurrentReportVersionLabel(
  submission: Submission | null,
  history: SubmissionHistory[],
  projectGroups: ProjectGroup[],
) {
  if (!submission) return "V1";
  const matchedVersion = projectGroups.flatMap((group) => group.versions).find((version) => version.submission.id === submission.id);
  if (matchedVersion) {
    return getProjectVersionLabel(matchedVersion);
  }
  if (submission.title?.trim() && !submission.title.trim().endsWith("提交")) return submission.title.trim();
  const sorted = history.filter((item) => item.overall_score != null).sort((a, b) => {
    const aTime = new Date(a.created_at ?? "").getTime() || 0;
    const bTime = new Date(b.created_at ?? "").getTime() || 0;
    return aTime - bTime || a.id - b.id;
  });
  const index = sorted.findIndex((item) => item.id === submission.id);
  return `V${index >= 0 ? index + 1 : 1}`;
}

export interface HistoryGroupCacheEntry {
  items: SubmissionHistory[];
  pending?: Promise<SubmissionHistory[]>;
}

export const historyGroupCache = new Map<string, HistoryGroupCacheEntry>();

export function getHistoryGroupKey(project: Project | null) {
  return project?.name.trim() ?? "";
}

export function sortHistoryByCreatedAt(items: SubmissionHistory[]) {
  return [...items].sort((a, b) => {
    const aTime = new Date(a.created_at ?? "").getTime() || 0;
    const bTime = new Date(b.created_at ?? "").getTime() || 0;
    return aTime - bTime || a.id - b.id;
  });
}

export function getCachedGroupHistory(project: Project | null, fallback: SubmissionHistory[]) {
  const key = getHistoryGroupKey(project);
  const cached = key ? historyGroupCache.get(key)?.items ?? [] : [];
  return cached.length ? cached : sortHistoryByCreatedAt(fallback);
}

// 同名项目的历史记录较多时，提前加载并缓存，避免进入历史页后才等待多次接口返回。
export function loadProjectGroupHistory(project: Project | null, projects: Project[], fallback: SubmissionHistory[]) {
  const key = getHistoryGroupKey(project);
  if (!project || !key) return Promise.resolve(sortHistoryByCreatedAt(fallback));
  const relatedProjects = projects.filter((item) => item.name.trim() === key);
  if (relatedProjects.length <= 1) {
    const localHistory = sortHistoryByCreatedAt(fallback);
    historyGroupCache.set(key, { items: localHistory });
    return Promise.resolve(localHistory);
  }
  const cached = historyGroupCache.get(key);
  if (cached?.pending) return cached.pending;
  const pending = Promise.all(relatedProjects.map((item) => getProjectHistory(item.id).catch(() => [])))
    .then((items) => {
      const merged = sortHistoryByCreatedAt(items.flat());
      const result = merged.length ? merged : sortHistoryByCreatedAt(fallback);
      historyGroupCache.set(key, { items: result });
      return result;
    })
    .catch(() => {
      const localHistory = sortHistoryByCreatedAt(fallback);
      historyGroupCache.set(key, { items: localHistory });
      return localHistory;
    });
  historyGroupCache.set(key, { items: cached?.items ?? sortHistoryByCreatedAt(fallback), pending });
  return pending;
}
