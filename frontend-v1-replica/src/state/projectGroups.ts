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

let cachedSignature = "";
let cachedGroups: ProjectGroup[] = [];
let pendingSignature = "";
let pendingRequest: Promise<ProjectGroup[]> | null = null;

// 用项目编号生成缓存标识，便于页面切换时直接复用已有卡片。
function createSignature(projects: Project[]) {
  return projects.map((project) => project.id).join(",");
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

// 返回可立即显示的分组；已有缓存时页面切换不会短暂变空。
export function getCachedProjectGroups(projects: Project[]) {
  const signature = createSignature(projects);
  return cachedSignature === signature ? cachedGroups : createBaseGroups(projects);
}

// 加载每个同名项目下的提交，并按提交时间生成 V1、V2 等版本。
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
      versions.forEach((version, index) => {
        version.versionNumber = index + 1;
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
