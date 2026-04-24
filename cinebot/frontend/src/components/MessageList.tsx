/**
 * Chat transcript. Renders a scrolling column of alternating user /
 * assistant bubbles. Assistant messages may embed a slate of
 * recommendation cards beneath the text.
 *
 * The transcript auto-scrolls to bottom on new content, but only when
 * the user is already near the bottom — we don't rip them away from
 * reading older messages.
 */

import { useEffect, useRef } from "react";
import { RecommendationCard } from "./RecommendationCard";
import { Sprocket } from "./Sprocket";
import { cn } from "@/lib/utils";
import type { FeedbackSignal, UIMessage } from "@/types/api";

interface Props {
  messages: UIMessage[];
  onFeedback: (
    movieId: number,
    signal: FeedbackSignal,
    sourceMessageId?: string,
  ) => void;
}

const NEAR_BOTTOM_PX = 120;

export function MessageList({ messages, onFeedback }: Props) {
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const distanceFromBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom < NEAR_BOTTOM_PX) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div
        ref={scrollerRef}
        className="flex h-full items-center justify-center px-6"
      >
        <EmptyState />
      </div>
    );
  }

  return (
    <div
      ref={scrollerRef}
      className="h-full overflow-y-auto px-6 py-8"
      aria-live="polite"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-6">
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} onFeedback={onFeedback} />
        ))}
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  onFeedback,
}: {
  message: UIMessage;
  onFeedback: Props["onFeedback"];
}) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        "message-in flex flex-col gap-3",
        isUser ? "items-end" : "items-start",
      )}
    >
      <div
        className={cn(
          "max-w-[85%] rounded-md px-4 py-3 text-[15px] leading-relaxed",
          isUser
            ? "rounded-br-sm bg-accent/90 text-accent-foreground"
            : "rounded-bl-sm border border-border bg-card",
        )}
      >
        {message.pending && message.content === "" ? (
          <TypingIndicator />
        ) : (
          <p className="whitespace-pre-wrap">{message.content}</p>
        )}
      </div>

      {message.recommendations && message.recommendations.length > 0 && (
        <div className="w-full max-w-3xl">
          <div className="mb-3 flex items-center gap-3">
            <span className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
              Tonight's reel
            </span>
            <Sprocket className="flex-1" count={48} />
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {message.recommendations.map((card, idx) => (
              <RecommendationCard
                key={card.movie_id}
                card={card}
                rank={idx + 1}
                onFeedback={(id, sig) => onFeedback(id, sig, message.id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TypingIndicator() {
  return (
    <span className="inline-flex items-center gap-1 text-muted-foreground">
      <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
      <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
      <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
    </span>
  );
}

function EmptyState() {
  const suggestions = [
    "Feel-good comedy from the 90s",
    "Something tense under 100 minutes",
    "A weird indie sci-fi I've never heard of",
    "Cozy Sunday-afternoon rewatch",
  ];
  return (
    <div className="flex max-w-xl flex-col items-center text-center">
      <Sprocket count={32} className="mb-5" />
      <h1 className="font-display text-4xl tracking-tight md:text-5xl">
        What are we watching?
      </h1>
      <p className="mt-3 text-muted-foreground">
        Tell me a mood, a genre, a decade — even just the last film you loved.
        I'll find five picks and explain why.
      </p>
      <ul className="mt-6 flex flex-wrap justify-center gap-2">
        {suggestions.map((s) => (
          <li
            key={s}
            className="rounded-sm border border-border bg-card px-3 py-1.5 text-sm text-muted-foreground"
          >
            "{s}"
          </li>
        ))}
      </ul>
    </div>
  );
}
