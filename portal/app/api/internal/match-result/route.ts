// app/api/internal/match-result/route.ts
// Called by the BullMQ worker after each match completes.
// Protected by INTERNAL_API_KEY — never exposed to the public.

import { createClient } from "@supabase/supabase-js";
import { NextRequest, NextResponse } from "next/server";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!   // service role — bypasses RLS
);

export async function POST(req: NextRequest) {
  // Auth check
  const key = req.headers.get("x-internal-key");
  if (key !== process.env.INTERNAL_API_KEY) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: {
    match_id:    string;
    tournament:  string;
    round:       number;
    results:     Record<string, { final_stack: number; chip_delta: number }>;
    hands?:      any[];
  };

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { match_id, tournament, results, hands } = body;

  // Resolve tournament UUID from name
  const { data: t, error: tErr } = await supabase
    .from("tournaments")
    .select("id")
    .eq("name", tournament)
    .single();

  if (tErr || !t) {
    return NextResponse.json({ error: "Tournament not found" }, { status: 404 });
  }

  // Resolve bot UUIDs — match.py uses bot_id strings which map to bots.id
  const botIds = Object.keys(results);
  const { data: bots, error: bErr } = await supabase
    .from("bots")
    .select("id, bot_name")
    .in("id", botIds);

  if (bErr) {
    return NextResponse.json({ error: bErr.message }, { status: 500 });
  }

  // Build results array for the SQL function
  const resultArray = botIds.map((bot_id) => ({
    bot_id,
    chip_delta: results[bot_id].chip_delta,
  }));

  // Call the DB function — handles match update + leaderboard upsert + rank recompute
  const { error: fnErr } = await supabase.rpc("record_match_result", {
    p_match_id:     match_id,
    p_tournament_id: t.id,
    p_results:      resultArray,
  });

  if (fnErr) {
    console.error("[match-result] RPC error:", fnErr);
    return NextResponse.json({ error: fnErr.message }, { status: 500 });
  }

  // Write hand history (async — don't block the response)
  if (hands && hands.length > 0) {
    void writeHandHistory(match_id, hands);
  }

  return NextResponse.json({ ok: true, match_id });
}

async function writeHandHistory(match_id: string, hands: any[]) {
  // Batch insert hands in chunks of 100
  const CHUNK = 100;
  for (let i = 0; i < hands.length; i += CHUNK) {
    const chunk = hands.slice(i, i + CHUNK).map((h) => ({
      match_id,
      hand_num:       h.hand_num,
      street:         h.result.street,
      pot:            h.result.pot,
      community_cards: h.result.community_cards,
      action_log:     h.result.action_log,
      revealed_cards: h.result.revealed_cards ?? {},
    }));

    const { error } = await supabase.from("hands").insert(chunk);
    if (error) {
      console.error("[match-result] Hand insert error:", error.message);
    }
  }
}
