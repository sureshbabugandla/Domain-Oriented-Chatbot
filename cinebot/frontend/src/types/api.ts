// Wire-format types. Kept in sync with backend/app/api/schemas.py.
// If the backend adds a field, update this file before the UI uses it.

export type Intent =
  | "greet"
  | "recommend"
  | "refine"
  | "feedback"
  | "more_info"
  | "goodbye"
  | "oos";

export interface RecommendationCard {
  movie_id: number;
  title: string;
  year: number | null;
  poster_url: string | null;
  score: number;
  reasons: string[];
  rendered: string;
}

export interface ChatResponse {
  session_id: string;
  turn: number;
  intent: Intent;
  intent_confidence: number;
  text: string;
  recommendations: RecommendationCard[];
}

export interface ChatRequest {
  session_id: string | null;
  message: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserPublic {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
}

// Client-side message model — includes UI-only fields like `pending`.
export interface UIMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  recommendations?: RecommendationCard[];
  pending?: boolean;
  createdAt: number;
}

export type FeedbackSignal = "like" | "dislike" | "click" | "dismiss";
