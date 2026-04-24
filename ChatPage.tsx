/**
 * The main chat experience.
 *
 * State machine:
 *   idle → user sends message → optimistic user bubble appended →
 *   assistant "pending" bubble with typing indicator →
 *   token frames concat into pending.content → done frame replaces it
 *   with final text + recommendations.
 */

import { useCallback, useRef, useState } from "react";
import { MessageList } from "@/components/MessageList";
import { ChatComposer } from "@/components/ChatComposer";
import { Sidebar } from "@/components/Sidebar";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import { useChatSocket } from "@/hooks/useChatSocket";
import type {
  ChatResponse,
  FeedbackSignal,
  UIMessage,
} from "@/types/api";

let uid = 0;
const nextId = () => `m${++uid}-${Date.now().toString(36)}`;

export function ChatPage() {
  const sessionId = useStore((s) => s.sessionId);
  const setSessionId = useStore((s) => s.setSessionId);
  const newSession = useStore((s) => s.newSession);

  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const pendingIdRef = useRef<string | null>(null);

  // ── WebSocket handlers ──────────────────────────────
  const onToken = useCallback((chunk: string) => {
    const pid = pendingIdRef.current;
    if (!pid) return;
    setMessages((prev) =>
      prev.map((m) =>
        m.id === pid ? { ...m, content: m.content + chunk } : m,
      ),
    );
  }, []);

  const onDone = useCallback(
    (resp: ChatResponse) => {
      const pid = pendingIdRef.current;
      pendingIdRef.current = null;
      setStreaming(false);
      setSessionId(resp.session_id);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === pid
            ? {
                ...m,
                content: resp.text,
                recommendations: resp.recommendations,
                pending: false,
              }
            : m,
        ),
      );
    },
    [setSessionId],
  );

  const onError = useCallback((detail: string) => {
    const pid = pendingIdRef.current;
    pendingIdRef.current = null;
    setStreaming(false);
    setMessages((prev) =>
      prev.map((m) =>
        m.id === pid
          ? {
              ...m,
              content: `Sorry — ${detail}. Please try again.`,
              pending: false,
            }
          : m,
      ),
    );
  }, []);

  const { status, send } = useChatSocket({ onToken, onDone, onError });

  // ── Outgoing ────────────────────────────────────────
  const handleSend = useCallback(
    (text: string) => {
      const userMsg: UIMessage = {
        id: nextId(),
        role: "user",
        content: text,
        createdAt: Date.now(),
      };
      const pending: UIMessage = {
        id: nextId(),
        role: "assistant",
        content: "",
        pending: true,
        createdAt: Date.now(),
      };
      pendingIdRef.current = pending.id;
      setMessages((prev) => [...prev, userMsg, pending]);
      setStreaming(true);
      const sent = send(sessionId, text);
      if (!sent) {
        // WS isn't open — fall back to the REST endpoint so the user isn't
        // stuck waiting for a reconnect.
        api
          .chat({ session_id: sessionId, message: text })
          .then((resp) => onDone(resp))
          .catch((e) => onError(String(e?.detail ?? e)));
      }
    },
    [sessionId, send, onDone, onError],
  );

  const handleFeedback = useCallback(
    (movieId: number, signal: FeedbackSignal, sourceMessageId?: string) => {
      if (!sessionId) return;
      api
        .feedback({
          session_id: sessionId,
          movie_id: movieId,
          signal,
          source_message_id: sourceMessageId,
        })
        .catch(() => {
          // Silent — the user already saw their vote register locally;
          // we don't want to show an error for an implicit signal.
        });
    },
    [sessionId],
  );

  const handleNewChat = useCallback(() => {
    newSession();
    setMessages([]);
  }, [newSession]);

  // ── Layout ──────────────────────────────────────────
  return (
    <div className="flex h-screen w-full">
      <Sidebar wsStatus={status} onNewChat={handleNewChat} />
      <main className="flex flex-1 flex-col">
        <div className="flex-1 overflow-hidden">
          <MessageList messages={messages} onFeedback={handleFeedback} />
        </div>
        <ChatComposer onSend={handleSend} disabled={streaming} />
      </main>
    </div>
  );
}
