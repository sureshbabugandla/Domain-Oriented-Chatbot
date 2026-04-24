/**
 * A single movie recommendation. Layout intent:
 *   ┌──────────────┬────────────────────────────┐
 *   │              │  TITLE (serif display)     │
 *   │    poster    │  year · score chip         │
 *   │    (2:3)     │                            │
 *   │              │  reasons bullets           │
 *   │              │                            │
 *   └──────────────┤  [👍]  [👎]                │
 *                  └────────────────────────────┘
 *
 * On hover, the poster does a subtle scale-up. Amber accent denotes rank.
 */

import { useState } from "react";
import { ThumbsUp, ThumbsDown, Star, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FeedbackSignal, RecommendationCard as Card } from "@/types/api";

interface Props {
  card: Card;
  rank: number;
  onFeedback: (movieId: number, signal: FeedbackSignal) => void;
}

export function RecommendationCard({ card, rank, onFeedback }: Props) {
  const [voted, setVoted] = useState<null | "like" | "dislike">(null);
  const vote = (signal: FeedbackSignal) => {
    if (signal === "like" || signal === "dislike") {
      setVoted(signal);
    }
    onFeedback(card.movie_id, signal);
  };

  return (
    <article
      className={cn(
        "group relative flex gap-4 overflow-hidden rounded-md border border-border bg-card/80 p-3",
        "backdrop-blur-sm transition-all hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-lg",
      )}
    >
      {/* Rank marker — marquee amber */}
      <span
        aria-hidden
        className="absolute left-0 top-0 flex h-7 w-8 items-center justify-center rounded-br-md bg-accent text-[13px] font-medium tracking-wide text-accent-foreground"
      >
        {rank.toString().padStart(2, "0")}
      </span>

      {/* Poster */}
      <div className="relative h-36 w-24 flex-shrink-0 overflow-hidden rounded-sm bg-muted">
        {card.poster_url ? (
          <img
            src={card.poster_url}
            alt={`${card.title} poster`}
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
            no poster
          </div>
        )}
      </div>

      {/* Body */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="mb-1 pr-2 pt-1">
          <h3 className="font-display text-lg leading-tight tracking-tight">
            {card.title}
          </h3>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            {card.year && <span className="font-mono">{card.year}</span>}
            <span
              className="inline-flex items-center gap-1 rounded-sm bg-accent/15 px-1.5 py-0.5 text-accent"
              title="blended relevance score"
            >
              <Star className="h-3 w-3" />
              {card.score.toFixed(2)}
            </span>
          </div>
        </header>

        <ul className="mt-1 flex-1 space-y-0.5 text-sm text-foreground/80">
          {card.reasons.slice(0, 3).map((r, i) => (
            <li
              key={i}
              className="before:mr-2 before:text-accent before:content-['—']"
            >
              {r}
            </li>
          ))}
        </ul>

        <footer className="mt-2 flex items-center gap-2 border-t border-border pt-2">
          <button
            type="button"
            onClick={() => vote("like")}
            disabled={voted !== null}
            aria-label={`Like ${card.title}`}
            className={cn(
              "inline-flex h-7 w-7 items-center justify-center rounded-sm border border-border",
              "transition-colors hover:border-accent hover:text-accent",
              "disabled:cursor-default disabled:opacity-60",
              voted === "like" && "border-accent bg-accent/10 text-accent",
            )}
          >
            {voted === "like" ? (
              <Check className="h-3.5 w-3.5" />
            ) : (
              <ThumbsUp className="h-3.5 w-3.5" />
            )}
          </button>
          <button
            type="button"
            onClick={() => vote("dislike")}
            disabled={voted !== null}
            aria-label={`Dislike ${card.title}`}
            className={cn(
              "inline-flex h-7 w-7 items-center justify-center rounded-sm border border-border",
              "transition-colors hover:border-destructive hover:text-destructive",
              "disabled:cursor-default disabled:opacity-60",
              voted === "dislike" && "border-destructive bg-destructive/10 text-destructive",
            )}
          >
            <ThumbsDown className="h-3.5 w-3.5" />
          </button>
          <span className="ml-auto text-[11px] uppercase tracking-widest text-muted-foreground">
            rec #{rank}
          </span>
        </footer>
      </div>
    </article>
  );
}
