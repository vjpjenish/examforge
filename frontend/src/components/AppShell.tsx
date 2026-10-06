"use client";

import clsx from "clsx";
import {
  BookOpenCheck,
  ClipboardList,
  FileUp,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Sparkles,
  Sun,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth, useRequireAuth } from "@/lib/auth";

import { useTheme } from "./Providers";
import { Spinner } from "./ui";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/tests", label: "Test series", icon: ClipboardList },
  { href: "/pyq", label: "PYQ bank", icon: BookOpenCheck },
  { href: "/history", label: "History", icon: History },
];
const ADMIN_NAV = [{ href: "/admin", label: "PDF extraction", icon: FileUp }];

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="grid h-8 w-8 place-items-center rounded-xl bg-gradient-to-br from-brand to-brand-2 text-white shadow-[0_6px_16px_-6px_var(--brand)]">
        <Sparkles className="h-4 w-4" />
      </span>
      <span className="text-lg">ExamForge</span>
    </Link>
  );
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      aria-label="Toggle theme"
      className="grid h-9 w-9 place-items-center rounded-xl text-muted transition hover:bg-sunken hover:text-fg"
    >
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user } = useAuth();
  const groups = [{ title: "Learn", items: NAV }, ...(user?.role === "admin" ? [{ title: "Admin", items: ADMIN_NAV }] : [])];
  return (
    <nav className="space-y-6">
      {groups.map((g) => (
        <div key={g.title}>
          <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-subtle">{g.title}</p>
          <div className="space-y-1">
            {g.items.map(({ href, label, icon: Icon }) => {
              const active = pathname === href || pathname.startsWith(href + "/");
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={onNavigate}
                  className={clsx(
                    "relative flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors",
                    active ? "text-fg" : "text-muted hover:bg-sunken hover:text-fg",
                  )}
                >
                  {active && (
                    <motion.span
                      layoutId="nav-active"
                      className="absolute inset-0 rounded-xl bg-brand-soft"
                      transition={{ type: "spring", stiffness: 500, damping: 40 }}
                    />
                  )}
                  <Icon className={clsx("relative h-4 w-4", active && "text-brand")} />
                  <span className="relative">{label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}

function UserFooter() {
  const { user, logout } = useAuth();
  const router = useRouter();
  if (!user) return null;
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line p-3">
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand to-brand-2 text-sm font-semibold text-white">
        {user.name.slice(0, 1).toUpperCase()}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{user.name}</p>
        <p className="truncate text-xs text-subtle">{user.role === "admin" ? "Administrator" : user.email}</p>
      </div>
      <button
        aria-label="Sign out"
        onClick={() => {
          logout();
          router.push("/login");
        }}
        className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-sunken hover:text-fg"
      >
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  );
}

export function AppShell({ children, admin }: { children: React.ReactNode; admin?: boolean }) {
  const { ready } = useRequireAuth(admin ? "admin" : undefined);
  const [open, setOpen] = useState(false);

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-line bg-elev/70 px-4 py-5 backdrop-blur-xl lg:flex">
        <div className="mb-8 flex items-center justify-between px-1">
          <Logo />
          <ThemeToggle />
        </div>
        <div className="flex-1">
          <NavLinks />
        </div>
        <UserFooter />
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-bg/80 px-4 backdrop-blur-xl lg:hidden">
        <Logo />
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <button
            aria-label="Open menu"
            onClick={() => setOpen(true)}
            className="grid h-9 w-9 place-items-center rounded-xl hover:bg-sunken"
          >
            <Menu className="h-5 w-5" />
          </button>
        </div>
      </header>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
            />
            <motion.aside
              className="fixed inset-y-0 right-0 z-50 flex w-72 flex-col bg-elev px-4 py-5 shadow-2xl lg:hidden"
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", stiffness: 380, damping: 38 }}
            >
              <div className="mb-8 flex items-center justify-between">
                <Logo />
                <button aria-label="Close menu" onClick={() => setOpen(false)} className="grid h-9 w-9 place-items-center rounded-xl hover:bg-sunken">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="flex-1">
                <NavLinks onNavigate={() => setOpen(false)} />
              </div>
              <UserFooter />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <main className="lg:pl-64">
        <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-10 lg:py-10">
          {ready ? (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
              {children}
            </motion.div>
          ) : (
            <div className="grid min-h-[50vh] place-items-center">
              <Spinner />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
