/**
 * Typed API client.
 *
 * Owns bearer-token plumbing: attaches the access token, auto-refreshes
 * on 401 once, and persists tokens to localStorage. Everything returns
 * typed results — the call sites never see raw JSON.
 */

import type {
  ChatRequest,
  ChatResponse,
  FeedbackSignal,
  TokenPair,
  UserPublic,
} from "@/types/api";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const STORAGE = { access: "cinebot.access", refresh: "cinebot.refresh" } as const;

export function getTokens(): TokenPair | null {
  const access = localStorage.getItem(STORAGE.access);
  const refresh = localStorage.getItem(STORAGE.refresh);
  if (!access || !refresh) return null;
  return { access_token: access, refresh_token: refresh, token_type: "bearer" };
}

export function setTokens(t: TokenPair): void {
  localStorage.setItem(STORAGE.access, t.access_token);
  localStorage.setItem(STORAGE.refresh, t.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(STORAGE.access);
  localStorage.removeItem(STORAGE.refresh);
}

// ── Request plumbing ─────────────────────────────────────
class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`${status}: ${detail}`);
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  retried = false,
): Promise<T> {
  const tokens = getTokens();
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json");
  if (tokens) headers.set("authorization", `Bearer ${tokens.access_token}`);

  const res = await fetch(`${BASE}${path}`, { ...init, headers });

  // Auto-refresh on 401 exactly once. If refresh itself fails, sign out.
  if (res.status === 401 && !retried && tokens && path !== "/api/v1/auth/refresh") {
    const refreshed = await tryRefresh();
    if (refreshed) return request<T>(path, init, true);
    clearTokens();
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // body isn't JSON — ignore, use statusText
    }
    throw new ApiError(res.status, detail);
  }

  // 204 — no body
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function tryRefresh(): Promise<boolean> {
  const tokens = getTokens();
  if (!tokens) return false;
  try {
    const next = await request<TokenPair>("/api/v1/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: tokens.refresh_token }),
    });
    setTokens(next);
    return true;
  } catch {
    return false;
  }
}

// ── Public API ───────────────────────────────────────────
export const api = {
  async register(
    email: string,
    password: string,
    display_name?: string,
  ): Promise<UserPublic> {
    return request<UserPublic>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name }),
    });
  },

  async login(email: string, password: string): Promise<TokenPair> {
    const pair = await request<TokenPair>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setTokens(pair);
    return pair;
  },

  logout(): void {
    clearTokens();
  },

  async chat(payload: ChatRequest): Promise<ChatResponse> {
    return request<ChatResponse>("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async feedback(args: {
    session_id: string;
    movie_id: number;
    signal: FeedbackSignal;
    source_message_id?: string;
  }): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>("/api/v1/feedback", {
      method: "POST",
      body: JSON.stringify(args),
    });
  },
};

export { ApiError };
