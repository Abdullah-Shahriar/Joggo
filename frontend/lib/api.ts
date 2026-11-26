export class ApiError extends Error {
  code: string;
  requestId: string;
  status: number;
  existingDocumentId?: string;

  constructor(
    code: string,
    message: string,
    requestId: string,
    status: number,
    existingDocumentId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.requestId = requestId;
    this.status = status;
    this.existingDocumentId = existingDocumentId;
  }
}

export type ToastPayload = {
  kind: "success" | "error";
  message: string;
  requestId?: string;
};

type ToastListener = (toast: ToastPayload) => void;
const toastListeners = new Set<ToastListener>();

export function subscribeToasts(listener: ToastListener): () => void {
  toastListeners.add(listener);
  return () => {
    toastListeners.delete(listener);
  };
}

export function emitToast(payload: ToastPayload): void {
  toastListeners.forEach((fn) => fn(payload));
}

interface ApiRequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  redirectOn401?: boolean;
  silentErrorToast?: boolean;
  skipRefresh?: boolean;
}

const NO_REFRESH_PATHS = new Set([
  "/auth/login",
  "/auth/signup",
  "/auth/google",
  "/auth/refresh",
  "/auth/logout",
]);

let refreshPromise: Promise<boolean> | null = null;

async function attemptRefresh(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      const res = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "include",
        headers: {
          "X-Requested-With": "fetch",
        },
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

async function parseError(res: Response): Promise<ApiError> {
  let code = "INTERNAL_ERROR";
  let message = "Something went wrong. Please try again.";
  let requestId = res.headers.get("x-request-id") || "";
  let existingDocumentId: string | undefined;

  try {
    const data = await res.json();
    if (data && typeof data === "object" && data.error) {
      code = String(data.error.code || code);
      message = String(data.error.message || message);
      requestId = String(data.error.request_id || requestId);
      if (data.error.existing_document_id) {
        existingDocumentId = String(data.error.existing_document_id);
      }
    }
  } catch {
    // Keep generic fallback
  }

  return new ApiError(code, message, requestId, res.status, existingDocumentId);
}

function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  const current = window.location.pathname + window.location.search;
  if (current.startsWith("/login") || current.startsWith("/signup")) return;
  const next = encodeURIComponent(current);
  window.location.href = `/login?next=${next}`;
}

async function rawFetch(path: string, options: ApiRequestOptions, isRetry = false): Promise<Response> {
  const method = options.method ?? "GET";
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const headers: Record<string, string> = {
    "X-Requested-With": "fetch",
    ...(options.headers || {}),
  };
  if (!isFormData && options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`/api${path}`, {
    method,
    credentials: "include",
    headers,
    body:
      options.body === undefined
        ? undefined
        : isFormData
          ? (options.body as FormData)
          : JSON.stringify(options.body),
  });

  if (
    res.status === 401 &&
    !isRetry &&
    !options.skipRefresh &&
    !NO_REFRESH_PATHS.has(path)
  ) {
    const refreshed = await attemptRefresh();
    if (refreshed) {
      return rawFetch(path, options, true);
    }
    if (options.redirectOn401 !== false) {
      redirectToLogin();
    }
  }

  return res;
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const res = await rawFetch(path, options, false);

  if (!res.ok) {
    const err = await parseError(res);
    if (!options.silentErrorToast) {
      emitToast({
        kind: "error",
        message: err.message,
        requestId: err.requestId || undefined,
      });
    }
    throw err;
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export async function apiBlob(
  path: string,
  options: Omit<ApiRequestOptions, "body"> = {},
): Promise<{ blob: Blob; filename: string | null }> {
  const res = await rawFetch(path, options, false);
  if (!res.ok) {
    const err = await parseError(res);
    if (!options.silentErrorToast) {
      emitToast({
        kind: "error",
        message: err.message,
        requestId: err.requestId || undefined,
      });
    }
    throw err;
  }
  const cd = res.headers.get("content-disposition") || "";
  const match = cd.match(/filename="([^"]+)"/);
  return {
    blob: await res.blob(),
    filename: match ? match[1] : null,
  };
}
