// 项目分组状态：把同名项目按时间归并为一个项目，并统一提供侧栏和首页所需版本信息。
import { getProjectOverview } from "../api/projects";
import type { Project, Submission, SubmissionHistory } from "../types/api";

export interface ProjectVersion {
  project: Project;
  submission: Submission;
  history: SubmissionHistory | null;
  versionNumber: number;
  activityAt: string;
}

export interface ProjectGroup {
  key: string;
  name: string;
  projects: Project[];
  latestProject: Project;
  versions: ProjectVersion[];
  lastActivityAt: string;
}

// 判断版本是否仍使用系统默认标题。
export function isDefaultSubmissionTitle(title?: string) {
  return !title?.trim() || title.trim().endsWith("提交");
}

// 项目侧栏、报告标题和历史页统一使用这一套版本名称规则。
export function getProjectVersionLabel(version: ProjectVersion) {
  const title = version.submission.title.trim();
  if (!isDefaultSubmissionTitle(title)) return title;
  return version.history?.overall_score == null ? "草稿" : `V${version.versionNumber}`;
}

export const PINNED_PROJECT_IDS_KEY = "archcritic:pinned-project-ids";
export const PINNED_PROJECTS_CHANGED_EVENT = "archcritic:pinned-projects-changed";

let cachedSignature = "";
let cachedGroups: ProjectGroup[] = [];
let pendingSignature = "";
let pendingRequest: Promise<ProjectGroup[]> | null = null;

