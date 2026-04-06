"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export default function OnboardingPage() {
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [botName, setBotName]         = useState("");
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const supabase = createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) { router.push("/"); return; }

    const { error } = await supabase
      .from("users")
      .upsert({ id: user.id, email: user.email!, display_name: displayName.trim() });

    if (error) { setError(error.message); setLoading(false); return; }

    // Pre-create empty bot record
    if (botName.trim()) {
      await supabase.from("bots").upsert({
        user_id:      user.id,
        bot_name:     botName.trim(),
        storage_path: "",
        status:       "pending",
      });
    }

    router.push("/dashboard");
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-10">
          <div className="text-4xl mb-4">♠</div>
          <h1 className="text-2xl font-bold text-white">Welcome to Fullhouse</h1>
          <p className="text-sm text-[#666] mt-1">Set up your participant profile</p>
        </div>

        <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-8">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-xs text-[#666] mb-1.5 uppercase tracking-wide">
                Your name
              </label>
              <input
                type="text"
                required
                value={displayName}
                onChange={e => setDisplayName(e.target.value)}
                placeholder="Ozan Kardes"
                maxLength={60}
                className="w-full bg-[#0a0a0a] border border-[#2a2a2a] rounded-lg px-4 py-3 text-white text-sm placeholder-[#444] focus:outline-none focus:border-[#555] transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs text-[#666] mb-1.5 uppercase tracking-wide">
                Bot name
              </label>
              <input
                type="text"
                required
                value={botName}
                onChange={e => setBotName(e.target.value)}
                placeholder="TheSharknado"
                maxLength={32}
                minLength={2}
                className="w-full bg-[#0a0a0a] border border-[#2a2a2a] rounded-lg px-4 py-3 text-white text-sm placeholder-[#444] focus:outline-none focus:border-[#555] transition-colors"
              />
              <p className="text-xs text-[#444] mt-1.5">2–32 characters. This is how your bot appears on the leaderboard.</p>
            </div>
            {error && (
              <p className="text-xs text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-3">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={loading || !displayName.trim() || !botName.trim()}
              className="w-full bg-white text-black font-semibold text-sm py-3 rounded-lg hover:bg-[#e5e5e5] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {loading ? "Setting up…" : "Enter the arena →"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
