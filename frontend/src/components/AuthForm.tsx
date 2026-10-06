"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/lib/auth";

import { Logo } from "./AppShell";
import { Button, Card, ErrorNote, Field, Input } from "./ui";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user =
        mode === "login" ? await login(form.email, form.password) : await register(form.name, form.email, form.password);
      const next = params.get("next");
      router.replace(next && next.startsWith("/") ? next : user.role === "admin" ? "/admin" : "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setBusy(false);
    }
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden px-4">
      <div className="bg-grid pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute -top-32 left-1/2 h-96 w-[700px] -translate-x-1/2 rounded-full bg-gradient-to-r from-brand/20 to-brand-2/20 blur-3xl" />
      <motion.div
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className="relative w-full max-w-md"
      >
        <div className="mb-8 flex justify-center">
          <Logo />
        </div>
        <Card className="p-8">
          <h1 className="text-xl font-semibold tracking-tight">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
          <p className="mt-1 text-sm text-muted">
            {mode === "login" ? "Sign in to continue your preparation." : "Start practising with AI-built tests."}
          </p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            {mode === "register" && (
              <Field label="Full name">
                <Input required value={form.name} onChange={set("name")} placeholder="Aarav Sharma" autoComplete="name" />
              </Field>
            )}
            <Field label="Email">
              <Input required type="email" value={form.email} onChange={set("email")} placeholder="you@example.com" autoComplete="email" />
            </Field>
            <Field label="Password" hint={mode === "register" ? "At least 8 characters" : undefined}>
              <Input
                required
                type="password"
                minLength={mode === "register" ? 8 : undefined}
                value={form.password}
                onChange={set("password")}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </Field>
            {error && <ErrorNote message={error} />}
            <Button type="submit" loading={busy} className="w-full">
              {mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>
        </Card>
        <p className="mt-6 text-center text-sm text-muted">
          {mode === "login" ? "New here? " : "Already have an account? "}
          <Link href={mode === "login" ? "/register" : "/login"} className="font-medium text-brand hover:underline">
            {mode === "login" ? "Create an account" : "Sign in"}
          </Link>
        </p>
      </motion.div>
    </div>
  );
}
