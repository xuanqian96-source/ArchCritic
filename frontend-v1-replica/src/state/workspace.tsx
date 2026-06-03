// 工作区状态：集中保存项目草稿、图纸、评图过程和报告，供全部页面复用。
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";
import { checkHealth } from "../api/client";
import { deleteDrawing, deleteDrawings, listDrawings, updateDrawing, uploadDrawing } from "../api/files";
import { cloneProject, createProject, getProject, getProjectHistory, listProjects, listProjectSubmissions, updateProject } from "../api/projects";
import { downloadReport, getReport, listChatMessages, sendChat } from "../api/reports";
import { cancelEvaluation, createSubmission, evaluateStream, getSubmission, listAttachments, updateSubmission, uploadAttachment } from "../api/submissions";
import type { Attachment, ChatMessage, DrawingFile, EvaluationStreamEvent, OverallReport, Project, Submission, SubmissionHistory } from "../types/api";

const DEFAULT_AGENTS = ["site_agent", "function_agent", "form_agent", "structure_agent"];
const DEFAULT_MODEL = { provider: "mock", model: "demo", label: "ArchCritic Pro" };

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
  selectedDrawingId: number | null;
  evaluation: EvaluationStatus;
  notice: string;
  setNotice: (message: string) => void;
  setDraftField: <K extends keyof DraftValues>(field: K, value: DraftValues[K]) => void;
  resetDraft: () => void;
  toggleAgent: (agentType: string) => void;
  saveDraft: () => Promise<Submission>;
  uploadFiles: (files: FileList | File[]) => Promise<void>;
  uploadTaskbook: (file: File) => Promise<void>;
  selectDrawing: (fileId: number) => void;
  updateSelectedDrawing: (payload: Partial<Pick<DrawingFile, "drawing_type" | "description">>) => Promise<void>;
  deleteSelectedDrawing: () => Promise<void>;
  deleteAllDrawings: () => Promise<void>;
  startEvaluation: () => Promise<void>;
  pauseEvaluation: () => Promise<void>;
  downloadCurrentReport: () => void;
  sendQuestion: (content: string) => Promise<void>;
  inheritProject: (projectId: number) => Promise<void>;
  refreshProjects: () => Promise<void>;
  openProject: (projectId: number) => Promise<void>;
  openSubmission: (submissionId: number) => Promise<void>;
}