// 读取本地置顶项目顺序。
export function readPinnedProjectIds() {
  try {
    const raw = window.localStorage.getItem(PINNED_PROJECT_IDS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((item): item is number => typeof item === "number") : [];
  } catch {
    return [];
  }
}

// 保存本地置顶项目顺序。
export function writePinnedProjectIds(ids: number[]) {
  window.localStorage.setItem(PINNED_PROJECT_IDS_KEY, JSON.stringify(ids));
  window.dispatchEvent(new Event(PINNED_PROJECTS_CHANGED_EVENT));
}

// 判断同名项目组是否已置顶。
export function isProjectGroupPinned(group: ProjectGroup, pinnedIds: number[]) {
  return group.projects.some((project) => pinnedIds.includes(project.id));
}

// 按置顶顺序和原始时间顺序排列项目组。
export function sortPinnedProjectGroups(groups: ProjectGroup[], pinnedIds: number[]) {
  return [...groups].sort((a, b) => {
    const aPinned = isProjectGroupPinned(a, pinnedIds);
    const bPinned = isProjectGroupPinned(b, pinnedIds);
    if (aPinned !== bPinned) return aPinned ? -1 : 1;
    if (!aPinned || !bPinned) return 0;
    const aIndex = Math.min(...a.projects.map((project) => pinnedIds.indexOf(project.id)).filter((index) => index >= 0));
    const bIndex = Math.min(...b.projects.map((project) => pinnedIds.indexOf(project.id)).filter((index) => index >= 0));
    return aIndex - bIndex;
  });
}

// 用项目编号生成缓存标识，便于页面切换时直接复用已有卡片。
function createSignature(projects: Project[]) {
  return projects.map((project) => `${project.id}:${project.name}:${project.created_at ?? ""}`).join(",");
}

// 读取提交的最近活动时间，优先使用后端维护的更新时间。
function getSubmissionActivityAt(submission: Submission) {
  return submission.updated_at ?? submission.created_at ?? "";
}

// 比较两个版本的时间，时间相同时用编号保证顺序稳定。
function compareVersionsByActivity(a: ProjectVersion, b: ProjectVersion) {
  return a.activityAt.localeCompare(b.activityAt) || a.submission.id - b.submission.id;
}

// 从项目创建时间中取一个兜底活动时间。
function getProjectGroupFallbackActivity(projects: Project[]) {
  return projects.reduce((latest, project) => {
    const time = project.created_at ?? "";
    return time > latest ? time : latest;
  }, "");
}

// 未出分的多条草稿只保留最后一次修改；已出分记录继续按时间编号。
function normalizeProjectVersions(versions: ProjectVersion[]) {
  let latestDraft: ProjectVersion | null = null;
  const completedVersions: ProjectVersion[] = [];

  versions.forEach((version) => {
    if (version.history?.overall_score == null) {
      if (!latestDraft || compareVersionsByActivity(latestDraft, version) <= 0) {
        latestDraft = version;
      }
      return;
    }
    completedVersions.push(version);
  });

  const normalized = latestDraft ? [...completedVersions, latestDraft] : completedVersions;
  normalized.sort(compareVersionsByActivity);

  let completedIndex = 1;
  return normalized.map((version) => ({
    ...version,
    versionNumber: version.history?.overall_score == null ? 0 : completedIndex++,
  }));
}

// 计算项目组最后活动时间，用于侧栏日期和排序。
function getLastActivityAt(versions: ProjectVersion[], fallback: string) {
  return versions.reduce((latest, version) => version.activityAt > latest ? version.activityAt : latest, fallback);
}

// 按最后活动时间排序项目组，最新的显示在前面。
function sortGroupsByActivity(groups: ProjectGroup[]) {
  return [...groups].sort((a, b) => {
    return b.lastActivityAt.localeCompare(a.lastActivityAt) || b.latestProject.id - a.latestProject.id;
  });
}

// 按项目名称归并后端记录，并保留后端返回的最近更新时间顺序。
function createBaseGroups(projects: Project[]): ProjectGroup[] {
  const groups = new Map<string, ProjectGroup>();
  projects.forEach((project) => {
    const name = project.name.trim() || "未命名项目";
    const key = name;
    const current = groups.get(key);
    if (current) {
      current.projects.push(project);
      return;
    }
    groups.set(key, {
      key,
      name,
      projects: [project],
      latestProject: project,
      versions: [],
      lastActivityAt: project.created_at ?? "",
    });
  });
  return sortGroupsByActivity([...groups.values()].map((group) => {
    group.projects.sort((a, b) => {
      const timeA = a.created_at ?? "";
      const timeB = b.created_at ?? "";
      return timeB.localeCompare(timeA) || b.id - a.id;
    });
    group.latestProject = group.projects[0];
    group.lastActivityAt = getProjectGroupFallbackActivity(group.projects);
    return group;
  }));
}

// 项目列表变化时尽量沿用已加载版本，避免首页卡片短暂回到未加载状态。
function hydrateBaseGroupsFromCache(groups: ProjectGroup[]) {
  if (!cachedGroups.length) return groups;
  const cachedVersions = new Map<number, ProjectVersion>();
  cachedGroups.forEach((group) => {
    group.versions.forEach((version) => cachedVersions.set(version.submission.id, version));
  });
  return sortGroupsByActivity(groups.map((group) => {
    const projectIds = new Set(group.projects.map((project) => project.id));
    const versions = [...cachedVersions.values()].filter((version) => projectIds.has(version.project.id));
    const normalizedVersions = normalizeProjectVersions(versions);
    return {
      ...group,
      versions: normalizedVersions,
      lastActivityAt: getLastActivityAt(normalizedVersions, group.lastActivityAt),
    };
  }));
}

// 返回可立即显示的分组；已有缓存时页面切换不会短暂变空。
export function getCachedProjectGroups(projects: Project[]) {
  const signature = createSignature(projects);
  return cachedSignature === signature ? cachedGroups : hydrateBaseGroupsFromCache(createBaseGroups(projects));
}

// 加载每个同名项目下的提交，并只给已出分的提交生成 V1、V2 等版本号。
export function loadProjectGroups(projects: Project[]) {
  const signature = createSignature(projects);
  if (!projects.length) {
    cachedSignature = signature;
    cachedGroups = [];
    return Promise.resolve([]);
  }
  if (pendingRequest && pendingSignature === signature) return pendingRequest;

  const groups = createBaseGroups(projects);
  pendingSignature = signature;
  pendingRequest = getProjectOverview().then((items) => {
    const details = new Map(items.map((item) => [item.project.id, item]));
    groups.forEach((group) => {
      const versions = group.projects.flatMap((project) => {
        const detail = details.get(project.id);
        return (detail?.submissions ?? []).map((submission) => ({
          project,
          submission,
          history: detail?.history.find((item) => item.id === submission.id) ?? null,
          versionNumber: 0,
          activityAt: getSubmissionActivityAt(submission),
        }));
      });
      group.versions = normalizeProjectVersions(versions);
      group.lastActivityAt = getLastActivityAt(versions, getProjectGroupFallbackActivity(group.projects));
    });
    cachedSignature = signature;
    cachedGroups = sortGroupsByActivity(groups);
    return cachedGroups;
  }).finally(() => {
    pendingRequest = null;
    pendingSignature = "";
  });
  return pendingRequest;
}

// 读取一个项目组中最新的提交版本。
export function getLatestVersion(group: ProjectGroup) {
  return group.versions[group.versions.length - 1] ?? null;
}
