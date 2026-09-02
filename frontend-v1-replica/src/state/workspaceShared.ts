// 工作区共享类型与纯逻辑：草稿默认值、评图事件转换和缓存数据结构。
import { createContext } from "react";
import type { Attachment, ChatMessage, DrawingFile, EvaluationStreamEvent, OverallReport, Project, Submission, SubmissionHistory } from "../types/api";

export const DEFAULT_AGENTS = ["function_agent", "site_agent", "form_agent", "structure_agent", "review_agent"];
export const DEFAULT_MODEL = { provider: "dashscope", model: "qwen3.8-max", label: "qwen3.8-max" };
export const ACCEPTED_DRAWING_TYPES = ["application/pdf"];

export interface DraftValues {
  name: string;
  buildingType: string;
  ownerName: string;
  grade: string;
  siteLocation: string;
  courseName: string;
  description: string;
  designStage: string;
  enabledAgents: string[];
  modelProvider: string;
  modelName: string;
  modelLabel: string;
}

export interface EvaluationStatus {
  running: boolean;
  paused: boolean;
  progress: number;
  completedAgents: string[];
  activeAgent: string;
  completedStages: string[];
  activeStageId: string;
  errorStageId: string;
  messages: string[];
  error: string;
  startedAt: number | null;
  pausedAt: number | null;
  elapsedBeforePause: number;
}

export interface WorkspaceState {
  projects: Project[];
  project: Project | null;
  submission: Submission | null;
  drawings: DrawingFile[];
  attachments: Attachment[];
  report: OverallReport | null;
  history: SubmissionHistory[];
  chatMessages: ChatMessage[];
  draft: DraftValues;
  draftDirty: boolean;
  selectedDrawingId: number | null;
  evaluation: EvaluationStatus;
  notice: string;
  setNotice: (message: string) => void;
  setDraftField: <K extends keyof DraftValues>(field: K, value: DraftValues[K]) => void;
  resetDraft: () => void;
  toggleAgent: (agentType: string) => void;
  saveDraft: () => Promise<Submission>;
  uploadFiles: (files: FileList | File[]) => Promise<void>;
  replaceSelectedDrawing: (file: File) => Promise<void>;
  uploadTaskbook: (file: File) => Promise<void>;
  deleteTaskbook: (attachmentId: number) => Promise<void>;
  selectDrawing: (fileId: number) => void;
  updateSelectedDrawing: (payload: Partial<Pick<DrawingFile, "drawing_type" | "description">>) => Promise<void>;
  deleteSelectedDrawing: () => Promise<void>;
  deleteAllDrawings: () => Promise<void>;
  deleteDrawingIds: (fileIds: number[]) => Promise<void>;
  startEvaluation: () => Promise<void>;
  pauseEvaluation: () => Promise<void>;
  downloadCurrentReport: () => void;
  sendQuestion: (content: string, tool?: ChatMessage["tool"], signal?: AbortSignal, onDelta?: (text: string) => void) => Promise<void>;
  refreshChatMessages: () => Promise<ChatMessage[]>;
  inheritProject: (projectId: number, sourceSubmissionId?: number) => Promise<void>;
  refreshProjects: () => Promise<void>;
  syncProjectName: (projectIds: number[], name: string) => void;
  syncSubmissionTitle: (submissionId: number, title: string) => void;
  openProject: (projectId: number, preloadProject?: Project) => Promise<void>;
  openSubmission: (submissionId: number, preload?: SubmissionPreload) => Promise<void>;
  prefetchSubmission: (submissionId: number, preload?: SubmissionPreload) => void;
}

export const DEFAULT_DRAFT: DraftValues = {
  name: "",
  buildingType: "",
  ownerName: "前端工程师",
  grade: "",
  siteLocation: "",
  courseName: "",
  description: "",
  designStage: "方案阶段",
  enabledAgents: DEFAULT_AGENTS,
  modelProvider: DEFAULT_MODEL.provider,
  modelName: DEFAULT_MODEL.model,
  modelLabel: DEFAULT_MODEL.label,
};

