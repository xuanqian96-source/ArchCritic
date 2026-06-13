// 工作区状态：集中保存项目草稿、图纸、评图过程和报告，供全部页面复用。
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren } from "react";
import { checkHealth } from "../api/client";
import { deleteDrawing, deleteDrawings, listDrawings, updateDrawing, uploadDrawing } from "../api/files";
import { cloneProject, createProject, getProject, getProjectHistory, listProjects, listProjectSubmissions, updateProject } from "../api/projects";
import { downloadReport, getReport, listChatMessages, sendChat } from "../api/reports";
import { cancelEvaluation, createSubmission, deleteAttachment, evaluateStream, getSubmission, listAttachments, updateSubmission, uploadAttachment } from "../api/submissions";
import type { Attachment, ChatMessage, DrawingFile, EvaluationStreamEvent, OverallReport, Project, Submission, SubmissionHistory } from "../types/api";

const DEFAULT_AGENTS = ["function_agent", "site_agent", "form_agent", "structure_agent", "review_agent"];
const DEFAULT_MODEL = { provider: "dashscope", model: "qwen3.6-plus", label: "qwen3.6-plus" };
const ACCEPTED_DRAWING_TYPES = ["application/pdf"];

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
  progress: number;
  completedAgents: string[];
  activeAgent: string;
  messages: string[];
  error: string;
}

interface WorkspaceState {
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
  sendQuestion: (content: string) => Promise<void>;
  inheritProject: (projectId: number, sourceSubmissionId?: number) => Promise<void>;
  refreshProjects: () => Promise<void>;
  syncProjectName: (projectIds: number[], name: string) => void;
  syncSubmissionTitle: (submissionId: number, title: string) => void;
  openProject: (projectId: number, preloadProject?: Project) => Promise<void>;
  openSubmission: (submissionId: number, preload?: SubmissionPreload) => Promise<void>;
  prefetchSubmission: (submissionId: number, preload?: SubmissionPreload) => void;
}

