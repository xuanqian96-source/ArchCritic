// 图纸接口：负责上传、读取、修改和删除。
import { requestJson, uploadForm } from "./client";
import type { DrawingFile } from "../types/api";

// 上传图纸。
export function uploadDrawing(submissionId: number, drawingType: string, file: File): Promise<DrawingFile> {
  const formData = new FormData();
  formData.append("drawing_type", drawingType);
  formData.append("file", file);
  return uploadForm(`/api/submissions/${submissionId}/files`, formData);
}

// 获取某次提交的图纸。
export function listDrawings(submissionId: number): Promise<DrawingFile[]> {
  return requestJson(`/api/submissions/${submissionId}/files`);
}

// 更新图纸类型或说明。
export function updateDrawing(fileId: number, payload: Partial<Pick<DrawingFile, "drawing_type" | "description" | "sort_order">>): Promise<DrawingFile> {
  return requestJson(`/api/files/${fileId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// 删除单张图纸。
export function deleteDrawing(fileId: number): Promise<void> {
  return requestJson(`/api/files/${fileId}`, { method: "DELETE" });
}

// 批量删除图纸。
export function deleteDrawings(fileIds: number[]): Promise<void> {
  return requestJson("/api/files/batch-delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_ids: fileIds }),
  });
}
