"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

const NAV = [
  { href: "/dashboard",   label: "Dashboard" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/matches",     label: "Matches" },
  { href: "/referrals",   label: "Referrals" },
];

export default function NavBar({ displayName }: { displayName?: string }) {
  const pathname = usePathname();
  const router   = useRouter();

  async function signOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/");
  }

  return (
    <nav className="border-b border-[#1e1e1e] bg-[#0a0a0a] sticky top-0 z-50">
      <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link href="/dashboard" className="text-white font-bold text-lg">♠ Fullhouse</Link>
          <div className="hidden sm:flex items-center gap-1">
            {NAV.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                  pathname === href
                    ? "text-white bg-[#1a1a1a]"
                    : "text-[#666] hover:text-[#aaa] hover:bg-[#151515]"
                }`}
              >
                {label}
              </Link>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {displayName && (
            <span className="text-xs text-[#555] hidden sm:block">{displayName}</span>
          )}
          <button
            onClick={signOut}
            className="text-xs text-[#555] hover:text-[#888] transition-colors"
          >
            Sign out
          </button>
        </div>
      </div>
    </nav>
  );
}
