/**
 * Auth page — single form with a tab toggle between login and register.
 * Minimal validation client-side; the backend owns the real rules and
 * we surface whatever error string it returns.
 */

import { type FormEvent, useState } from "react";
import { Film } from "lucide-react";
import { useStore } from "@/lib/store";
import { Sprocket } from "@/components/Sprocket";
import { cn } from "@/lib/utils";

type Mode = "login" | "register";

export function AuthPage() {
  const { login, register } = useStore();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, name || undefined);
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message.replace(/^\d+:\s*/, "") : "Unknown error";
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen w-full grid-cols-1 md:grid-cols-[1.1fr_1fr]">
      {/* Left: hero panel */}
      <div className="relative hidden flex-col justify-between overflow-hidden bg-card/60 p-12 md:flex">
        {/* Marquee accent strip */}
        <div className="absolute inset-y-0 left-0 w-1 bg-accent" aria-hidden />
        <div>
          <div className="flex items-center gap-2">
            <Film className="h-5 w-5 text-accent" strokeWidth={1.5} />
            <span className="font-display text-2xl tracking-tight">CineBot</span>
          </div>
          <Sprocket count={30} className="mt-6" />
        </div>
        <figure className="max-w-md">
          <blockquote className="font-display text-4xl leading-tight tracking-tight">
            "Tell me how you're feeling, and I'll find you a film."
          </blockquote>
          <figcaption className="mt-4 text-sm uppercase tracking-[0.22em] text-muted-foreground">
            — your new movie concierge
          </figcaption>
        </figure>
        <Sprocket count={30} className="opacity-50" />
      </div>

      {/* Right: form */}
      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <h1 className="font-display text-3xl tracking-tight">
            {mode === "login" ? "Welcome back" : "Make yourself at home"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {mode === "login"
              ? "Pick up where you left off."
              : "A quick account so I can remember your tastes."}
          </p>

          {/* Mode toggle */}
          <div className="mt-6 inline-flex rounded-sm border border-border p-0.5">
            {(["login", "register"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={cn(
                  "px-3 py-1 text-xs uppercase tracking-[0.16em]",
                  mode === m
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {m === "login" ? "Sign in" : "Create"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
            {mode === "register" && (
              <Field
                label="Display name"
                type="text"
                value={name}
                onChange={setName}
                autoComplete="name"
                placeholder="optional"
              />
            )}
            <Field
              label="Email"
              type="email"
              value={email}
              onChange={setEmail}
              autoComplete="email"
              required
            />
            <Field
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={mode === "register" ? 8 : undefined}
              required
            />

            {error && (
              <p
                className="rounded-sm border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                role="alert"
              >
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className={cn(
                "w-full rounded-sm bg-accent px-3 py-2.5 text-sm font-medium text-accent-foreground",
                "transition-opacity hover:opacity-90 disabled:opacity-60",
              )}
            >
              {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function Field(props: {
  label: string;
  type: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  placeholder?: string;
  required?: boolean;
  minLength?: number;
}) {
  const id = `f-${props.label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <label htmlFor={id} className="block">
      <span className="mb-1 block text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
        {props.label}
      </span>
      <input
        id={id}
        type={props.type}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        autoComplete={props.autoComplete}
        placeholder={props.placeholder}
        required={props.required}
        minLength={props.minLength}
        className={cn(
          "w-full rounded-sm border border-border bg-background px-3 py-2 text-sm",
          "focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40",
        )}
      />
    </label>
  );
}
