// API 基础客户端：集中处理后端地址、超时和错误提示。
const DEFAULT_TIMEOUT_MS = 180_000;

// 根据当前网页主机计算后端地址，兼容 localhost 和局域网访问。
export function getApiBase(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) return configured.replace(/\/$/, "");
  const hostname = window.location.hostname || "127.0.0.1";
  return `http://${hostname}:8000`;
}

// 把后端相对路径转换为可直接访问的完整地址。
export function apiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `${getApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
}

// 读取后端错误并转换成用户能理解的提示。
async function readError(response: Response): Promise<string> {
  const payload = await response.json().catch(() => ({}));
  return typeof payload.detail === "string" ? payload.detail : "后端接口请求失败。";
}

// 发起 JSON 请求，并在超时或后端不可达时返回明确原因。
export async function requestJson<T>(path: string, options: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const { timeoutMs: _timeoutMs, ...requestOptions } = options;
  void _timeoutMs;
  try {
    const response = await fetch(apiUrl(path), { ...requestOptions, signal: controller.signal });
    if (!response.ok) throw new Error(await readError(response));
    return await response.json() as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("请求等待超时，请稍后重试。");
    }
    if (error instanceof TypeError) {
      throw new Error(`无法连接后端服务：${getApiBase()}。请确认后端已启动。`);
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

// 上传文件，并复用统一错误提示。
export async function uploadForm<T>(path: string, formData: FormData): Promise<T> {
  return requestJson<T>(path, { method: "POST", body: formData });
}

// 检查后端服务是否可访问。
export async function checkHealth(): Promise<void> {
  await requestJson("/health");
}
