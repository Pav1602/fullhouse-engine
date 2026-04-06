import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import NavBar from "@/components/NavBar";
import LiveLeaderboard from "@/components/LiveLeaderboard";

export default async function LeaderboardPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/");

  const [{ data: profile }, { data: tournament }, { data: userBot }] = await Promise.all([
    supabase.from("users").select("display_name").eq("id", user.id).single(),
    supabase.from("tournaments").select("*").order("created_at", { ascending: false }).limit(1).single(),
    supabase.from("bots").select("id").eq("user_id", user.id).single(),
  ]);

  let initialRows: any[] = [];
  if (tournament) {
    const { data } = await supabase
      .from("leaderboard")
      .select("rank, cumulative_delta, matches_played, bot_id, bots(bot_name, user_id, users(display_name))")
      .eq("tournament_id", tournament.id)
      .order("rank", { ascending: true })
      .limit(100);
    initialRows = data ?? [];
  }

  return (
    <>
      <NavBar displayName={profile?.display_name} />
      <main className="max-w-5xl mx-auto px-4 py-10">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Leaderboard</h1>
            <p className="text-[#666] text-sm mt-1">
              {tournament ? tournament.name : "Tournament not started yet"} · Updates live
            </p>
          </div>
          {tournament && (
            <span className="text-xs text-[#555] bg-[#111] border border-[#1e1e1e] px-3 py-1.5 rounded-full">
              Phase: {tournament.phase}
            </span>
          )}
        </div>

        {!tournament || initialRows.length === 0 ? (
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-16 text-center">
            <div className="text-4xl mb-4">🃏</div>
            <h2 className="text-lg font-semibold text-white mb-2">No matches yet</h2>
            <p className="text-sm text-[#666]">
              The leaderboard will populate once the tournament begins on 1 June 2026.
            </p>
          </div>
        ) : (
          <LiveLeaderboard
            initialRows={initialRows}
            tournamentId={tournament.id}
            myBotId={userBot?.id}
          />
        )}
      </main>
    </>
  );
}
