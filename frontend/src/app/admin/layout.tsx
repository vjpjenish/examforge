import { ElevateShell } from "@/components/ElevateShell";

export default function Layout({ children }: { children: React.ReactNode }) {
  return <ElevateShell admin>{children}</ElevateShell>;
}
