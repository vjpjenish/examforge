"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, getToken, setToken, type User } from "./api";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (name: string, email: string, password: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  // Only "loading" while a stored token is being validated.
  const [loading, setLoading] = useState(() => typeof window !== "undefined" && !!getToken());

  useEffect(() => {
    if (!getToken()) return;
    api<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  const finish = useCallback((res: { token: string; user: User }) => {
    setToken(res.token);
    setUser(res.user);
    return res.user;
  }, []);

  const login = useCallback(
    (email: string, password: string) =>
      api<{ token: string; user: User }>("/api/auth/login", { method: "POST", json: { email, password } }).then(finish),
    [finish],
  );
  const register = useCallback(
    (name: string, email: string, password: string) =>
      api<{ token: string; user: User }>("/api/auth/register", { method: "POST", json: { name, email, password } }).then(
        finish,
      ),
    [finish],
  );
  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, loading, login, register, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** Redirects to /login when signed out (and to /dashboard when a student opens an admin page). */
export function useRequireAuth(role?: "admin") {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (loading) return;
    if (!user) router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    else if (role === "admin" && user.role !== "admin") router.replace("/dashboard");
  }, [user, loading, role, router]);
  return { user, ready: !loading && !!user && (role !== "admin" || user.role === "admin") };
}