const DEFAULT_DRAFT: DraftValues = {
  name: "美术馆方案",
  buildingType: "公共建筑",
  ownerName: "前端工程师",
  grade: "三年级",
  siteLocation: "上海市徐汇滨江",
  courseName: "建筑设计课 · 三年级",
  description: "公共文化建筑，重点关注城市界面、展厅流线与复合公共空间。",
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

const WorkspaceContext = createContext<WorkspaceState | null>(null);
const LAST_SUBMISSION_KEY = "archcritic:last-submission-id";

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
  const [selectedDrawingId, setSelectedDrawingId] = useState<number | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationStatus>(EMPTY_EVALUATION);
  const [notice, setNotice] = useState("");

  // 更新单个草稿字段。
  const setDraftField = useCallback(<K extends keyof DraftValues>(field: K, value: DraftValues[K]) => {
    setDraft((current) => ({ ...current, [field]: value }));
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
    setDraft((current) => ({
      ...current,
      name: savedProject.name,
      buildingType: savedProject.building_type,
      ownerName: savedProject.owner_name,
      grade: savedProject.grade,
      siteLocation: savedProject.site_location ?? "",
      courseName: savedProject.course_name ?? "",
      description: savedSubmission?.description ?? current.description,
      designStage: savedSubmission?.design_stage ?? current.designStage,
      enabledAgents: savedSubmission?.enabled_agents?.length ? savedSubmission.enabled_agents : current.enabledAgents,
      modelProvider: savedSubmission?.selected_model_provider ?? current.modelProvider,
      modelName: savedSubmission?.selected_model_name ?? current.modelName,
    }));
  }, []);

  // 打开一个历史提交，并同步图纸、附件、报告与项目历史。
  const openSubmission = useCallback(async (submissionId: number) => {
    const savedSubmission = await getSubmission(submissionId);
    const savedProject = await getProject(savedSubmission.project_id);
    const [savedDrawings, savedAttachments, savedHistory, savedReport, savedChatMessages] = await Promise.all([
      listDrawings(submissionId),
      listAttachments(submissionId).catch(() => []),
      getProjectHistory(savedProject.id),
      getReport(submissionId).catch(() => null),
      listChatMessages(submissionId).catch(() => []),
    ]);
    setProject(savedProject);
    setSubmission(savedSubmission);
    setDrawings(savedDrawings);
    setAttachments(savedAttachments);
    setHistory(savedHistory);
    setReport(savedReport);
    setChatMessages(savedChatMessages);
    setSelectedDrawingId(savedDrawings[0]?.id ?? null);
    fillDraft(savedProject, savedSubmission);
    window.localStorage.setItem(LAST_SUBMISSION_KEY, String(submissionId));
  }, [fillDraft]);

  // 打开项目最近一次提交；新项目则只恢复基础资料。
  const openProject = useCallback(async (projectId: number) => {
    const savedProject = await getProject(projectId);
    const submissions = await listProjectSubmissions(projectId);
    if (submissions[0]) {
      await openSubmission(submissions[0].id);
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

  // 清空当前工作区，并恢复 Figma 默认表单内容。
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
      description: draft.description || "未填写设计说明。",
      status: "draft",
      enabled_agents: draft.enabledAgents,
      selected_model_provider: draft.modelProvider,
      selected_model_name: draft.modelName,
    };
    const savedSubmission = submission
      ? await updateSubmission(submission.id, submissionPayload)
      : await createSubmission(submissionPayload);
    setSubmission(savedSubmission);
    window.localStorage.setItem(LAST_SUBMISSION_KEY, String(savedSubmission.id));
    setNotice("草稿已保存。");
    await refreshProjects();
    return savedSubmission;
  }, [draft, project, refreshProjects, submission]);

  // 上传图片并立即同步到右侧列表。
  const uploadFiles = useCallback(async (files: FileList | File[]) => {
    const savedSubmission = await saveDraft();
    const imageFiles = Array.from(files).filter((file) => file.type.startsWith("image/"));
    if (!imageFiles.length) throw new Error("当前只支持上传图片文件。");
    const added: DrawingFile[] = [];
    for (const file of imageFiles) {
      added.push(await uploadDrawing(savedSubmission.id, "plan", file));
    }
    setDrawings((current) => [...current, ...added]);
    setSelectedDrawingId((current) => current ?? added[0]?.id ?? null);
    setNotice(`已上传 ${added.length} 张图纸。`);
  }, [saveDraft]);

  // 上传任务书并同步当前页面。
  const uploadTaskbook = useCallback(async (file: File) => {
    const savedSubmission = await saveDraft();
    const added = await uploadAttachment(savedSubmission.id, file);
    setAttachments((current) => [...current, added]);
    setNotice("任务书已上传。");
  }, [saveDraft]);

  // 修改当前选中图纸的类型或说明。
  const updateSelectedDrawing = useCallback(async (payload: Partial<Pick<DrawingFile, "drawing_type" | "description">>) => {
    if (!selectedDrawingId) return;
    const updated = await updateDrawing(selectedDrawingId, payload);
    setDrawings((current) => current.map((item) => item.id === updated.id ? updated : item));
    setNotice("图纸信息已更新。");
  }, [selectedDrawingId]);

  // 删除当前选中图纸。
  const deleteSelectedDrawing = useCallback(async () => {
    if (!selectedDrawingId) return;
    await deleteDrawing(selectedDrawingId);
    setDrawings((current) => {
      const remaining = current.filter((item) => item.id !== selectedDrawingId);
      setSelectedDrawingId(remaining[0]?.id ?? null);
      return remaining;
    });
    setNotice("图纸已删除。");
  }, [selectedDrawingId]);

  // 删除当前提交的全部图纸。
  const deleteAllDrawings = useCallback(async () => {
    await deleteDrawings(drawings.map((item) => item.id));
    setDrawings([]);
    setSelectedDrawingId(null);
    setNotice("已删除所选图纸。");
  }, [drawings]);

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
    const answer = await sendChat(submission.id, question.content);
    setChatMessages((current) => [...current, answer]);
  }, [submission]);

  // 从已有项目复制资料进入新一轮评图。
  const inheritProject = useCallback(async (projectId: number) => {
    const cloned = await cloneProject(projectId);
    await openProject(cloned.id);
    await refreshProjects();
    setNotice("已继承项目资料。");
  }, [openProject, refreshProjects]);

  const value = useMemo(() => ({
    projects, project, submission, drawings, attachments, report, history, chatMessages,
    draft, selectedDrawingId, evaluation, notice, setNotice, setDraftField, resetDraft,
    toggleAgent, saveDraft, uploadFiles, uploadTaskbook, selectDrawing: setSelectedDrawingId,
    updateSelectedDrawing, deleteSelectedDrawing, deleteAllDrawings, startEvaluation,
    pauseEvaluation, downloadCurrentReport, sendQuestion, inheritProject,
    refreshProjects, openProject, openSubmission,
  }), [
    projects, project, submission, drawings, attachments, report, history, chatMessages,
    draft, selectedDrawingId, evaluation, notice, setDraftField, resetDraft,
    toggleAgent, saveDraft, uploadFiles, uploadTaskbook, updateSelectedDrawing,
    deleteSelectedDrawing, deleteAllDrawings, startEvaluation, pauseEvaluation,
    downloadCurrentReport, sendQuestion, inheritProject, refreshProjects, openProject, openSubmission,
  ]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

// 读取工作区状态。
export function useWorkspace(): WorkspaceState {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error("工作区状态尚未初始化。");
  return context;
}
