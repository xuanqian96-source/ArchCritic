// 工作区状态：协调项目草稿、图纸、任务书、评图过程和报告。
import { useCallback, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren } from "react";
import { checkHealth } from "../api/client";
import { listDrawings } from "../api/files";
import { cloneProject, createProject, getProject, getProjectHistory, listProjects, listProjectSubmissions, updateProject } from "../api/projects";
import { downloadReport, getReport, listChatMessages, sendChat } from "../api/reports";
import { cancelEvaluation, createSubmission, evaluateStream, getSubmission, listAttachments, updateSubmission } from "../api/submissions";
import type { Attachment, ChatMessage, DrawingFile, OverallReport, Project, Submission, SubmissionHistory } from "../types/api";
import { useAuth } from "./auth";
import { applyEvaluationEvent, cleanSavedDescription, DEFAULT_DRAFT, DUPLICATE_PROJECT_NAME_MESSAGE, EMPTY_EVALUATION, type DraftValues, type EvaluationStatus, getLastSubmissionKey, LAST_SUBMISSION_KEY, normalizeProjectNameForCompare, normalizeSavedModel, type SubmissionPreload, type SubmissionSnapshot, type WorkspaceState, waitForChatFrame, WorkspaceContext } from "./workspaceShared";
import { useWorkspaceFileActions } from "./workspaceFileActions";

