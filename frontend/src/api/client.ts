/**
 * The single point through which the browser talks to Django.
 *
 * Session cookies, not tokens: the SPA is served from the same origin as /api/, so
 * there is no CORS and nothing sensitive in browser storage (ADR 0003). Writes are
 * CSRF-protected, so every mutating request carries the X-CSRFToken header.
 *
 * No component should call fetch() directly.
 */

const BASE = "/api";

/** The error envelope every failure shares (docs/api.md). */
export interface ApiErrorBody {
  error: { code: string; message: string; detail: Record<string, unknown> };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: Record<string, unknown>;

  constructor(status: number, code: string, message: string, detail: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }

  /** Missing and not-yours both return 404, so callers cannot tell them apart. */
  get isNotFound() {
    return this.status === 404;
  }

  get isUnauthenticated() {
    return this.status === 401;
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[2]) : null;
}

let csrfPrimed = false;

/**
 * Make sure we hold a CSRF cookie before the first write.
 *
 * A single-page app has no server-rendered form to carry the token, so it asks for one.
 */
export async function primeCsrf(): Promise<void> {
  if (csrfPrimed && readCookie("csrftoken")) return;
  await fetch(`${BASE}/auth/csrf`, { credentials: "same-origin" });
  csrfPrimed = true;
}

const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

interface RequestOptions {
  method?: string;
  /** JSON body. Mutually exclusive with `form`. */
  body?: unknown;
  /** multipart body, for uploads. */
  form?: FormData;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};

  if (WRITE_METHODS.has(method)) {
    await primeCsrf();
    const token = readCookie("csrftoken");
    if (token) headers["X-CSRFToken"] = token;
  }

  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form; // let the browser set the multipart boundary
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body,
    credentials: "same-origin",
    signal: options.signal,
  });

  if (response.status === 204) return undefined as T;

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const envelope = (payload as ApiErrorBody)?.error;
    throw new ApiError(
      response.status,
      envelope?.code ?? "http_error",
      envelope?.message ?? `Request failed (${response.status})`,
      envelope?.detail ?? {},
    );
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", form }),
  /** Absolute URL for a download the browser should fetch itself. */
  url: (path: string) => `${BASE}${path}`,
};
