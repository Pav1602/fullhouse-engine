import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import NavBar from "@/components/NavBar";
import HandReplay from "@/components/HandReplay";

interface PageProps { params: Promise<{ id: string }>; }

export default async function MatchReplayPage({ params }: PageProps) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/");

  const [{ data: profile }, { data: match }, { data: matchBots }, { data: hands }] = await Promise.all([
    supabase.from("users").select("display_name").eq("id", user.id).single(),
    supabase
      .from("matches")
      .select("id, round, status, started_at, completed_at, n_hands, tournament_id, tournaments(name)")
      .eq("id", id)
      .maybeSingle(),
    supabase
      .from("match_bots")
      .select("bot_id, seat, final_stack, chip_delta, bots(bot_name, users(display_name, avatar_key, hat_key))")
      .eq("match_id", id),
    supabase
      .from("hands")
      .select("id, hand_num, street, pot, community_cards, action_log, revealed_cards, hand_winners(bot_id, amount)")
      .eq("match_id", id)
      .order("hand_num", { ascending: true }),
  ]);

  if (!match) notFound();

  const bots = (matchBots ?? [])
    .map(mb => {
      const bot = Array.isArray(mb.bots) ? mb.bots[0] : (mb.bots as any);
      const usr = bot ? (Array.isArray(bot.users) ? bot.users[0] : bot.users) : undefined;
      return {
        bot_id: mb.bot_id,
        bot_name: bot?.bot_name ?? "?",
        seat: mb.seat,
        display_name: usr?.display_name ?? "",
        avatar_key: usr?.avatar_key ?? "robot_1",
        hat_key: usr?.hat_key ?? "none",
        chip_delta: mb.chip_delta ?? 0,
        final_stack: mb.final_stack ?? null,
      };
    })
    .sort((a, b) => a.seat - b.seat);

  const hs = (hands ?? []).map(h => ({
    id: h.id,
    hand_num: h.hand_num,
    street: h.street,
    pot: h.pot,
    community_cards: h.community_cards ?? [],
    action_log: h.action_log ?? [],
    revealed_cards: (h.revealed_cards as any) ?? {},
    hand_winners: (h.hand_winners ?? []) as { bot_id: string; amount: number }[],
  }));

  const tournament = Array.isArray(match.tournaments) ? match.tournaments[0] : (match.tournaments as any);
  const matchTitle = `Round ${match.round}`;
  const matchSubtitle = `${tournament?.name ?? "Tournament"} · ${match.n_hands} hands · ${match.status}`;

  return (
    <>
      <NavBar displayName={profile?.display_name} />
      <main className="max-w-5xl mx-auto px-4 py-10">
        <div className="mb-6">
          <Link href="/matches" className="text-xs text-[#666] hover:text-[#aaa] transition-colors">← Back to matches</Link>
          <h1 className="text-2xl font-bold text-white mt-2">Match replay</h1>
          <p className="text-[#666] text-sm mt-1">{matchSubtitle}</p>
        </div>

        {hs.length === 0 ? (
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-12 text-center">
            <p className="text-sm text-[#666]">No hand history recorded for this match yet.</p>
          </div>
        ) : (
          <HandReplay matchTitle={matchTitle} matchSubtitle={matchSubtitle} bots={bots} hands={hs} />
        )}
      </main>
    </>
  );
}
