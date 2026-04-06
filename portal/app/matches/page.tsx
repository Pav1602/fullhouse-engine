import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import NavBar from "@/components/NavBar";

export default async function MatchesPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/");

  const [{ data: profile }, { data: bot }] = await Promise.all([
    supabase.from("users").select("display_name").eq("id", user.id).single(),
    supabase.from("bots").select("id, bot_name").eq("user_id", user.id).single(),
  ]);

  let matches: any[] = [];
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
    matches = data ?? [];
  }

  return (
    <>
      <NavBar displayName={profile?.display_name} />
      <main className="max-w-5xl mx-auto px-4 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white">Matches</h1>
          <p className="text-[#666] text-sm mt-1">
            {bot ? `Match history for ${bot.bot_name}` : "Submit a bot first to see matches"}
          </p>
        </div>

        {matches.length === 0 ? (
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-16 text-center">
            <div className="text-4xl mb-4">🎰</div>
            <h2 className="text-lg font-semibold text-white mb-2">No matches yet</h2>
            <p className="text-sm text-[#666]">
              {!bot
                ? "Submit your bot from the dashboard to get started."
                : "Your bot hasn't played any matches yet. Check back once the tournament begins."}
            </p>
          </div>
        ) : (
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl overflow-hidden">
            <div className="grid grid-cols-12 px-6 py-3 border-b border-[#1e1e1e] text-xs text-[#555] uppercase tracking-wide">
              <div className="col-span-2">Round</div>
              <div className="col-span-4">Opponents</div>
              <div className="col-span-2">Hands</div>
              <div className="col-span-2 text-right">Chip Δ</div>
              <div className="col-span-2 text-right">Result</div>
            </div>

            {matches.map((mb, i) => {
              const match    = mb.matches;
              const myDelta  = mb.chip_delta ?? 0;
              const opponents = (match?.match_bots ?? [])
                .filter((b: any) => b.bot_id !== bot?.id)
                .map((b: any) => b.bots?.bot_name)
                .filter(Boolean)
                .join(", ");

              return (
                <div
                  key={match?.id ?? i}
                  className={`grid grid-cols-12 px-6 py-4 border-b border-[#0f0f0f] items-center ${
                    i % 2 === 0 ? "" : "bg-[#0d0d0d]"
                  }`}
                >
                  <div className="col-span-2 text-sm text-[#888]">
                    R{match?.round ?? "—"}
                  </div>
                  <div className="col-span-4 text-sm text-[#aaa] truncate">
                    {opponents || "—"}
                  </div>
                  <div className="col-span-2 text-sm text-[#555]">
                    {match?.n_hands ?? "—"}
                  </div>
                  <div className={`col-span-2 text-right text-sm font-mono font-medium ${
                    myDelta >= 0 ? "text-green-400" : "text-red-400"
                  }`}>
                    {myDelta >= 0 ? "+" : ""}{myDelta.toLocaleString()}
                  </div>
                  <div className="col-span-2 text-right">
                    <span className={`text-xs px-2 py-1 rounded-full border ${
                      match?.status === "complete"
                        ? myDelta >= 0
                          ? "text-green-400 bg-green-400/10 border-green-400/20"
                          : "text-red-400 bg-red-400/10 border-red-400/20"
                        : "text-[#555] bg-[#555]/10 border-[#555]/20"
                    }`}>
                      {match?.status === "complete"
                        ? myDelta >= 0 ? "Win" : "Loss"
                        : match?.status ?? "—"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </>
  );
}