const DEFAULT_DRAFT: DraftValues = {
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

const EMPTY_EVALUATION: EvaluationStatus = {
  running: false,
  progress: 0,
  completedAgents: [],
  activeAgent: "",
  messages: [],
  error: "",
};

// 判断文件是否可以作为图纸上传。
function isAcceptedDrawingFile(file: File) {
  return file.type.startsWith("image/") || ACCEPTED_DRAWING_TYPES.includes(file.type);
}

const WorkspaceContext = createContext<WorkspaceState | null>(null);
const LAST_SUBMISSION_KEY = "archcritic:last-submission-id";

interface SubmissionPreload {
  project?: Project;
  submission?: Submission;
}

interface SubmissionSnapshot {
  project: Project;
  submission: Submission;
  drawings: DrawingFile[];
  attachments: Attachment[];
  history: SubmissionHistory[];
  report: OverallReport | null;
  chatMessages: ChatMessage[];
}

// 把流式事件转换为等待页需要的状态。
function applyEvaluationEvent(
  current: EvaluationStatus,
  event: EvaluationStreamEvent,
): EvaluationStatus {
  const payload = event.payload;
  if (event.event === "status") {
    return { ...current, messages: [...current.messages, String(payload.message ?? "")] };
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
    return { ...current, running: false, error: String(payload.message ?? "评图失败。") };
  }
  return current;
}

// 兼容旧草稿中保存过的空说明占位文案。
function cleanSavedDescription(description?: string | null) {
  return description === "未填写设计说明。" ? "" : description ?? "";
}

// 旧草稿可能保存过演示模型，恢复时统一转成当前真实默认模型。
function normalizeSavedModel(provider?: string | null, model?: string | null) {
  if (provider === "gemini") return { provider, model: model || "gemini-2.5-flash" };
  return { provider: "dashscope", model: model && model !== "demo" ? model : "qwen3.6-plus" };
}

// 为所有页面提供统一工作区状态。
export function WorkspaceProvider({ children }: PropsWithChildren) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [drawings, setDrawings] = useState<DrawingFile[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [report, setReport] = useState<OverallReport | null>(null);
  const [history, setHistory] = useState<SubmissionHistory[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState<DraftValues>(DEFAULT_DRAFT);
  const [draftDirty, setDraftDirty] = useState(false);
  const [selectedDrawingId, setSelectedDrawingId] = useState<number | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationStatus>(EMPTY_EVALUATION);
  const [notice, setNotice] = useState("");
  const openRequestRef = useRef(0);
  const submissionCacheRef = useRef(new Map<number, SubmissionSnapshot | Promise<SubmissionSnapshot>>());

  // 当前提交内容变化后清掉详情缓存，避免从首页回来时看到旧图纸或旧附件。
  const invalidateSubmissionCache = useCallback((submissionId?: number | null) => {
    if (!submissionId) return;
    submissionCacheRef.current.delete(submissionId);
  }, []);

  // 更新单个草稿字段。
  const setDraftField = useCallback(<K extends keyof DraftValues>(field: K, value: DraftValues[K]) => {
    setDraft((current) => ({ ...current, [field]: value }));
    setDraftDirty(true);
  }, []);

  // 重新加载项目首页所需列表。
  const refreshProjects = useCallback(async () => {
    try {
      setProjects(await listProjects());
    } catch {
      // 后端未启动时仍允许查看静态页面，真正保存时再显示错误。
    }
  }, []);

  // 按后端内容恢复表单，避免刷新页面后丢失当前项目。
  const fillDraft = useCallback((savedProject: Project, savedSubmission?: Submission | null) => {
    const restoredModel = normalizeSavedModel(
      savedSubmission?.selected_model_provider,
      savedSubmission?.selected_model_name,
    );
    setDraft((current) => ({
      ...current,
      name: savedProject.name,
      buildingType: savedProject.building_type,
      ownerName: savedProject.owner_name,
      grade: savedProject.grade,
      siteLocation: savedProject.site_location ?? "",
      courseName: savedProject.course_name ?? "",
      description: savedSubmission ? cleanSavedDescription(savedSubmission.description) : current.description,
      designStage: savedSubmission?.design_stage ?? current.designStage,
      enabledAgents: savedSubmission?.enabled_agents?.length ? savedSubmission.enabled_agents : current.enabledAgents,
      modelProvider: savedSubmission ? restoredModel.provider : current.modelProvider,
      modelName: savedSubmission ? restoredModel.model : current.modelName,
      modelLabel: savedSubmission ? restoredModel.model : current.modelLabel,
    }));
    setDraftDirty(false);
  }, []);

  // 读取并缓存提交详情，历史版本数据稳定，重复打开时不再重复请求。
  const getSubmissionSnapshot = useCallback((submissionId: number, preload?: SubmissionPreload): Promise<SubmissionSnapshot> => {
    const cached = submissionCacheRef.current.get(submissionId);
    if (cached) return Promise.resolve(cached);
    const request = (async () => {
      const savedSubmission = preload?.submission ?? await getSubmission(submissionId);
      const savedProject = preload?.project ?? await getProject(savedSubmission.project_id);
      const [savedDrawings, savedAttachments, savedHistory, savedReport, savedChatMessages] = await Promise.all([
        listDrawings(submissionId),
        listAttachments(submissionId).catch(() => []),
        getProjectHistory(savedProject.id),
        getReport(submissionId).catch(() => null),
        listChatMessages(submissionId).catch(() => []),
      ]);
      return {
        project: savedProject,
        submission: savedSubmission,
        drawings: savedDrawings,
        attachments: savedAttachments,
        history: savedHistory,
        report: savedReport,
        chatMessages: savedChatMessages,
      };
    })();
    submissionCacheRef.current.set(submissionId, request);
    request.then((snapshot) => {
      submissionCacheRef.current.set(submissionId, snapshot);
    }).catch(() => {
      submissionCacheRef.current.delete(submissionId);
    });
    return request;
  }, []);

  // 把已读取的提交快照写入当前页面。
  const applySubmissionSnapshot = useCallback((snapshot: SubmissionSnapshot) => {
    setProject(snapshot.project);
    setSubmission(snapshot.submission);
    setDrawings(snapshot.drawings);
    setAttachments(snapshot.attachments);
    setHistory(snapshot.history);
    setReport(snapshot.report);
    setChatMessages(snapshot.chatMessages);
    setSelectedDrawingId(snapshot.drawings[0]?.id ?? null);
    fillDraft(snapshot.project, snapshot.submission);
    setDraftDirty(false);
    window.localStorage.setItem(LAST_SUBMISSION_KEY, String(snapshot.submission.id));
  }, [fillDraft]);

  // 预取提交详情，只填缓存，不改变当前页面。
  const prefetchSubmission = useCallback((submissionId: number, preload?: SubmissionPreload) => {
    void getSubmissionSnapshot(submissionId, preload).catch(() => undefined);
  }, [getSubmissionSnapshot]);

  // 同步侧栏项目重命名后的当前页面状态，避免报告页继续显示旧项目名。
  const syncProjectName = useCallback((projectIds: number[], name: string) => {
    const idSet = new Set(projectIds);
    setProjects((current) => current.map((item) => idSet.has(item.id) ? { ...item, name } : item));
    setProject((current) => current && idSet.has(current.id) ? { ...current, name } : current);
    setDraft((current) => project && idSet.has(project.id) ? { ...current, name } : current);
    submissionCacheRef.current.forEach((cached, key) => {
      if (cached instanceof Promise) return;
      if (!idSet.has(cached.project.id)) return;
      submissionCacheRef.current.set(key, { ...cached, project: { ...cached.project, name } });
    });
  }, [project]);

  // 同步侧栏版本重命名后的当前页面状态和历史版本列表。
  const syncSubmissionTitle = useCallback((submissionId: number, title: string) => {
    setSubmission((current) => current?.id === submissionId ? { ...current, title } : current);
    setHistory((current) => current.map((item) => item.id === submissionId ? { ...item, title } : item));
    submissionCacheRef.current.forEach((cached, key) => {
      if (cached instanceof Promise) return;
      if (cached.submission.id !== submissionId && !cached.history.some((item) => item.id === submissionId)) return;
      submissionCacheRef.current.set(key, {
        ...cached,
        submission: cached.submission.id === submissionId ? { ...cached.submission, title } : cached.submission,
        history: cached.history.map((item) => item.id === submissionId ? { ...item, title } : item),
      });
    });
  }, []);

  // 打开一个历史提交，并同步图纸、附件、报告与项目历史。
  const openSubmission = useCallback(async (submissionId: number, preload?: SubmissionPreload) => {
    const requestId = ++openRequestRef.current;
    const snapshot = await getSubmissionSnapshot(submissionId, preload);
    if (requestId !== openRequestRef.current) return;
    applySubmissionSnapshot(snapshot);
  }, [applySubmissionSnapshot, getSubmissionSnapshot]);

  // 打开项目最近一次提交；新项目则只恢复基础资料。
  const openProject = useCallback(async (projectId: number, preloadProject?: Project) => {
    const requestId = ++openRequestRef.current;
    const savedProject = preloadProject ?? await getProject(projectId);
    const submissions = await listProjectSubmissions(projectId);
    if (requestId !== openRequestRef.current) return;
    if (submissions[0]) {
      await openSubmission(submissions[0].id, { project: savedProject, submission: submissions[0] });
      return;
    }
    setProject(savedProject);
    setSubmission(null);
    setDrawings([]);
    setAttachments([]);
    setReport(null);
    setChatMessages([]);
    setHistory([]);
    setSelectedDrawingId(null);
    fillDraft(savedProject);
  }, [fillDraft, openSubmission]);

  useEffect(() => {
    void refreshProjects();
  }, [refreshProjects]);

  useEffect(() => {
    const savedId = Number(window.localStorage.getItem(LAST_SUBMISSION_KEY));
    if (savedId) void openSubmission(savedId).catch(() => window.localStorage.removeItem(LAST_SUBMISSION_KEY));
  }, [openSubmission]);

  // 清空当前工作区，并恢复空白新建表单。
  const resetDraft = useCallback(() => {
    setProject(null);
    setSubmission(null);
    setDrawings([]);
    setAttachments([]);
    setReport(null);
    setChatMessages([]);
    setHistory([]);
    setSelectedDrawingId(null);
    setEvaluation(EMPTY_EVALUATION);
    setDraft(DEFAULT_DRAFT);
    setDraftDirty(false);
    window.localStorage.removeItem(LAST_SUBMISSION_KEY);
  }, []);

  // 开关某个专项 Agent。
  const toggleAgent = useCallback((agentType: string) => {
    setDraft((current) => ({
      ...current,
      enabledAgents: current.enabledAgents.includes(agentType)
        ? current.enabledAgents.filter((item) => item !== agentType)
        : [...current.enabledAgents, agentType],
    }));
    setDraftDirty(true);
  }, []);

  // 创建或更新当前项目与草稿提交。
  const saveDraft = useCallback(async (): Promise<Submission> => {
    await checkHealth();
    const projectPayload = {
      name: draft.name || "未命名项目",
      building_type: draft.buildingType || "未填写类型",
      owner_name: draft.ownerName || "未填写提交人",
      grade: draft.grade,
      site_location: draft.siteLocation,
      course_name: draft.courseName,
    };
    const savedProject = project
      ? await updateProject(project.id, projectPayload)
      : await createProject(projectPayload);
    setProject(savedProject);
    const submissionPayload = {
      project_id: savedProject.id,
      title: `${draft.designStage}提交`,
      design_stage: draft.designStage,
      description: draft.description,
      status: "draft",
      enabled_agents: draft.enabledAgents,
      selected_model_provider: draft.modelProvider,
      selected_model_name: draft.modelName,
    };
    const savedSubmission = submission
      ? await updateSubmission(submission.id, submissionPayload)
      : await createSubmission(submissionPayload);
    setSubmission(savedSubmission);
    setDraftDirty(false);
    window.localStorage.setItem(LAST_SUBMISSION_KEY, String(savedSubmission.id));
    setNotice("草稿已保存。");
    invalidateSubmissionCache(savedSubmission.id);
    await refreshProjects();
    return savedSubmission;
  }, [draft, invalidateSubmissionCache, project, refreshProjects, submission]);

  // 上传图片并立即同步到右侧列表。
  const uploadFiles = useCallback(async (files: FileList | File[]) => {
    const savedSubmission = await saveDraft();
    const drawingFiles = Array.from(files).filter(isAcceptedDrawingFile);
    if (!drawingFiles.length) throw new Error("当前只支持上传图片或 PDF 图纸。");
    const added: DrawingFile[] = [];
    for (const file of drawingFiles) {
      added.push(await uploadDrawing(savedSubmission.id, "plan", file));
    }
    invalidateSubmissionCache(savedSubmission.id);
    setDrawings((current) => [...current, ...added]);
    setSelectedDrawingId(added[0]?.id ?? null);
    setDraftDirty(true);
    setNotice(`已上传 ${added.length} 张图纸。`);
  }, [invalidateSubmissionCache, saveDraft]);

  // 用新图片替换当前选中的图纸，并保留原卡片位置。
  const replaceSelectedDrawing = useCallback(async (file: File) => {
    if (!isAcceptedDrawingFile(file)) throw new Error("当前只支持上传图片或 PDF 图纸。");
    const savedSubmission = await saveDraft();
    const currentDrawing = drawings.find((item) => item.id === selectedDrawingId);
    if (!currentDrawing) {
      const added = await uploadDrawing(savedSubmission.id, "plan", file);
      invalidateSubmissionCache(savedSubmission.id);
      setDrawings((current) => [...current, added]);
      setSelectedDrawingId(added.id);
      setDraftDirty(true);
      setNotice("图纸已上传。");
      return;
    }
    const added = await uploadDrawing(savedSubmission.id, currentDrawing.drawing_type || "plan", file);
    const updated = await updateDrawing(added.id, {
      description: currentDrawing.description ?? "",
      sort_order: currentDrawing.sort_order,
    });
    await deleteDrawing(currentDrawing.id);
    invalidateSubmissionCache(savedSubmission.id);
    setDrawings((current) => current.map((item) => item.id === currentDrawing.id ? updated : item));
    setSelectedDrawingId(updated.id);
    setDraftDirty(true);
    setNotice("图纸已替换。");
  }, [drawings, invalidateSubmissionCache, saveDraft, selectedDrawingId]);

  // 上传任务书并同步当前页面。
  const uploadTaskbook = useCallback(async (file: File) => {
    const savedSubmission = await saveDraft();
    const added = await uploadAttachment(savedSubmission.id, file);
    invalidateSubmissionCache(savedSubmission.id);
    setAttachments((current) => [...current, added]);
    setDraftDirty(true);
    setNotice("任务书已上传。");
  }, [invalidateSubmissionCache, saveDraft]);

  // 删除已上传的任务书或补充资料。
  const deleteTaskbook = useCallback(async (attachmentId: number) => {
    await deleteAttachment(attachmentId);
    invalidateSubmissionCache(submission?.id);
    setAttachments((current) => current.filter((item) => item.id !== attachmentId));
    setDraftDirty(true);
    setNotice("附件已删除。");
  }, [invalidateSubmissionCache, submission?.id]);

  // 修改当前选中图纸的类型或说明。
  const updateSelectedDrawing = useCallback(async (payload: Partial<Pick<DrawingFile, "drawing_type" | "description">>) => {
    if (!selectedDrawingId) return;
    const updated = await updateDrawing(selectedDrawingId, payload);
    invalidateSubmissionCache(updated.submission_id);
    setDrawings((current) => current.map((item) => item.id === updated.id ? updated : item));
    setDraftDirty(true);
    setNotice("图纸信息已更新。");
  }, [invalidateSubmissionCache, selectedDrawingId]);

  // 删除当前选中图纸。
  const deleteSelectedDrawing = useCallback(async () => {
    if (!selectedDrawingId) return;
    await deleteDrawing(selectedDrawingId);
    invalidateSubmissionCache(submission?.id);
    setDrawings((current) => {
      const deletedIndex = current.findIndex((item) => item.id === selectedDrawingId);
      const remaining = current.filter((item) => item.id !== selectedDrawingId);
      const previousIndex = Math.max(0, deletedIndex - 1);
      setSelectedDrawingId(remaining[previousIndex]?.id ?? remaining[remaining.length - 1]?.id ?? null);
      return remaining;
    });
    setDraftDirty(true);
    setNotice("图纸已删除。");
  }, [invalidateSubmissionCache, selectedDrawingId, submission?.id]);

  // 删除当前提交的全部图纸。
  const deleteAllDrawings = useCallback(async () => {
    await deleteDrawings(drawings.map((item) => item.id));
    invalidateSubmissionCache(submission?.id);
    setDrawings([]);
    setSelectedDrawingId(null);
    setDraftDirty(true);
    setNotice("已删除所选图纸。");
  }, [drawings, invalidateSubmissionCache, submission?.id]);

  // 删除批量编辑中勾选的图纸。
  const deleteDrawingIds = useCallback(async (fileIds: number[]) => {
    if (!fileIds.length) return;
    const removingIds = new Set(fileIds);
    await deleteDrawings(fileIds);
    invalidateSubmissionCache(submission?.id);
    setDrawings((current) => {
      const currentSelectedId = selectedDrawingId;
      const deletedIndex = currentSelectedId ? current.findIndex((item) => item.id === currentSelectedId) : -1;
      const remaining = current.filter((item) => !removingIds.has(item.id));
      if (currentSelectedId && removingIds.has(currentSelectedId)) {
        const previous = current.slice(0, deletedIndex).reverse().find((item) => !removingIds.has(item.id));
        setSelectedDrawingId(previous?.id ?? remaining[0]?.id ?? null);
      }
      return remaining;
    });
    setDraftDirty(true);
    setNotice(`已删除 ${fileIds.length} 张图纸。`);
  }, [invalidateSubmissionCache, selectedDrawingId, submission?.id]);

  // 确认提交后启动流式评图。
  const startEvaluation = useCallback(async () => {
    try {
      const savedSubmission = await saveDraft();
      setReport(null);
      setEvaluation({ ...EMPTY_EVALUATION, running: true, progress: 10 });
      await updateSubmission(savedSubmission.id, {
        status: "evaluating",
        selected_model_provider: draft.modelProvider,
        selected_model_name: draft.modelName,
      });
      await evaluateStream(savedSubmission.id, draft.modelProvider, draft.modelName, (event) => {
        setEvaluation((current) => applyEvaluationEvent(current, event));
        if (event.event === "final") {
          setReport(event.payload.report as unknown as OverallReport);
          setEvaluation((current) => ({ ...current, running: false, progress: 100, activeAgent: "" }));
        }
      });
      setHistory(await getProjectHistory(savedSubmission.project_id));
      setNotice("评图报告已生成。");
    } catch (error) {
      const message = error instanceof Error ? error.message : "评图失败。";
      setEvaluation((current) => ({ ...current, running: false, error: message }));
      setNotice(message);
    }
  }, [draft.modelName, draft.modelProvider, saveDraft]);

  // 暂停当前评图任务。
  const pauseEvaluation = useCallback(async () => {
    if (!submission) return;
    await cancelEvaluation(submission.id);
    setEvaluation((current) => ({ ...current, running: false, activeAgent: "" }));
    setNotice("评图已暂停。");
  }, [submission]);

  // 下载当前报告。
  const downloadCurrentReport = useCallback(() => {
    if (submission) downloadReport(submission.id);
  }, [submission]);

  // 发送报告追问并同步右侧对话区。
  const sendQuestion = useCallback(async (content: string) => {
    if (!submission || !content.trim()) return;
    const question: ChatMessage = { role: "user", content: content.trim() };
    setChatMessages((current) => [...current, question]);
    const answer = await sendChat(submission.id, question.content, draft.modelProvider, draft.modelName);
    setChatMessages((current) => [...current, answer]);
  }, [draft.modelName, draft.modelProvider, submission]);

  // 从已有项目复制资料进入新一轮评图。
  const inheritProject = useCallback(async (projectId: number, sourceSubmissionId?: number) => {
    const cloned = await cloneProject(projectId, sourceSubmissionId);
    await openProject(cloned.id);
    await refreshProjects();
    setNotice("已继承项目资料。");
  }, [openProject, refreshProjects]);

  const value = useMemo(() => ({
    projects, project, submission, drawings, attachments, report, history, chatMessages,
    draft, draftDirty, selectedDrawingId, evaluation, notice, setNotice, setDraftField, resetDraft,
    toggleAgent, saveDraft, uploadFiles, replaceSelectedDrawing, uploadTaskbook, deleteTaskbook, selectDrawing: setSelectedDrawingId,
    updateSelectedDrawing, deleteSelectedDrawing, deleteAllDrawings, deleteDrawingIds, startEvaluation,
    pauseEvaluation, downloadCurrentReport, sendQuestion, inheritProject,
    refreshProjects, syncProjectName, syncSubmissionTitle, openProject, openSubmission, prefetchSubmission,
  }), [
    projects, project, submission, drawings, attachments, report, history, chatMessages,
    draft, draftDirty, selectedDrawingId, evaluation, notice, setDraftField, resetDraft,
    toggleAgent, saveDraft, uploadFiles, replaceSelectedDrawing, uploadTaskbook, deleteTaskbook, updateSelectedDrawing,
    deleteSelectedDrawing, deleteAllDrawings, deleteDrawingIds, startEvaluation, pauseEvaluation,
    downloadCurrentReport, sendQuestion, inheritProject, refreshProjects,
    syncProjectName, syncSubmissionTitle, openProject, openSubmission, prefetchSubmission,
  ]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

// 读取工作区状态。
export function useWorkspace(): WorkspaceState {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error("工作区状态尚未初始化。");
  return context;
}
