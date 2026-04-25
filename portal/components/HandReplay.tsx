"use client";

/**
 * HandReplay — client component that takes one match's bots + hands and
 * renders a step-through replay. Minimal styling, dealer character, animated
 * pot tween + card flip, dealer button rotates with hand index.
 */

import { useEffect, useMemo, useState } from "react";
import { PixelRobot, type AvatarKey, type HatKey } from "./PixelRobot";

type Bot = {
  bot_id: string;
  bot_name: string;
  seat: number;
  display_name: string;
  avatar_key: string;
  hat_key: string;
  chip_delta: number;
  final_stack: number | null;
};
type ActionEntry = { seat: number; action: string; amount?: number };
type Hand = {
  id: string;
  hand_num: number;
  street: string;
  pot: number;
  community_cards: string[];
  action_log: ActionEntry[];
  revealed_cards: Record<string, string[]>;
  hand_winners: { bot_id: string; amount: number }[];
};

interface Props {
  matchTitle: string;
  matchSubtitle: string;
  bots: Bot[];
  hands: Hand[];
}

const SUITS: Record<string, string> = { h: "♥", d: "♦", s: "♠", c: "♣" };
const RED = (s: string) => s === "h" || s === "d";

function Card({ card, hidden, empty, flip }: { card?: string; hidden?: boolean; empty?: boolean; flip?: boolean }) {
  if (empty) return <div className="rep-card empty" />;
  if (hidden || !card) return <div className={"rep-card back" + (flip ? " flip-in" : "")} />;
  const r = card[0]; const s = card[1];
  return (
    <div className={"rep-card" + (RED(s) ? " red" : "") + (flip ? " flip-in" : "")}>
      <span className="r">{r}</span><span className="s">{SUITS[s] ?? s}</span>
    </div>
  );
}

function Croupier() {
  return (
    <svg viewBox="0 0 16 16" width="44" height="44" shapeRendering="crispEdges">
      <rect x="5" y="3" width="6" height="6" fill="#e8c5a0" />
      <rect x="4" y="4" width="1" height="4" fill="#e8c5a0" />
      <rect x="11" y="4" width="1" height="4" fill="#e8c5a0" />
      <rect x="4" y="2" width="8" height="2" fill="#1a1a1a" />
      <rect x="3" y="3" width="2" height="2" fill="#1a1a1a" />
      <rect x="11" y="3" width="2" height="2" fill="#1a1a1a" />
      <rect x="6" y="6" width="1" height="1" fill="#1a1a1a" />
      <rect x="9" y="6" width="1" height="1" fill="#1a1a1a" />
      <rect x="7" y="8" width="2" height="1" fill="#a86060" />
      <rect x="3" y="10" width="10" height="6" fill="#1a1a1a" />
      <rect x="3" y="10" width="3" height="6" fill="#0a0a0a" />
      <rect x="10" y="10" width="3" height="6" fill="#0a0a0a" />
      <rect x="6" y="10" width="4" height="6" fill="#fff" />
      <rect x="6" y="10" width="1" height="2" fill="#c0392b" />
      <rect x="9" y="10" width="1" height="2" fill="#c0392b" />
      <rect x="7" y="10" width="2" height="2" fill="#9b2a23" />
    </svg>
  );
}

// Position pills derived from dealer rotation
function positionForSeat(seat: number, dealer: number, n: number): string {
  if (n <= 0) return "";
  if (seat === dealer) return "BTN";
  const sb = (dealer + 1) % n;
  const bb = (dealer + 2) % n;
  if (seat === sb) return "SB";
  if (seat === bb) return "BB";
  if (seat === (dealer + 3) % n) return "UTG";
  return "MP";
}

// Sum amounts from action_log entries that match a predicate, for a given seat
function sumActions(log: ActionEntry[], seat: number): { fold: boolean; betTotal: number } {
  let fold = false;
  let betTotal = 0;
  for (const a of log) {
    if (a.seat !== seat) continue;
    const act = (a.action || "").toLowerCase();
    if (act === "fold" || act === "folds") fold = true;
    if (typeof a.amount === "number" && a.amount > 0 &&
        ["bet","raise","call","post_sb","post_bb","small_blind","big_blind","all_in","allin"].includes(act)) {
      betTotal += a.amount;
    }
  }
  return { fold, betTotal };
}