export function WorkspaceProvider({ children }: PropsWithChildren) {
  const { user } = useAuth();
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
  const evaluationRequestRef = useRef(0);
  const pauseRequestedRef = useRef(false);
  const submissionCacheRef = useRef(new Map<number, SubmissionSnapshot | Promise<SubmissionSnapshot>>());
  const draftRef = useRef(draft);
  const projectRef = useRef(project);
  const submissionRef = useRef(submission);
  const draftRevisionRef = useRef(0);
  const saveDraftRequestRef = useRef<Promise<Submission> | null>(null);
  const saveDraftQueuedRef = useRef(false);

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    projectRef.current = project;
  }, [project]);

  useEffect(() => {
    submissionRef.current = submission;
  }, [submission]);

  // 当前提交内容变化后清掉详情缓存，避免从首页回来时看到旧图纸或旧附件。
  const invalidateSubmissionCache = useCallback((submissionId?: number | null) => {
    if (!submissionId) return;
    submissionCacheRef.current.delete(submissionId);
  }, []);

  // 更新单个草稿字段。
  const setDraftField = useCallback(<K extends keyof DraftValues>(field: K, value: DraftValues[K]) => {
    draftRevisionRef.current += 1;
    setDraftDirty(true);
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
    window.localStorage.setItem(getLastSubmissionKey(user?.username), String(snapshot.submission.id));
  }, [fillDraft, user?.username]);

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
    if (!user) return;
    void refreshProjects();
    const scopedKey = getLastSubmissionKey(user.username);
    const legacyValue = window.localStorage.getItem(LAST_SUBMISSION_KEY);
    const savedId = Number(window.localStorage.getItem(scopedKey) ?? legacyValue);
    if (legacyValue && !window.localStorage.getItem(scopedKey)) {
      window.localStorage.setItem(scopedKey, legacyValue);
      window.localStorage.removeItem(LAST_SUBMISSION_KEY);
    }
    if (savedId) void openSubmission(savedId).catch(() => window.localStorage.removeItem(scopedKey));
    setDraft((current) => current.ownerName === DEFAULT_DRAFT.ownerName ? { ...current, ownerName: user.display_name } : current);
  }, [openSubmission, refreshProjects, user]);

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
    setDraft({ ...DEFAULT_DRAFT, ownerName: user?.display_name ?? DEFAULT_DRAFT.ownerName });
    setDraftDirty(false);
    window.localStorage.removeItem(getLastSubmissionKey(user?.username));
  }, [user?.display_name, user?.username]);

  // 开关某个专项 Agent。
  const toggleAgent = useCallback((agentType: string) => {
    draftRevisionRef.current += 1;
    setDraft((current) => ({
      ...current,
      enabledAgents: current.enabledAgents.includes(agentType)
        ? current.enabledAgents.filter((item) => item !== agentType)
        : [...current.enabledAgents, agentType],
    }));
    setDraftDirty(true);
  }, []);

  // 执行一次真实草稿保存，保存期间的新修改会保持未保存状态。
  const performDraftSave = useCallback(async (): Promise<Submission> => {
    await checkHealth();
    const draftSnapshot = draftRef.current;
    const projectSnapshot = projectRef.current;
    const submissionSnapshot = submissionRef.current;
    const startedRevision = draftRevisionRef.current;
    const projectPayload = {
      name: draftSnapshot.name || "未命名项目",
      building_type: draftSnapshot.buildingType || "未填写类型",
      owner_name: draftSnapshot.ownerName || "未填写提交人",
      grade: draftSnapshot.grade,
      site_location: draftSnapshot.siteLocation,
      course_name: draftSnapshot.courseName,
    };
    const normalizedProjectName = normalizeProjectNameForCompare(projectPayload.name);
    if (!projectSnapshot && normalizedProjectName && projects.some((item) => normalizeProjectNameForCompare(item.name) === normalizedProjectName)) {
      throw new Error(DUPLICATE_PROJECT_NAME_MESSAGE);
    }
    const savedProject = projectSnapshot
      ? await updateProject(projectSnapshot.id, projectPayload)
      : await createProject(projectPayload);
    projectRef.current = savedProject;
    setProject(savedProject);
    const submissionPayload = {
      project_id: savedProject.id,
      title: `${draftSnapshot.designStage}提交`,
      design_stage: draftSnapshot.designStage,
      description: draftSnapshot.description,
      status: "draft",
      enabled_agents: draftSnapshot.enabledAgents,
      selected_model_provider: draftSnapshot.modelProvider,
      selected_model_name: draftSnapshot.modelName,
    };
    const savedSubmission = submissionSnapshot
      ? await updateSubmission(submissionSnapshot.id, submissionPayload)
      : await createSubmission(submissionPayload);
    submissionRef.current = savedSubmission;
    setSubmission(savedSubmission);
    setDraftDirty(startedRevision !== draftRevisionRef.current);
    window.localStorage.setItem(getLastSubmissionKey(user?.username), String(savedSubmission.id));
    setNotice("草稿已保存。");
    invalidateSubmissionCache(savedSubmission.id);
    await refreshProjects();
    return savedSubmission;
  }, [invalidateSubmissionCache, projects, refreshProjects, user?.username]);

  // 创建或更新当前项目与草稿提交；连续保存会排队合并，避免重复创建草稿。
  const saveDraft = useCallback(async (): Promise<Submission> => {
    if (saveDraftRequestRef.current) {
      saveDraftQueuedRef.current = true;
      return saveDraftRequestRef.current;
    }
    const request = (async () => {
      let savedSubmission: Submission | null = null;
      do {
        saveDraftQueuedRef.current = false;
        savedSubmission = await performDraftSave();
      } while (saveDraftQueuedRef.current);
      return savedSubmission;
    })();
    saveDraftRequestRef.current = request;
    try {
      return await request;
    } finally {
      if (saveDraftRequestRef.current === request) {
        saveDraftRequestRef.current = null;
      }
    }
  }, [performDraftSave]);

  const {
    deleteAllDrawings,
    deleteDrawingIds,
    deleteSelectedDrawing,
    deleteTaskbook,
    replaceSelectedDrawing,
    updateSelectedDrawing,
    uploadFiles,
    uploadTaskbook,
  } = useWorkspaceFileActions({
    drawings,
    selectedDrawingId,
    submissionId: submission?.id,
    saveDraft,
    invalidateSubmissionCache,
    setAttachments,
    setDrawings,
    setSelectedDrawingId,
    setDraftDirty,
    setNotice,
  });

  // 确认提交后启动流式评图。
  const startEvaluation = useCallback(async () => {
    const requestId = evaluationRequestRef.current + 1;
    evaluationRequestRef.current = requestId;
    pauseRequestedRef.current = false;
    try {
      const savedSubmission = await saveDraft();
      let finalReceived = false;
      setReport(null);
      setEvaluation({ ...EMPTY_EVALUATION, running: true, progress: 5, startedAt: Date.now() });
      await updateSubmission(savedSubmission.id, {
        status: "evaluating",
        selected_model_provider: draft.modelProvider,
        selected_model_name: draft.modelName,
      });
      await evaluateStream(savedSubmission.id, draft.modelProvider, draft.modelName, (event) => {
        if (evaluationRequestRef.current !== requestId) return;
        if (pauseRequestedRef.current && event.event !== "status") return;
        setEvaluation((current) => applyEvaluationEvent(current, event));
        if (!pauseRequestedRef.current && event.event === "final") {
          finalReceived = true;
          setReport(event.payload.report as unknown as OverallReport);
          setEvaluation((current) => ({
            ...current,
            running: false,
            paused: false,
            progress: 100,
            activeAgent: "",
            activeStageId: "",
            completedStages: current.completedStages.includes("report") ? current.completedStages : [...current.completedStages, "report"],
            messages: [...current.messages, "评图已完成，请点击“查看评图报告”查看结果。"],
          }));
        }
      });
      if (finalReceived) {
        setHistory(await getProjectHistory(savedSubmission.project_id));
        setNotice("评图报告已生成。");
      }
    } catch (error) {
      if (pauseRequestedRef.current) {
        setEvaluation((current) => ({
          ...current,
          running: false,
          paused: true,
          activeAgent: "",
          activeStageId: "",
          messages: current.messages.includes("评图已暂停，可点击“继续评图”恢复。")
            ? current.messages
            : [...current.messages, "评图已暂停，可点击“继续评图”恢复。"],
        }));
        return;
      }
      const message = error instanceof Error ? error.message : "评图失败。";
      setEvaluation((current) => ({
        ...current,
        running: false,
        paused: false,
        errorStageId: current.activeAgent || current.activeStageId || "report",
        activeAgent: "",
        activeStageId: "",
        error: message,
      }));
      setNotice(message);
    }
  }, [draft.modelName, draft.modelProvider, saveDraft]);

  // 暂停当前评图任务。
  const pauseEvaluation = useCallback(async () => {
    if (!submission) return;
    pauseRequestedRef.current = true;
    await cancelEvaluation(submission.id);
    setEvaluation((current) => ({
      ...current,
      running: false,
      paused: true,
      activeAgent: "",
      activeStageId: "",
      pausedAt: Date.now(),
      elapsedBeforePause: current.startedAt ? current.elapsedBeforePause + Date.now() - current.startedAt : current.elapsedBeforePause,
      messages: current.messages.includes("评图已暂停，可点击“继续评图”恢复。")
        ? current.messages
        : [...current.messages, "评图已暂停，可点击“继续评图”恢复。"],
    }));
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
    setChatMessages((current) => [...current, { role: "assistant", content: "" }]);
    for (let index = 1; index <= answer.content.length; index += 1) {
      const nextContent = answer.content.slice(0, index);
      setChatMessages((current) => current.map((item, itemIndex) => (
        itemIndex === current.length - 1 ? { ...answer, content: nextContent } : item
      )));
      if (index % 3 === 0) await waitForChatFrame();
    }
    setChatMessages((current) => current.map((item, itemIndex) => (
      itemIndex === current.length - 1 ? answer : item
    )));
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
