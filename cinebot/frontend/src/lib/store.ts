/**
 * Global client state: auth + current session.
 *
 * Message history lives per-component (useState) — we don't want it in the
 * store since it's ephemeral. Session id is persisted so refresh resumes
 * the conversation.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api, clearTokens, getTokens } from "@/lib/api";

type AuthStatus = "unknown" | "signed_in" | "signed_out";

interface Store {
  authStatus: AuthStatus;
  email: string | null;
  sessionId: string | null;

  // setters
  setAuth: (email: string) => void;
  signOut: () => void;
  setSessionId: (id: string | null) => void;
  newSession: () => void;

  // actions
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
}

export const useStore = create<Store>()(
  persist(
    (set) => ({
      authStatus: getTokens() ? "signed_in" : "signed_out",
      email: null,
      sessionId: null,

      setAuth: (email) => set({ authStatus: "signed_in", email }),
      signOut: () => {
        clearTokens();
        set({ authStatus: "signed_out", email: null, sessionId: null });
      },
      setSessionId: (id) => set({ sessionId: id }),
      newSession: () => set({ sessionId: null }),

      login: async (email, password) => {
        await api.login(email, password);
        set({ authStatus: "signed_in", email, sessionId: null });
      },
      register: async (email, password, display_name) => {
        await api.register(email, password, display_name);
        await api.login(email, password);
        set({ authStatus: "signed_in", email, sessionId: null });
      },
    }),
    {
      name: "cinebot.store",
      partialize: (s) => ({ email: s.email, sessionId: s.sessionId }),
    },
  ),
);