function actionPretty(a: ActionEntry, seatNames: Record<number, string>): string {
  const name = seatNames[a.seat] ?? `seat ${a.seat}`;
  const act = (a.action || "").toLowerCase();
  const amount = a.amount ? ` ${a.amount.toLocaleString()}` : "";
  const map: Record<string, string> = {
    post_sb: "posts SB", small_blind: "posts SB",
    post_bb: "posts BB", big_blind: "posts BB",
    fold: "folds", check: "checks", call: "calls",
    bet: "bets", raise: "raises to", all_in: "all-in", allin: "all-in",
  };
  return `${name} ${map[act] ?? act}${["fold","check","all_in","allin"].includes(act) ? "" : amount}`;
}

export default function HandReplay({ matchTitle, matchSubtitle, bots, hands }: Props) {
  const [handIdx, setHandIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [displayPot, setDisplayPot] = useState<number>(hands[0]?.pot ?? 0);
  const [prevCommunityLen, setPrevCommunityLen] = useState<number>(0);
  const [prevRevealed, setPrevRevealed] = useState<boolean>(false);

  const sortedBots = useMemo(() => [...bots].sort((a, b) => a.seat - b.seat), [bots]);
  const seatToBotId = useMemo(() => Object.fromEntries(sortedBots.map(b => [b.seat, b.bot_id])), [sortedBots]);
  const seatNames = useMemo(() => Object.fromEntries(sortedBots.map(b => [b.seat, b.bot_name])), [sortedBots]);

  const hand = hands[handIdx];
  const dealerSeat = hand ? sortedBots[handIdx % sortedBots.length]?.seat ?? 0 : 0;

  const handWinnerIds = useMemo(() => new Set((hand?.hand_winners ?? []).map(w => w.bot_id)), [hand]);
  const isShowdown = hand?.street === "showdown" || hand?.community_cards?.length === 5;

  // Animate pot tween between hands
  useEffect(() => {
    if (!hand) return;
    let raf = 0;
    const start = displayPot;
    const target = hand.pot;
    const t0 = performance.now();
    const dur = 450;
    function frame(t: number) {
      const k = Math.min(1, (t - t0) / dur);
      setDisplayPot(Math.round(start + (target - start) * k));
      if (k < 1) raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handIdx]);

  // Auto-play
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      setHandIdx(i => {
        if (i >= hands.length - 1) { setPlaying(false); return i; }
        return i + 1;
      });
    }, 2200);
    return () => clearInterval(t);
  }, [playing, hands.length]);

  // Track previous values for animations
  useEffect(() => {
    setPrevCommunityLen(hand?.community_cards.length ?? 0);
    setPrevRevealed(isShowdown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handIdx]);

  if (!hand || sortedBots.length === 0) {
    return <div className="text-sm text-[#666]">No hands recorded for this match yet.</div>;
  }

  const community = hand.community_cards ?? [];
  const visibleCommunity = community.slice(0, ({ preflop: 0, flop: 3, turn: 4, river: 5, showdown: 5 } as Record<string, number>)[hand.street] ?? community.length);
  const log = hand.action_log ?? [];

  return (
    <div>
      <style>{`
        .rep { background:#0a0a0a; border:0.5px solid #1e1e1e; border-radius:12px; padding:16px; color:#fff; }
        .rep-table { background:#14110e; border:1px solid #2a2218; border-radius:16px; padding:18px 18px 12px; position:relative; }
        .rep-top { display:grid; grid-template-columns:92px 1fr 130px; align-items:center; gap:18px; min-height:92px; }
        .rep-card { width:38px; height:54px; border-radius:5px; background:#fff; color:#000; border:0.5px solid #000; display:flex; flex-direction:column; align-items:center; justify-content:center; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; transition: transform .35s ease, opacity .35s ease; }
        .rep-card .r { font-size:16px; font-weight:700; line-height:1; }
        .rep-card .s { font-size:12px; line-height:1; margin-top:2px; }
        .rep-card.red { color:#c0392b; }
        .rep-card.empty { background:transparent; border:0.5px dashed #3a3022; color:transparent; }
        .rep-card.back { background:#1a1a1a; background-image: linear-gradient(135deg, rgba(255,255,255,0.06) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.06) 50%, rgba(255,255,255,0.06) 75%, transparent 75%); background-size:6px 6px; border-color:#2a2a2a; color:transparent; }
        .rep-card.flip-in { animation: rep-flipIn .45s ease both; }
        @keyframes rep-flipIn { 0% { transform: rotateY(90deg); opacity:0; } 100% { transform: rotateY(0); opacity:1; } }
        .rep-deck { position:relative; width:32px; height:44px; margin-top:4px; }
        .rep-deck .b { position:absolute; top:0; left:0; width:32px; height:44px; background:#1a1a1a; background-image: linear-gradient(135deg, rgba(255,255,255,0.06) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.06) 50%, rgba(255,255,255,0.06) 75%, transparent 75%); background-size:6px 6px; border:0.5px solid #2a2a2a; border-radius:4px; }
        .rep-deck .b:nth-child(1){ transform: translate(0,0); } .rep-deck .b:nth-child(2){ transform: translate(-1px,-1px); } .rep-deck .b:nth-child(3){ transform: translate(-2px,-2px); }
        .rep-pot { text-align:right; }
        .rep-pot-label { color:#5d5240; font-size:10px; text-transform:uppercase; letter-spacing:0.12em; }
        .rep-pot-amt { color:#ffd93d; font-size:22px; font-weight:700; font-variant-numeric:tabular-nums; }
        .rep-street { display:inline-block; margin-top:4px; color:#5d5240; font-size:10px; text-transform:uppercase; letter-spacing:0.12em; border:0.5px solid #2a2218; border-radius:999px; padding:2px 8px; }
        .rep-community { display:flex; gap:6px; justify-content:center; align-items:center; }
        .rep-players { display:grid; grid-template-columns: repeat(${sortedBots.length}, 1fr); gap:8px; margin-top:14px; }
        .rep-player { background:#1a1611; border:0.5px solid #2a2218; border-radius:8px; padding:8px 6px 6px; display:flex; flex-direction:column; align-items:center; gap:4px; transition: opacity .35s ease, border-color .35s ease, background .35s ease; position:relative; }
        .rep-player.folded { opacity:0.32; }
        .rep-player.winner { border-color:#ffd93d; background:#1a1408; }
        .rep-pname { color:#fff; font-size:11px; font-weight:500; line-height:1.2; text-align:center; }
        .rep-pstack { color:#888; font-size:10px; font-family: ui-monospace, monospace; line-height:1.2; }
        .rep-phole { display:flex; gap:2px; margin-top:2px; }
        .rep-phole .rep-card { width:22px; height:30px; }
        .rep-phole .rep-card .r { font-size:10px; }
        .rep-phole .rep-card .s { font-size:9px; margin-top:1px; }
        .rep-dbtn { position:absolute; top:4px; right:4px; width:16px; height:16px; border-radius:50%; background:#ffd93d; color:#1a1a1a; display:flex; align-items:center; justify-content:center; font-size:9px; font-weight:700; border:1px solid #c19e11; }
        .rep-pos { position:absolute; bottom:4px; left:4px; color:#5d5240; font-size:8px; text-transform:uppercase; letter-spacing:0.06em; }
        .rep-bet-chip { background:#ffd93d; color:#1a1a1a; font-size:9px; font-weight:700; padding:2px 6px; border-radius:999px; border:1px solid #c19e11; font-family: ui-monospace, monospace; margin-top:2px; }
        .rep-ctrls { display:flex; align-items:center; gap:8px; margin-top:12px; }
        .rep-btn { background:#1a1a1a; color:#ddd; border:0.5px solid #2a2a2a; border-radius:8px; padding:7px 14px; font-size:12px; cursor:pointer; transition: background .15s ease; }
        .rep-btn:hover { background:#222; border-color:#3a3a3a; }
        .rep-btn:disabled { opacity:0.3; cursor:not-allowed; }
        .rep-step-info { flex:1; text-align:right; color:#555; font-size:11px; font-family: ui-monospace, monospace; }
        .rep-progress { height:2px; background:#1a1a1a; border-radius:999px; margin-top:10px; overflow:hidden; }
        .rep-progress-bar { height:100%; background:#4ECDC4; transition: width .45s ease; }
        .rep-log { margin-top:10px; background:#0a0a0a; border:0.5px solid #1e1e1e; border-radius:8px; padding:8px 12px; max-height:130px; overflow-y:auto; }
        .rep-log-entry { color:#888; font-size:12px; font-family: ui-monospace, monospace; padding:3px 0; }
        .rep-log-entry.win { color:#ffd93d; } .rep-log-entry.bet { color:#e8c134; } .rep-log-entry.fold { color:#555; } .rep-log-entry.check { color:#4ECDC4; }
      `}</style>

      <div className="rep">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 500 }}>{matchTitle} · Hand {hand.hand_num} of {hands.length}</div>
          <div style={{ color: "#555", fontSize: 11, fontFamily: "ui-monospace, monospace" }}>{matchSubtitle}</div>
        </div>

        <div className="rep-table">
          <div className="rep-top">
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
              <Croupier />
              <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.12em" }}>Dealer</div>
              <div className="rep-deck"><div className="b" /><div className="b" /><div className="b" /></div>
            </div>
            <div className="rep-community">
              {Array.from({ length: 5 }).map((_, i) => (
                <Card key={i} card={visibleCommunity[i]} empty={i >= visibleCommunity.length} flip={i >= prevCommunityLen && i < visibleCommunity.length} />
              ))}
            </div>
            <div className="rep-pot">
              <div className="rep-pot-label">POT</div>
              <div className="rep-pot-amt">{displayPot.toLocaleString()}</div>
              <div className="rep-street">{hand.street}</div>
            </div>
          </div>

          <div className="rep-players">
            {sortedBots.map(b => {
              const seatLog = sumActions(log, b.seat);
              const isFolded = seatLog.fold;
              const isWinner = handWinnerIds.has(b.bot_id);
              const isDealer = b.seat === dealerSeat;
              const pos = positionForSeat(b.seat, dealerSeat, sortedBots.length);
              const reveal = isShowdown && !isFolded;
              const revealedCards = (hand.revealed_cards ?? {})[b.bot_id] ?? [];
              const hole: (string | undefined)[] = reveal && revealedCards.length >= 2 ? [revealedCards[0], revealedCards[1]] : [undefined, undefined];
              return (
                <div key={b.bot_id} className={"rep-player" + (isFolded ? " folded" : "") + (isWinner ? " winner" : "")}>
                  {isDealer && <div className="rep-dbtn" title="Dealer button">D</div>}
                  <div className="rep-pos">{pos}</div>
                  <PixelRobot avatar={b.avatar_key as AvatarKey} hat={b.hat_key as HatKey} size={36} />
                  <div className="rep-pname">{b.bot_name}{isWinner ? " ★" : ""}</div>
                  <div className="rep-pstack">{(b.final_stack ?? 0).toLocaleString()}</div>
                  <div className="rep-phole">
                    <Card card={hole[0]} hidden={!reveal} flip={reveal && !prevRevealed} />
                    <Card card={hole[1]} hidden={!reveal} flip={reveal && !prevRevealed} />
                  </div>
                  {seatLog.betTotal > 0 && <div className="rep-bet-chip">{seatLog.betTotal.toLocaleString()}</div>}
                </div>
              );
            })}
          </div>
        </div>

        <div className="rep-ctrls">
          <button className="rep-btn" onClick={() => setHandIdx(i => Math.max(0, i - 1))} disabled={handIdx === 0}>‹ Prev hand</button>
          <button className="rep-btn" onClick={() => setHandIdx(i => Math.min(hands.length - 1, i + 1))} disabled={handIdx === hands.length - 1}>Next hand ›</button>
          <button className="rep-btn" onClick={() => setPlaying(p => !p)}>{playing ? "⏸ Pause" : "▶ Play"}</button>
          <span className="rep-step-info">hand {handIdx + 1} / {hands.length}</span>
        </div>
        <div className="rep-progress"><div className="rep-progress-bar" style={{ width: `${((handIdx + 1) / hands.length) * 100}%` }} /></div>

        <div className="rep-log">
          {log.length === 0
            ? <div className="rep-log-entry">No actions logged for this hand.</div>
            : log.map((a, i) => {
                const text = actionPretty(a, seatNames);
                let cls = "";
                if (/folds$/.test(text)) cls = "fold";
                else if (/checks$/.test(text)) cls = "check";
                else if (/(bets|raises) /.test(text)) cls = "bet";
                return <div key={i} className={"rep-log-entry " + cls}>{text}</div>;
              })}
          {hand.hand_winners?.length > 0 && (
            <div className="rep-log-entry win">★ {hand.hand_winners.map(w => `${seatNames[(sortedBots.find(b => b.bot_id === w.bot_id)?.seat) ?? -1] ?? "?"} wins ${w.amount.toLocaleString()}`).join(", ")}</div>
          )}
        </div>
      </div>
    </div>
  );
}
