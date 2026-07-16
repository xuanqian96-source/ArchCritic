// 工作区文件动作：集中处理图纸、任务书的上传、替换、修改和删除。
import { useCallback, type Dispatch, type SetStateAction } from "react";
import { deleteDrawing, deleteDrawings, updateDrawing, uploadDrawing } from "../api/files";
import { deleteAttachment, uploadAttachment } from "../api/submissions";
import type { Attachment, DrawingFile, Submission } from "../types/api";
import { isAcceptedDrawingFile } from "./workspaceShared";

interface WorkspaceFileActionOptions {
  drawings: DrawingFile[];
  selectedDrawingId: number | null;
  submissionId?: number;
  saveDraft: () => Promise<Submission>;
  invalidateSubmissionCache: (submissionId?: number | null) => void;
  setAttachments: Dispatch<SetStateAction<Attachment[]>>;
  setDrawings: Dispatch<SetStateAction<DrawingFile[]>>;
  setSelectedDrawingId: Dispatch<SetStateAction<number | null>>;
  setDraftDirty: Dispatch<SetStateAction<boolean>>;
  setNotice: Dispatch<SetStateAction<string>>;
}

// 返回工作区使用的全部文件动作，状态容器只负责组合而不再承载细节。
export function useWorkspaceFileActions(options: WorkspaceFileActionOptions) {
  const {
    drawings,
    selectedDrawingId,
    submissionId,
    saveDraft,
    invalidateSubmissionCache,
    setAttachments,
    setDrawings,
    setSelectedDrawingId,
    setDraftDirty,
    setNotice,
  } = options;

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
  }, [invalidateSubmissionCache, saveDraft, setDraftDirty, setDrawings, setNotice, setSelectedDrawingId]);

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
  }, [drawings, invalidateSubmissionCache, saveDraft, selectedDrawingId, setDraftDirty, setDrawings, setNotice, setSelectedDrawingId]);

  const uploadTaskbook = useCallback(async (file: File) => {
    const savedSubmission = await saveDraft();
    const added = await uploadAttachment(savedSubmission.id, file);
    invalidateSubmissionCache(savedSubmission.id);
    setAttachments((current) => [...current, added]);
    setDraftDirty(true);
    setNotice("任务书已上传。");
  }, [invalidateSubmissionCache, saveDraft, setAttachments, setDraftDirty, setNotice]);

  const deleteTaskbook = useCallback(async (attachmentId: number) => {
    await deleteAttachment(attachmentId);
    invalidateSubmissionCache(submissionId);
    setAttachments((current) => current.filter((item) => item.id !== attachmentId));
    setDraftDirty(true);
    setNotice("附件已删除。");
  }, [invalidateSubmissionCache, setAttachments, setDraftDirty, setNotice, submissionId]);

  const updateSelectedDrawing = useCallback(async (payload: Partial<Pick<DrawingFile, "drawing_type" | "description">>) => {
    if (!selectedDrawingId) return;
    const updated = await updateDrawing(selectedDrawingId, payload);
    invalidateSubmissionCache(updated.submission_id);
    setDrawings((current) => current.map((item) => item.id === updated.id ? updated : item));
    setDraftDirty(true);
    setNotice("图纸信息已更新。");
  }, [invalidateSubmissionCache, selectedDrawingId, setDraftDirty, setDrawings, setNotice]);

  const deleteSelectedDrawing = useCallback(async () => {
    if (!selectedDrawingId) return;
    await deleteDrawing(selectedDrawingId);
    invalidateSubmissionCache(submissionId);
    setDrawings((current) => {
      const deletedIndex = current.findIndex((item) => item.id === selectedDrawingId);
      const remaining = current.filter((item) => item.id !== selectedDrawingId);
      const previousIndex = Math.max(0, deletedIndex - 1);
      setSelectedDrawingId(remaining[previousIndex]?.id ?? remaining[remaining.length - 1]?.id ?? null);
      return remaining;
    });
    setDraftDirty(true);
    setNotice("图纸已删除。");
  }, [invalidateSubmissionCache, selectedDrawingId, setDraftDirty, setDrawings, setNotice, setSelectedDrawingId, submissionId]);

  const deleteAllDrawings = useCallback(async () => {
    await deleteDrawings(drawings.map((item) => item.id));
    invalidateSubmissionCache(submissionId);
    setDrawings([]);
    setSelectedDrawingId(null);
    setDraftDirty(true);
    setNotice("已删除所选图纸。");
  }, [drawings, invalidateSubmissionCache, setDraftDirty, setDrawings, setNotice, setSelectedDrawingId, submissionId]);

  const deleteDrawingIds = useCallback(async (fileIds: number[]) => {
    if (!fileIds.length) return;
    const removingIds = new Set(fileIds);
    await deleteDrawings(fileIds);
    invalidateSubmissionCache(submissionId);
    setDrawings((current) => {
      const deletedIndex = selectedDrawingId ? current.findIndex((item) => item.id === selectedDrawingId) : -1;
      const remaining = current.filter((item) => !removingIds.has(item.id));
      if (selectedDrawingId && removingIds.has(selectedDrawingId)) {
        const previous = current.slice(0, deletedIndex).reverse().find((item) => !removingIds.has(item.id));
        setSelectedDrawingId(previous?.id ?? remaining[0]?.id ?? null);
      }
      return remaining;
    });
    setDraftDirty(true);
    setNotice(`已删除 ${fileIds.length} 张图纸。`);
  }, [invalidateSubmissionCache, selectedDrawingId, setDraftDirty, setDrawings, setNotice, setSelectedDrawingId, submissionId]);

  return {
    deleteAllDrawings,
    deleteDrawingIds,
    deleteSelectedDrawing,
    deleteTaskbook,
    replaceSelectedDrawing,
    updateSelectedDrawing,
    uploadFiles,
    uploadTaskbook,
  };
}