export const EMPTY_EVALUATION: EvaluationStatus = {
  running: false,
  paused: false,
  progress: 0,
  completedAgents: [],
  activeAgent: "",
  completedStages: [],
  activeStageId: "",
  errorStageId: "",
  messages: [],
  error: "",
  startedAt: null,
  pausedAt: null,
  elapsedBeforePause: 0,
};

// 模拟逐字输出，让报告追问在界面中呈现流式阅读效果。
export function waitForChatFrame(delay = 12) {
  return new Promise((resolve) => window.setTimeout(resolve, delay));
}

// 判断文件是否可以作为图纸上传。
export function isAcceptedDrawingFile(file: File) {
  return file.type.startsWith("image/") || ACCEPTED_DRAWING_TYPES.includes(file.type);
}

export const WorkspaceContext = createContext<WorkspaceState | null>(null);
export const LAST_SUBMISSION_KEY = "archcritic:last-submission-id";
export const DUPLICATE_PROJECT_NAME_MESSAGE = "这个项目名称已经被使用了。为了避免报告归到已有项目下，请换一个项目名称。";

// 项目名用于归档分组，保存前统一压缩空白并忽略大小写。
export function normalizeProjectNameForCompare(name: string) {
  return name.trim().replace(/\s+/g, " ").toLowerCase();
}

export function getLastSubmissionKey(username?: string) {
  return username ? `${LAST_SUBMISSION_KEY}:${username}` : LAST_SUBMISSION_KEY;
}

export interface SubmissionPreload {
  project?: Project;
  submission?: Submission;
}

export interface SubmissionSnapshot {
  project: Project;
  submission: Submission;
  drawings: DrawingFile[];
  attachments: Attachment[];
  history: SubmissionHistory[];
  report: OverallReport | null;
  chatMessages: ChatMessage[];
}

// 把流式事件转换为等待页需要的状态。
export function applyEvaluationEvent(
  current: EvaluationStatus,
  event: EvaluationStreamEvent,
): EvaluationStatus {
  const payload = event.payload;
  if (event.event === "status") {
    const message = String(payload.message ?? "");
    const paused = message.includes("评图已暂停");
    return {
      ...current,
      running: paused ? false : current.running,
      paused: paused ? true : current.paused,
      activeAgent: paused ? "" : current.activeAgent,
      activeStageId: paused ? "" : current.activeStageId,
      messages: [...current.messages, message],
    };
  }
  if (event.event === "stage") {
    const stageId = String(payload.stage_id ?? "");
    const status = String(payload.status ?? "");
    const completedStages = status === "done" && stageId && !current.completedStages.includes(stageId)
      ? [...current.completedStages, stageId]
      : current.completedStages;
    return {
      ...current,
      activeStageId: status === "start" ? stageId : current.activeStageId === stageId ? "" : current.activeStageId,
      completedStages,
      messages: [...current.messages, String(payload.message ?? "")],
    };
  }
  if (event.event === "agent") {
    const agentType = String(payload.agent_type ?? "");
    const completedAgents = payload.status === "done" && !current.completedAgents.includes(agentType)
      ? [...current.completedAgents, agentType]
      : current.completedAgents;
    return {
      ...current,
      activeAgent: payload.status === "start" ? agentType : "",
      completedAgents,
      progress: Math.min(95, 10 + completedAgents.length * 18),
      messages: [...current.messages, String(payload.message ?? "")],
    };
  }
  if (event.event === "error") {
    return {
      ...current,
      running: false,
      paused: false,
      errorStageId: current.activeAgent || current.activeStageId || "report",
      activeAgent: "",
      activeStageId: "",
      error: String(payload.message ?? "评图失败。"),
    };
  }
  return current;
}

// 兼容旧草稿中保存过的空说明占位文案。
export function cleanSavedDescription(description?: string | null) {
  return description === "未填写设计说明。" ? "" : description ?? "";
}

// 当前产品统一使用千问；旧草稿中的其他模型值也在恢复时收敛到同一配置。
export function normalizeSavedModel(_provider?: string | null, _model?: string | null) {
  return { provider: "dashscope", model: "qwen3.8-max" };
}
