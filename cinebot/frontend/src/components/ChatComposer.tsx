/**
 * Message composer. Auto-growing textarea; Enter submits, Shift+Enter
 * inserts a newline. Disabled while the previous turn is still streaming
 * to avoid desynced state (the WS protocol is one-at-a-time).
 */

import {
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { Send } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

const MAX_HEIGHT = 180;

export function ChatComposer({ onSend, disabled, placeholder }: Props) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow up to MAX_HEIGHT, then scroll internally.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(MAX_HEIGHT, el.scrollHeight) + "px";
  }, [text]);

  const submit = useCallback(
    (e?: FormEvent) => {
      e?.preventDefault();
      const trimmed = text.trim();
      if (!trimmed || disabled) return;
      onSend(trimmed);
      setText("");
    },
    [text, disabled, onSend],
  );

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form
      onSubmit={submit}
      className="border-t border-border bg-background/80 px-6 py-4 backdrop-blur-md"
    >
      <div
        className={cn(
          "mx-auto flex max-w-3xl items-end gap-2 rounded-md border border-border bg-card px-3 py-2",
          "focus-within:border-accent focus-within:ring-1 focus-within:ring-accent/40",
          "transition-colors",
        )}
      >
        <textarea
          ref={textareaRef}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          placeholder={placeholder ?? "What are you in the mood for?"}
          disabled={disabled}
          maxLength={2000}
          className={cn(
            "flex-1 resize-none bg-transparent py-1.5 text-[15px] leading-relaxed",
            "placeholder:text-muted-foreground/70 focus:outline-none",
            "disabled:opacity-60",
          )}
          aria-label="Message CineBot"
        />
        <button
          type="submit"
          disabled={disabled || text.trim().length === 0}
          aria-label="Send message"
          className={cn(
            "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-sm",
            "bg-accent text-accent-foreground transition-opacity",
            "hover:opacity-90 disabled:opacity-40",
          )}
        >
          <Send className="h-3.5 w-3.5" />
        </button>
      </div>
      <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] uppercase tracking-[0.18em] text-muted-foreground/70">
        Enter to send · Shift + Enter for a new line
      </p>
    </form>
  );
}
