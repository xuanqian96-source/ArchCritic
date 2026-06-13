// 项目接口：负责创建、读取、更新、继承和历史列表。
import { requestJson } from "./client";
import type { Project, Submission, SubmissionHistory } from "../types/api";

export type ProjectPayload = Omit<Project, "id" | "created_at">;

// 获取全部项目。
export function listProjects(): Promise<Project[]> {
  return requestJson("/api/projects");
}

// 创建项目。
export function createProject(payload: ProjectPayload): Promise<Project> {
  return requestJson("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// 获取项目详情。
export function getProject(projectId: number): Promise<Project> {
  return requestJson(`/api/projects/${projectId}`);
}

// 获取项目下的全部提交版本。
export function listProjectSubmissions(projectId: number): Promise<Submission[]> {
  return requestJson(`/api/projects/${projectId}/submissions`);
}

// 更新项目详情。
export function updateProject(projectId: number, payload: Partial<ProjectPayload>): Promise<Project> {
  return requestJson(`/api/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// 删除项目及其全部版本。
export function deleteProject(projectId: number): Promise<{ deleted: number[]; submissions: number[] }> {
  return requestJson(`/api/projects/${projectId}`, { method: "DELETE" });
}

// 继承已有项目。
export function cloneProject(projectId: number, sourceSubmissionId?: number): Promise<Project> {
  const query = sourceSubmissionId ? `?source_submission_id=${sourceSubmissionId}` : "";
  return requestJson(`/api/projects/${projectId}/clone${query}`, { method: "POST" });
}

// 获取历史版本。
export function getProjectHistory(projectId: number): Promise<SubmissionHistory[]> {
  return requestJson(`/api/projects/${projectId}/history`);
}
