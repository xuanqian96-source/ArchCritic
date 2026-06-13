// 项目分组状态：把同名项目按时间归并为一个项目，并统一提供侧栏和首页所需版本信息。
import { getProjectHistory, listProjectSubmissions } from "../api/projects";
import type { Project, Submission, SubmissionHistory } from "../types/api";

export interface ProjectVersion {
  project: Project;
  submission: Submission;
  history: SubmissionHistory | null;
  versionNumber: number;
}

export interface ProjectGroup {
  key: string;
  name: string;
  projects: Project[];
  latestProject: Project;
  versions: ProjectVersion[];
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
    });
  });
  return [...groups.values()].map((group) => {
    group.projects.sort((a, b) => {
      const timeA = a.created_at ?? "";
      const timeB = b.created_at ?? "";
      return timeB.localeCompare(timeA) || b.id - a.id;
    });
    group.latestProject = group.projects[0];
    return group;
  }).sort((a, b) => {
    const timeA = a.latestProject.created_at ?? "";
    const timeB = b.latestProject.created_at ?? "";
    return timeB.localeCompare(timeA) || b.latestProject.id - a.latestProject.id;
  });
}

// 项目列表变化时尽量沿用已加载版本，避免首页卡片短暂回到未加载状态。
function hydrateBaseGroupsFromCache(groups: ProjectGroup[]) {
  if (!cachedGroups.length) return groups;
  const cachedVersions = new Map<number, ProjectVersion>();
  cachedGroups.forEach((group) => {
    group.versions.forEach((version) => cachedVersions.set(version.submission.id, version));
  });
  return groups.map((group) => {
    const projectIds = new Set(group.projects.map((project) => project.id));
    const versions = [...cachedVersions.values()].filter((version) => projectIds.has(version.project.id));
    versions.sort((a, b) => {
      const timeA = a.submission.created_at ?? "";
      const timeB = b.submission.created_at ?? "";
      return timeA.localeCompare(timeB) || a.submission.id - b.submission.id;
    });
    let completedIndex = 1;
    versions.forEach((version) => {
      version.versionNumber = version.history?.overall_score == null ? 0 : completedIndex++;
    });
    return { ...group, versions };
  });
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
  pendingRequest = Promise.all(projects.map(async (project) => {
    const [submissions, history] = await Promise.all([
      listProjectSubmissions(project.id).catch(() => []),
      getProjectHistory(project.id).catch(() => []),
    ]);
    return { project, submissions, history };
  })).then((items) => {
    const details = new Map(items.map((item) => [item.project.id, item]));
    groups.forEach((group) => {
      const versions = group.projects.flatMap((project) => {
        const detail = details.get(project.id);
        return (detail?.submissions ?? []).map((submission) => ({
          project,
          submission,
          history: detail?.history.find((item) => item.id === submission.id) ?? null,
          versionNumber: 0,
        }));
      });
      versions.sort((a, b) => {
        const timeA = a.submission.created_at ?? "";
        const timeB = b.submission.created_at ?? "";
        return timeA.localeCompare(timeB) || a.submission.id - b.submission.id;
      });
      let completedIndex = 1;
      versions.forEach((version) => {
        version.versionNumber = version.history?.overall_score == null ? 0 : completedIndex++;
      });
      group.versions = versions;
    });
    cachedSignature = signature;
    cachedGroups = groups;
    return groups;
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
