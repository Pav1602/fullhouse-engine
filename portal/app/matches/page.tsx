import { redirect } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import NavBar from "@/components/NavBar";

export default async function MatchesPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/");

  const [{ data: profile }, { data: bot }, { data: tournament }] = await Promise.all([
    supabase.from("users").select("display_name").eq("id", user.id).single(),
    supabase.from("bots").select("id, bot_name").eq("user_id", user.id).maybeSingle(),
    supabase.from("tournaments").select("id, name").order("created_at", { ascending: false }).limit(1).maybeSingle(),
  ]);

  // Matches the user's bot played in (own match history)
  let myMatches: any[] = [];
  if (bot) {
    const { data } = await supabase
      .from("match_bots")
      .select(`
        seat, final_stack, chip_delta,
        matches(id, round, status, started_at, completed_at, n_hands, tournament_id,
          match_bots(seat, chip_delta, bot_id, bots(bot_name)))
      `)
      .eq("bot_id", bot.id)
      .order("matches(completed_at)", { ascending: false })
      .limit(50);
    myMatches = data ?? [];
  }

  // All matches in the current tournament (browseable / spectatable)
  let recentMatches: any[] = [];
  if (tournament) {
    const { data } = await supabase
      .from("matches")
      .select(`
        id, round, status, started_at, completed_at, n_hands,
        match_bots(seat, chip_delta, bot_id, bots(bot_name))
      `)
      .eq("tournament_id", tournament.id)
      .eq("status", "complete")
      .order("completed_at", { ascending: false })
      .limit(20);
    recentMatches = data ?? [];
  }

  function botList(mbs: any[]): string {
    return (mbs ?? []).map(b => b?.bots?.bot_name).filter(Boolean).join(", ");
  }
  function topBot(mbs: any[]): { name: string; delta: number } | null {
    const xs = (mbs ?? []).filter(b => b?.bots?.bot_name && typeof b?.chip_delta === "number");
    if (!xs.length) return null;
    xs.sort((a, b) => (b.chip_delta ?? 0) - (a.chip_delta ?? 0));
    return { name: xs[0].bots.bot_name, delta: xs[0].chip_delta ?? 0 };
  }

  return (
    <>
      <NavBar displayName={profile?.display_name} />
      <main className="max-w-5xl mx-auto px-4 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white">Matches</h1>
          <p className="text-[#666] text-sm mt-1">
            {bot ? `Match history for ${bot.bot_name}` : "Submit a bot to start playing matches"}
          </p>
        </div>

        {/* Your matches */}
        {myMatches.length > 0 && (
          <section className="mb-10">
            <h2 className="text-xs uppercase tracking-wide text-[#555] mb-3">Your matches</h2>
            <div className="bg-[#111] border border-[#1e1e1e] rounded-xl overflow-hidden">
              <div className="grid grid-cols-12 px-6 py-3 border-b border-[#1e1e1e] text-xs text-[#555] uppercase tracking-wide">
                <div className="col-span-2">Round</div>
                <div className="col-span-5">Opponents</div>
                <div className="col-span-2">Hands</div>
                <div className="col-span-2 text-right">Chip Δ</div>
                <div className="col-span-1 text-right">Replay</div>
              </div>
              {myMatches.map((mb, i) => {
                const match = mb.matches;
                const myDelta = mb.chip_delta ?? 0;
                const opponents = (match?.match_bots ?? [])
                  .filter((b: any) => b.bot_id !== bot?.id)
                  .map((b: any) => b.bots?.bot_name)
                  .filter(Boolean)
                  .join(", ");
                return (
                  <Link
                    key={match?.id ?? i}
                    href={`/matches/${match?.id}`}
                    className={`grid grid-cols-12 px-6 py-4 border-b border-[#0f0f0f] items-center hover:bg-[#161616] transition-colors ${
                      i % 2 === 0 ? "" : "bg-[#0d0d0d]"
                    }`}
                  >
                    <div className="col-span-2 text-sm text-[#888]">R{match?.round ?? "—"}</div>
                    <div className="col-span-5 text-sm text-[#aaa] truncate">{opponents || "—"}</div>
                    <div className="col-span-2 text-sm text-[#555]">{match?.n_hands ?? "—"}</div>
                    <div className={`col-span-2 text-right text-sm font-mono font-medium ${myDelta >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {myDelta >= 0 ? "+" : ""}{myDelta.toLocaleString()}
                    </div>
                    <div className="col-span-1 text-right text-xs text-[#444]">→</div>
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        {/* Recent tournament matches (spectator) */}
        {recentMatches.length > 0 && (
          <section>
            <h2 className="text-xs uppercase tracking-wide text-[#555] mb-3">
              Recent tournament matches
            </h2>
            <div className="bg-[#111] border border-[#1e1e1e] rounded-xl overflow-hidden">
              <div className="grid grid-cols-12 px-6 py-3 border-b border-[#1e1e1e] text-xs text-[#555] uppercase tracking-wide">
                <div className="col-span-2">Round</div>
                <div className="col-span-6">Bots in match</div>
                <div className="col-span-3">Top bot Δ</div>
                <div className="col-span-1 text-right">Replay</div>
              </div>
              {recentMatches.map((m, i) => {
                const top = topBot(m.match_bots);
                return (
                  <Link
                    key={m.id}
                    href={`/matches/${m.id}`}
                    className={`grid grid-cols-12 px-6 py-4 border-b border-[#0f0f0f] items-center hover:bg-[#161616] transition-colors ${
                      i % 2 === 0 ? "" : "bg-[#0d0d0d]"
                    }`}
                  >
                    <div className="col-span-2 text-sm text-[#888]">R{m.round}</div>
                    <div className="col-span-6 text-sm text-[#aaa] truncate">{botList(m.match_bots)}</div>
                    <div className="col-span-3 text-sm text-[#888] font-mono">
                      {top ? `${top.name} ${top.delta >= 0 ? "+" : ""}${top.delta.toLocaleString()}` : "—"}
                    </div>
                    <div className="col-span-1 text-right text-xs text-[#444]">→</div>
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        {myMatches.length === 0 && recentMatches.length === 0 && (
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-16 text-center">
            <div className="text-4xl mb-4">🎰</div>
            <h2 className="text-lg font-semibold text-white mb-2">No matches yet</h2>
            <p className="text-sm text-[#666]">
              {!bot
                ? "Submit your bot from the dashboard to get started."
                : "Your bot hasn't played any matches yet. Check back once the tournament begins."}
            </p>
          </div>
        )}
      </main>
    </>
  );
}
