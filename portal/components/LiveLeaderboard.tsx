"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

interface Row {
  rank: number;
  cumulative_delta: number;
  matches_played: number;
  bot_id: string;
  bots: { bot_name: string; user_id: string; users: { display_name: string } | { display_name: string }[] } | { bot_name: string; user_id: string; users: { display_name: string } | { display_name: string }[] }[];
}

interface Props {
  initialRows: Row[];
  tournamentId: string;
  myBotId?: string;
}

function delta(n: number) {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toLocaleString()}`;
}

export default function LiveLeaderboard({ initialRows, tournamentId, myBotId }: Props) {
  const [rows, setRows]     = useState<Row[]>(initialRows);
  const [updated, setUpdated] = useState(false);

  useEffect(() => {
    const supabase = createClient();

    const channel = supabase
      .channel("leaderboard-live")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "leaderboard", filter: `tournament_id=eq.${tournamentId}` },
        async () => {
          // Refetch fresh data
          const { data } = await supabase
            .from("leaderboard")
            .select("rank, cumulative_delta, matches_played, bot_id, bots(bot_name, user_id, users(display_name))")
            .eq("tournament_id", tournamentId)
            .order("rank", { ascending: true })
            .limit(100);
          if (data) {
            setRows(data as unknown as Row[]);
            setUpdated(true);
            setTimeout(() => setUpdated(false), 2000);
          }
        }
      )
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, [tournamentId]);

  return (
    <div>
      {updated && (
        <div className="mb-4 text-xs text-green-400 bg-green-400/10 border border-green-400/20 rounded-lg px-4 py-2 inline-block">
          ⚡ Leaderboard updated
        </div>
      )}
      <div className="bg-[#111] border border-[#1e1e1e] rounded-xl overflow-hidden">
        {/* Header */}
        <div className="grid grid-cols-12 px-6 py-3 border-b border-[#1e1e1e] text-xs text-[#555] uppercase tracking-wide">
          <div className="col-span-1">#</div>
          <div className="col-span-5">Bot</div>
          <div className="col-span-3">Player</div>
          <div className="col-span-2 text-right">Chip Δ</div>
          <div className="col-span-1 text-right">Matches</div>
        </div>

        {rows.map((row, i) => {
          const isMe = row.bot_id === myBotId;
          return (
            <div
              key={row.bot_id}
              className={`grid grid-cols-12 px-6 py-4 border-b border-[#0f0f0f] items-center transition-colors ${
                isMe ? "bg-[#0f1a0f]" : i % 2 === 0 ? "" : "bg-[#0d0d0d]"
              }`}
            >
              <div className="col-span-1">
                <span className={`text-sm font-bold ${
                  row.rank === 1 ? "text-yellow-400" :
                  row.rank === 2 ? "text-[#aaa]" :
                  row.rank === 3 ? "text-orange-400" :
                  "text-[#444]"
                }`}>
                  {row.rank === 1 ? "🥇" : row.rank === 2 ? "🥈" : row.rank === 3 ? "🥉" : row.rank}
                </span>
              </div>
              <div className="col-span-5 flex items-center gap-2">
                <span className="text-sm font-medium text-white">{Array.isArray(row.bots) ? row.bots[0]?.bot_name : (row.bots as any)?.bot_name}</span>
                {isMe && (
                  <span className="text-xs text-green-400 bg-green-400/10 border border-green-400/20 px-2 py-0.5 rounded-full">
                    you
                  </span>
                )}
              </div>
              <div className="col-span-3 text-xs text-[#555]">
                {(() => {
                  const b = Array.isArray(row.bots) ? row.bots[0] : row.bots as any;
                  const u = Array.isArray(b?.users) ? b?.users[0] : b?.users;
                  return u?.display_name;
                })()}
              </div>
              <div className={`col-span-2 text-right text-sm font-mono font-medium ${
                row.cumulative_delta >= 0 ? "text-green-400" : "text-red-400"
              }`}>
                {delta(row.cumulative_delta)}
              </div>
              <div className="col-span-1 text-right text-xs text-[#444]">
                {row.matches_played}
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-xs text-[#333] text-center mt-4">
        Live · updates automatically via Supabase Realtime
      </p>
    </div>
  );
}
