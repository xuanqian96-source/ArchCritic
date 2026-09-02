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

// 下载后端根据当前真实评分生成的 PDF 报告。
export function downloadReport(submissionId: number): void {
  window.location.href = apiUrl(`/api/submissions/${submissionId}/report/export?format=pdf`);
}

// 发送报告追问。
export function sendChat(submissionId: number, content: string, tool: ChatMessage["tool"] = "none", signal?: AbortSignal): Promise<ChatMessage> {
  return requestJson(`/api/submissions/${submissionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, tool }),
    signal,
    timeoutMs: 300_000,
  });
}

// 读取报告助手事件流，持续显示正文并在结束时返回已保存的完整消息与报告更新。
export async function streamChat(
  submissionId: number,
  content: string,
  tool: ChatMessage["tool"] = "none",
  onDelta: (text: string) => void,
  signal?: AbortSignal,
): Promise<ChatMessage> {
  const response = await fetch(apiUrl(`/api/submissions/${submissionId}/chat/stream`), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, tool }),
    signal,
  });
  if (!response.ok || !response.body) {
    const error = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(error.detail ?? "AI 助手暂时无法回答，请稍后重试。");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalMessage: ChatMessage | null = null;
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = block.match(/^event:\s*(.+)$/m)?.[1];
      const rawData = block.match(/^data:\s*(.+)$/m)?.[1];
      if (!event || !rawData) continue;
      const data = JSON.parse(rawData) as unknown;
      if (event === "delta" && typeof data === "string") onDelta(data);
      if (event === "error") throw new Error(typeof data === "string" ? data : "AI 助手调用失败。");
      if (event === "final") finalMessage = data as ChatMessage;
    }
    if (done) break;
  }
  if (!finalMessage) throw new Error("AI 返回内容不完整，请重试。");
  return finalMessage;
}

// 获取报告追问历史。
export function listChatMessages(submissionId: number): Promise<ChatMessage[]> {
  return requestJson(`/api/submissions/${submissionId}/chat/messages`);
}
