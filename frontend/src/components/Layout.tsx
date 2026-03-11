import type { ReactNode } from "react";
import { Link as RouterLink, useLocation } from "react-router-dom";

const nav = [
  { to: "/", label: "Dashboard" },
  { to: "/builds", label: "Builds" },
  { to: "/devices", label: "Devices" },
  { to: "/profiles", label: "Profiles" },
];

export function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white py-3">
        <div className="mx-auto max-w-6xl px-4 flex items-center gap-6">
          <RouterLink to="/" className="font-bold text-lg text-gray-900 no-underline">
            Cook IPA
          </RouterLink>
          <nav className="flex gap-4">
            {nav.map(({ to, label }) => {
              const active = location.pathname === to || (to !== "/" && location.pathname.startsWith(to));
              return (
                <RouterLink
                  key={to}
                  to={to}
                  className={`no-underline ${active ? "font-semibold text-blue-600" : "text-gray-700 hover:text-blue-600"}`}
                >
                  {label}
                </RouterLink>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}
