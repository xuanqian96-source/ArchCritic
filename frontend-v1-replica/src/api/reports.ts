// 报告接口：负责报告、知识依据、下载和继续追问。
import { apiUrl, requestJson } from "./client";
import type { ChatMessage, KnowledgeReference, OverallReport } from "../types/api";

// 获取报告。
export function getReport(submissionId: number): Promise<OverallReport> {
  return requestJson(`/api/submissions/${submissionId}/report`);
}

// 获取知识依据。
export function getReferences(submissionId: number): Promise<KnowledgeReference[]> {
  return requestJson(`/api/submissions/${submissionId}/references`);
}

// 下载 Markdown 报告。
export function downloadReport(submissionId: number): void {
  window.location.href = apiUrl(`/api/submissions/${submissionId}/report/export?format=markdown`);
}

// 发送报告追问。
export function sendChat(submissionId: number, content: string): Promise<ChatMessage> {
  return requestJson(`/api/submissions/${submissionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}

// 获取报告追问历史。
export function listChatMessages(submissionId: number): Promise<ChatMessage[]> {
  return requestJson(`/api/submissions/${submissionId}/chat/messages`);
}
