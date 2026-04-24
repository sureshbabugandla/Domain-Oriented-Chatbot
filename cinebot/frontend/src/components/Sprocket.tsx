/**
 * Sprocket — decorative film-strip holes. Draws a row of rounded
 * rectangles in the accent colour. Use as a thin divider beneath headers
 * or along card edges for cinematic flavour.
 */

import { cn } from "@/lib/utils";

interface Props {
  className?: string;
  /** number of holes; defaults to enough to fill its container at 14px each */
  count?: number;
  direction?: "horizontal" | "vertical";
}

export function Sprocket({ className, count = 24, direction = "horizontal" }: Props) {
  const holes = Array.from({ length: count });
  return (
    <div
      aria-hidden
      className={cn(
        "flex gap-[6px] opacity-40",
        direction === "horizontal" ? "flex-row" : "flex-col",
        className,
      )}
    >
      {holes.map((_, i) => (
        <span
          key={i}
          className="h-2 w-3 rounded-[1px] bg-muted-foreground/60"
        />
      ))}
    </div>
  );
}
