import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import NavBar from "@/components/NavBar";
import BotUploader from "@/components/BotUploader";
import { CharacterPickerForCurrentUser } from "@/components/CharacterPicker";
import { SUBMISSIONS_OPEN, SUBMISSIONS_OPEN_DATE_LABEL, FINALISTS } from "@/lib/portal-state";

export default async function DashboardPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/");

  const [{ data: profile }, { data: bot }, { data: reg }] = await Promise.all([
    supabase.from("users").select("display_name").eq("id", user.id).single(),
    supabase.from("bots").select("*").eq("user_id", user.id).maybeSingle(),
    supabase.from("registrations").select("referral_code, referred_by").eq("email", user.email!).maybeSingle(),
  ]);

  const displayName = profile?.display_name ?? user.email!;

  const statusColors: Record<string, string> = {
    pending:    "text-[#888] bg-[#888]/10 border-[#888]/20",
    validating: "text-yellow-400 bg-yellow-400/10 border-yellow-400/20",
    ready:      "text-green-400 bg-green-400/10 border-green-400/20",
    error:      "text-red-400 bg-red-400/10 border-red-400/20",
    disqualified: "text-red-500 bg-red-500/10 border-red-500/20",
  };
  const status = bot?.status ?? "pending";
  const statusClass = statusColors[status] ?? statusColors.pending;

  return (
    <>
      <NavBar displayName={displayName} />
      <main className="max-w-5xl mx-auto px-4 py-10">

        <div className="mb-10">
          <h1 className="text-2xl font-bold text-white">
            Welcome back, {displayName.split(" ")[0]} 👋
          </h1>
          <p className="text-[#666] text-sm mt-1">
            Fullhouse Hackathon · 1 June 2026 · Online qualifier
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          <div className="lg:col-span-2 space-y-6">

            {/* Character picker */}
            <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-6">
              <h2 className="text-base font-semibold text-white mb-1">Your character</h2>
              <p className="text-sm text-[#666] mb-5">
                Pick a robot and a hat — shown next to your bot on the leaderboard and match replays. Saves automatically.
              </p>
              <CharacterPickerForCurrentUser />
            </div>

            {bot && bot.storage_path && (
              <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <p className="text-xs text-[#666] uppercase tracking-wide mb-1">Current bot</p>
                    <h2 className="text-lg font-semibold text-white">{bot.bot_name}</h2>
                  </div>
                  <span className={`text-xs font-medium px-3 py-1 rounded-full border ${statusClass}`}>
                    {status}
                  </span>
                </div>
                {bot.status === "error" && bot.error_message && (
                  <div className="bg-red-400/5 border border-red-400/20 rounded-lg p-4 mt-3">
                    <p className="text-xs text-red-400 font-medium mb-1">Validation failed</p>
                    <pre className="text-xs text-red-300 whitespace-pre-wrap font-mono">
                      {bot.error_message}
                    </pre>
                  </div>
                )}
                {bot.status === "ready" && (
                  <p className="text-xs text-green-400 mt-2">
                    ✓ Bot validated and ready for the tournament.
                  </p>
                )}
                <p className="text-xs text-[#444] mt-3">
                  Version {bot.version} · Submitted {new Date(bot.submitted_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                </p>
              </div>
            )}

            <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-6">
              <h2 className="text-base font-semibold text-white mb-1">
                {SUBMISSIONS_OPEN ? (bot?.storage_path ? "Update your bot" : "Submit your bot") : "Bot submissions"}
              </h2>
              <p className="text-sm text-[#666] mb-6">
                {SUBMISSIONS_OPEN
                  ? <>Upload a single <code className="text-[#888] bg-[#1a1a1a] px-1.5 py-0.5 rounded text-xs">bot.py</code> file. It must contain a <code className="text-[#888] bg-[#1a1a1a] px-1.5 py-0.5 rounded text-xs">decide(state)</code> function. Validation runs automatically.</>
                  : <>The submission window opens in {SUBMISSIONS_OPEN_DATE_LABEL}. We&apos;ll email everyone the moment it&apos;s live.</>}
              </p>
              <BotUploader
                userId={user.id}
                existingBot={bot && bot.storage_path ? bot : undefined}
              />
            </div>

            <div className="bg-[#0f0f0f] border border-[#1a1a1a] rounded-xl p-6">
              <h3 className="text-sm font-semibold text-white mb-3">Submission rules</h3>
              <ul className="space-y-2 text-sm text-[#666]">
                {[
                  "One file: bot.py with a decide(game_state) → dict function",
                  "2 seconds max to return an action or your bot auto-folds",
                  "No network calls, no file I/O",
                  "Available: eval7, numpy, scipy (request others in advance)",
                  "256 MB RAM · 0.5 CPU core · Docker isolated",
                  "Crashes auto-fold for that hand — bot stays in tournament",
                ].map(rule => (
                  <li key={rule} className="flex gap-2">
                    <span className="text-[#333] mt-0.5">–</span>
                    <span>{rule}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="space-y-4">

            <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-5">
              <p className="text-xs text-[#666] uppercase tracking-wide mb-3">Event</p>
              <div className="text-2xl font-bold text-white mb-1">1 June 2026</div>
              <p className="text-xs text-[#555]">Online · Finals 5 Jun at UCL East</p>
              <div className="mt-4 pt-4 border-t border-[#1e1e1e]">
                <div className="flex justify-between text-xs text-[#555] mb-2">
                  <span>Prize pool</span>
                  <span className="text-white font-medium">£4,000</span>
                </div>
                <div className="flex justify-between text-xs text-[#555]">
                  <span>Lead sponsor</span>
                  <span className="text-white font-medium">Quadrature Capital</span>
                </div>
              </div>
            </div>

            <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-5">
              <p className="text-xs text-[#666] uppercase tracking-wide mb-4">Tournament</p>
              <div className="space-y-3">
                {[
                  { day: "1 Jun", desc: `Swiss qualifier · top ${FINALISTS} advance` },
                  { day: "2 Jun", desc: "Patch window · update your bot" },
                  { day: "5 Jun", desc: "Finals night · UCL East · £4,000 prize" },
                ].map(({ day, desc }) => (
                  <div key={day} className="flex gap-3">
                    <span className="text-xs text-[#444] w-10 pt-0.5 shrink-0">{day}</span>
                    <span className="text-xs text-[#888]">{desc}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-5">
              <p className="text-xs text-[#666] uppercase tracking-wide mb-3">Resources</p>
              <div className="space-y-2">
                {[
                  { label: "Engine README", href: "https://github.com/uzlez/fullhouse-engine" },
                  { label: "Bot template", href: "https://github.com/uzlez/fullhouse-engine/blob/main/bots/template/bot.py" },
                  { label: "Rules & format", href: "https://fullhousehackathon.com" },
                ].map(({ label, href }) => (
                  <a
                    key={label}
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-between text-xs text-[#666] hover:text-white transition-colors py-0.5"
                  >
                    <span>{label}</span>
                    <span className="text-[#333]">↗</span>
                  </a>
                ))}
              </div>
            </div>

            {reg?.referral_code && (
              <div className="bg-[#0f1a0f] border border-[#1a3a1a] rounded-xl p-5">
                <p className="text-xs text-[#4a9a4a] uppercase tracking-wide mb-3">Your referral link</p>
                <code className="text-xs text-[#4a9a4a] break-all">
                  tally.so/r/b5OREg?ref={reg.referral_code}
                </code>
                <a
                  href="/referrals"
                  className="block text-xs text-[#444] hover:text-[#888] mt-3 transition-colors"
                >
                  View referrals →
                </a>
              </div>
            )}
          </div>
        </div>
      </main>
    </>
  );
}
