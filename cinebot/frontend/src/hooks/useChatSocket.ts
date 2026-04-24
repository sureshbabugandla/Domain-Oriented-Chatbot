/**
 * Streaming-chat WebSocket hook.
 *
 * Wire protocol (matches backend/app/api/routes/chat.py):
 *
 *   out: { session_id, message }         (after auth frame if no ?token=)
 *   in:  { type: "token", content: str }
 *   in:  { type: "done",  payload: ChatResponse }
 *   in:  { type: "error", detail: str }
 *
 * Reconnect: exponential backoff up to 30s, gives up after 6 tries.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getTokens } from "@/lib/api";
import type { ChatResponse } from "@/types/api";

type SocketStatus = "idle" | "connecting" | "open" | "closed" | "error";

interface Handlers {
  onToken: (chunk: string) => void;
  onDone: (response: ChatResponse) => void;
  onError: (detail: string) => void;
}

const WS_BASE =
  import.meta.env.VITE_WS_BASE_URL ??
  (typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`
    : "");

export function useChatSocket(handlers: Handlers) {
  const [status, setStatus] = useState<SocketStatus>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const reconnectTimer = useRef<number | null>(null);
  const handlersRef = useRef(handlers);

  // Keep handlers current without triggering reconnects when callbacks change.
  useEffect(() => {
    handlersRef.current = handlers;
  });

  const connect = useCallback(() => {
    const tokens = getTokens();
    if (!tokens) {
      setStatus("error");
      return;
    }
    setStatus("connecting");

    // Send token as first message rather than ?token= so it never lands
    // in server access logs.
    const ws = new WebSocket(`${WS_BASE}/api/v1/chat/stream`);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ auth: tokens.access_token }));
      retryRef.current = 0;
      setStatus("open");
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        switch (msg.type) {
          case "token":
            handlersRef.current.onToken(String(msg.content ?? ""));
            break;
          case "done":
            handlersRef.current.onDone(msg.payload as ChatResponse);
            break;
          case "error":
            handlersRef.current.onError(String(msg.detail ?? "server error"));
            break;
        }
      } catch {
        handlersRef.current.onError("malformed server message");
      }
    };

    ws.onerror = () => setStatus("error");
    ws.onclose = () => {
      setStatus("closed");
      if (retryRef.current < 6) {
        const backoff = Math.min(30_000, 500 * 2 ** retryRef.current);
        retryRef.current += 1;
        reconnectTimer.current = window.setTimeout(connect, backoff);
      }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback(
    (sessionId: string | null, message: string) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return false;
      ws.send(JSON.stringify({ session_id: sessionId, message }));
      return true;
    },
    [],
  );

  return { status, send };
}
