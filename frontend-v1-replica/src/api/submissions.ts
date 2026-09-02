// 提交接口：负责草稿、附件和流式评图。
import { apiUrl, requestJson, uploadForm } from "./client";
import type { Attachment, EvaluationStreamEvent, Submission, SubmissionWorkspace } from "../types/api";

export type SubmissionPayload = Omit<Submission, "id" | "created_at" | "updated_at" | "image_urls"> & { image_urls?: string[] };

// 创建草稿提交。
export function createSubmission(payload: SubmissionPayload): Promise<Submission> {
  return requestJson("/api/submissions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// 获取提交详情。
export function getSubmission(submissionId: number): Promise<Submission> {
  return requestJson(`/api/submissions/${submissionId}`);
}

// 一次获取进入工作台所需的完整快照。
export function getSubmissionWorkspace(submissionId: number): Promise<SubmissionWorkspace> {
  return requestJson(`/api/submissions/${submissionId}/workspace`);
}

// 更新草稿提交。
export function updateSubmission(submissionId: number, payload: Partial<SubmissionPayload>): Promise<Submission> {
  return requestJson(`/api/submissions/${submissionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// 删除一个提交版本。
export function deleteSubmission(submissionId: number): Promise<{ deleted: number[] }> {
  return requestJson(`/api/submissions/${submissionId}`, { method: "DELETE" });
}

// 上传任务书等补充附件。
export function uploadAttachment(submissionId: number, file: File): Promise<Attachment> {
  const formData = new FormData();
  formData.append("file", file);
  return uploadForm(`/api/submissions/${submissionId}/attachments`, formData);
}

// 获取补充附件列表。
export function listAttachments(submissionId: number): Promise<Attachment[]> {
  return requestJson(`/api/submissions/${submissionId}/attachments`);
}

// 删除一个补充附件。
export function deleteAttachment(attachmentId: number): Promise<{ deleted: number[] }> {
  return requestJson(`/api/submissions/attachments/${attachmentId}`, { method: "DELETE" });
}

// 解析 SSE 文本块。
function parseEvent(block: string): EvaluationStreamEvent | null {
  const lines = block.split("\n");
  const event = lines.find((line) => line.startsWith("event:"))?.replace("event:", "").trim();
  const data = lines.filter((line) => line.startsWith("data:")).map((line) => line.replace("data:", "").trim()).join("\n");
  if (!event || !data) return null;
  return { event: event as EvaluationStreamEvent["event"], payload: JSON.parse(data) as Record<string, unknown> };
}

// 启动流式评图，并逐条通知页面更新。
export async function evaluateStream(
  submissionId: number,
  provider: string,
  model: string,
  onEvent: (event: EvaluationStreamEvent) => void,
): Promise<void> {
  const query = new URLSearchParams({ provider, model });
  const response = await fetch(apiUrl(`/api/submissions/${submissionId}/evaluate-stream?${query.toString()}`), {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok || !response.body) throw new Error("流式评图接口请求失败。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    blocks.forEach((block) => {
      const event = parseEvent(block);
      if (event) onEvent(event);
    });
  }
  const lastEvent = parseEvent(buffer.trim());
  if (lastEvent) onEvent(lastEvent);
}

// 请求暂停当前评图任务。
export function cancelEvaluation(submissionId: number): Promise<Submission> {
  return requestJson(`/api/submissions/${submissionId}/cancel-evaluation`, { method: "POST" });
}
