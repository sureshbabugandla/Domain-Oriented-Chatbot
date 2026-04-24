import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Intent label → a one-word display string. */
export const intentLabels: Record<string, string> = {
  greet: "greeting",
  recommend: "recommendation",
  refine: "refinement",
  feedback: "feedback",
  more_info: "info request",
  goodbye: "goodbye",
  oos: "off-topic",
};
