// API 基础客户端：集中处理后端地址、超时和错误提示。
const DEFAULT_TIMEOUT_MS = 180_000;
const TRANSIENT_STATUS_CODES = new Set([502, 503, 504]);

type RequestOptions = RequestInit & {
  timeoutMs?: number;
  retryNetworkErrors?: number;
};

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

// 短暂等待后重试，吸收移动网络切换和边缘节点瞬时抖动。
function waitBeforeRetry(attempt: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, 400 * attempt));
}

// 发起 JSON 请求，并在超时或后端不可达时返回明确原因。
export async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const retryNetworkErrors = options.retryNetworkErrors ?? (method === "GET" || method === "HEAD" ? 1 : 0);
  const { timeoutMs: _timeoutMs, retryNetworkErrors: _retryNetworkErrors, signal: _signal, ...requestOptions } = options;
  void _timeoutMs;
  void _retryNetworkErrors;
  void _signal;
  let lastError: unknown;

  for (let attempt = 0; attempt <= retryNetworkErrors; attempt += 1) {
    const controller = new AbortController();
    const abortFromCaller = () => controller.abort();
    if (options.signal?.aborted) controller.abort();
    else options.signal?.addEventListener("abort", abortFromCaller, { once: true });
    const timer = window.setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
    try {
      const response = await fetch(apiUrl(path), {
        credentials: "include",
        ...requestOptions,
        signal: controller.signal,
      });
      if (!response.ok) {
        const responseError = new Error(await readError(response));
        if (TRANSIENT_STATUS_CODES.has(response.status) && attempt < retryNetworkErrors) {
          lastError = responseError;
          await waitBeforeRetry(attempt + 1);
          continue;
        }
        throw responseError;
      }
      return await response.json() as T;
    } catch (error) {
      if (options.signal?.aborted) throw new Error("请求已取消。");
      const isTimeout = error instanceof DOMException && error.name === "AbortError";
      const isNetworkError = error instanceof TypeError;
      if ((isTimeout || isNetworkError) && attempt < retryNetworkErrors) {
        lastError = error;
        await waitBeforeRetry(attempt + 1);
        continue;
      }
      if (isTimeout) throw new Error("网络连接不稳定，请稍后重试。");
      if (isNetworkError) throw new Error("暂时无法连接服务，请检查网络后重试。");
      throw error;
    } finally {
      window.clearTimeout(timer);
      options.signal?.removeEventListener("abort", abortFromCaller);
    }
  }

  throw lastError instanceof Error ? lastError : new Error("暂时无法连接服务，请稍后重试。");
}

// 上传文件，并复用统一错误提示。
export async function uploadForm<T>(path: string, formData: FormData): Promise<T> {
  return requestJson<T>(path, { method: "POST", body: formData });
}

// 检查后端服务是否可访问。
export async function checkHealth(): Promise<void> {
  await requestJson("/health");
}
