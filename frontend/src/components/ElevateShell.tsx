"use client";

import clsx from "clsx";
import {
  Bell,
  BookOpen,
  FileText,
  FileUp,
  LayoutGrid,
  LineChart,
  LogOut,
  Menu,
  Moon,
  MoreHorizontal,
  NotebookPen,
  Search,
  Sparkles,
  Sun,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAuth, useRequireAuth } from "@/lib/auth";

import { useTheme } from "./Providers";
import { Spinner } from "./ui";

type NavItem = { href: string; label: string; icon: typeof LayoutGrid; badge?: string };

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Overview", icon: LayoutGrid },
  { href: "/tests", label: "My tests", icon: FileText },
  { href: "/mistakes", label: "Mistake book", icon: NotebookPen },
  { href: "/history", label: "Analysis", icon: LineChart },
  { href: "/pyq", label: "PYQ library", icon: BookOpen, badge: "NEW" },
];
// Kept so admins never lose their way into the extraction queue, which is unchanged.
const ADMIN_NAV: NavItem[] = [{ href: "/admin", label: "PDF extraction", icon: FileUp }];

export function BrandMark() {
  return (
    <Link href="/dashboard" className="flex items-center gap-2.5">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand to-brand-2 text-base font-bold text-white shadow-[0_8px_18px_-8px_var(--brand)]">
        E
      </span>
      <span className="text-[17px] font-bold tracking-tight">ExamForge</span>
    </Link>
  );
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user } = useAuth();
  const items = [...NAV, ...(user?.role === "admin" ? ADMIN_NAV : [])];

  return (
    <nav className="space-y-1">
      {items.map(({ href, label, icon: Icon, badge }) => {
        const active = pathname === href || pathname.startsWith(href + "/");
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            className={clsx(
              "i-nav relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px]",
              active ? "font-semibold text-brand" : "font-medium text-muted hover:bg-sunken hover:text-fg",
            )}
          >
            {active && (
              <motion.span
                layoutId="elevate-nav-active"
                className="absolute inset-0 rounded-xl bg-brand-soft"
                transition={{ type: "spring", stiffness: 500, damping: 40 }}
              />
            )}
            <Icon className="relative h-[18px] w-[18px] shrink-0" />
            <span className="relative flex-1">{label}</span>
            {badge && (
              <span className="relative rounded-md bg-brand/10 px-1.5 py-0.5 text-[10px] font-bold tracking-wide text-brand">
                {badge}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

function HelpCard({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="rounded-2xl bg-brand-soft p-4">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-elev text-brand shadow-sm">
        <Sparkles className="h-[18px] w-[18px]" />
      </span>
      <p className="mt-3 text-sm font-semibold">Need a hand?</p>
      <p className="mt-1 text-[13px] leading-snug text-muted">
        Explore our quick guide to get the most out of ExamForge.
      </p>
      <Link
        href="/guide"
        onClick={onNavigate}
        className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-semibold text-brand transition-all hover:gap-2.5"
      >
        View guide <span aria-hidden>&rarr;</span>
      </Link>
    </div>
  );
}

/** Avatar + name, with the theme toggle and sign-out tucked into the overflow menu. */
function UserRow() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (!user) return null;
  return (
    <div ref={ref} className="relative flex items-center gap-3 px-1">
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-soft text-[13px] font-bold text-brand">
        {user.name.slice(0, 2).toUpperCase()}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">{user.name}</p>
        <p className="truncate text-xs text-subtle">{user.role === "admin" ? "Administrator" : "Aspirant"}</p>
      </div>
      <button
        aria-label="Account menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="grid h-8 w-8 place-items-center rounded-lg text-subtle transition hover:bg-sunken hover:text-fg"
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.97 }}
            transition={{ duration: 0.15 }}
            className="absolute bottom-full right-0 z-50 mb-2 w-44 overflow-hidden rounded-xl border border-line bg-elev p-1 shadow-card"
          >
            <button
              onClick={() => {
                toggle();
                setOpen(false);
              }}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted transition hover:bg-sunken hover:text-fg"
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              {theme === "dark" ? "Light mode" : "Dark mode"}
            </button>
            <button
              onClick={() => {
                logout();
                router.push("/login");
              }}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted transition hover:bg-sunken hover:text-danger"
            >
              <LogOut className="h-4 w-4" /> Sign out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      <div className="flex-1 overflow-y-auto">
        <NavList onNavigate={onNavigate} />
      </div>
      <div className="space-y-4 pt-4">
        <HelpCard onNavigate={onNavigate} />
        <UserRow />
      </div>
    </>
  );
}

/** Search box in the top bar. Routes into the PYQ library, which owns the real search. */
function TopSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        router.push(q.trim() ? `/pyq?q=${encodeURIComponent(q.trim())}` : "/pyq");
      }}
      className="relative w-full max-w-md"
    >
      <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
      <input
        ref={ref}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search tests, subjects, PYQs…"
        aria-label="Search"
        className="h-11 w-full rounded-xl border border-line bg-elev pl-10 pr-16 text-sm text-fg outline-none transition-all duration-200 placeholder:text-subtle focus:border-brand focus:ring-4 focus:ring-brand/12"
      />
      <kbd className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 items-center gap-0.5 rounded-md border border-line px-1.5 py-0.5 text-[10px] font-medium text-subtle sm:flex">
        <span className="text-[11px]">&#8984;</span> K
      </kbd>
    </form>
  );
}

export function ElevateShell({ children, admin }: { children: React.ReactNode; admin?: boolean }) {
  const { ready } = useRequireAuth(admin ? "admin" : undefined);
  const { user } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[264px] flex-col border-r border-line bg-elev px-4 py-5 xl:flex">
        <div className="mb-7 px-1">
          <BrandMark />
        </div>
        <SidebarBody />
      </aside>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm xl:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
            />
            <motion.aside
              className="fixed inset-y-0 left-0 z-50 flex w-[280px] flex-col bg-elev px-4 py-5 shadow-2xl xl:hidden"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 380, damping: 38 }}
            >
              <div className="mb-7 flex items-center justify-between px-1">
                <BrandMark />
                <button
                  aria-label="Close menu"
                  onClick={() => setOpen(false)}
                  className="grid h-9 w-9 place-items-center rounded-xl text-muted hover:bg-sunken"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <SidebarBody onNavigate={() => setOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <div className="xl:pl-[264px]">
        <header className="sticky top-0 z-20 flex h-[76px] items-center gap-3 border-b border-line bg-bg/85 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
          <button
            aria-label="Open menu"
            onClick={() => setOpen(true)}
            className="grid h-10 w-10 shrink-0 place-items-center rounded-xl text-muted hover:bg-sunken xl:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>
          <TopSearch />
          <div className="ml-auto flex items-center gap-2">
            <Link
              href="/history"
              aria-label="Notifications"
              className="grid h-10 w-10 place-items-center rounded-xl border border-line bg-elev text-muted transition hover:text-fg"
            >
              <Bell className="h-[18px] w-[18px]" />
            </Link>
            <div className="grid h-10 w-10 place-items-center rounded-full bg-brand-soft text-[13px] font-bold text-brand">
              {(user?.name ?? "··").slice(0, 2).toUpperCase()}
            </div>
          </div>
        </header>

        <main className="px-4 py-7 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-[1180px]">
            {ready ? (
              // `key` restarts the CSS animation on every route change.
              <div key={pathname} className="animate-rise">
                {children}
              </div>
            ) : (
              <div className="grid min-h-[50vh] place-items-center">
                <Spinner />
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
