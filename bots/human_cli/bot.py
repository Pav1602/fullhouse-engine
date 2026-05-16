import sys
import os
import time

# Global dictionary to remember seat assignments across the hand
SEAT_TO_BOT = {}

def decide(game_state):
    s = game_state
    
    # Store players mapping when available
    if "players" in s:
        for p in s["players"]:
            SEAT_TO_BOT[p["seat"]] = p.get("bot_id", f"Seat {p['seat']}")

    with open('/dev/tty', 'w') as tty_out, open('/dev/tty', 'r') as tty_in:
        def display(msg="", end="\n"):
            tty_out.write(msg + end)
            tty_out.flush()

        # Handle end of hand review
        if s.get("type") == "hand_complete":
            display("\n" + "="*60)
            display(f"HAND COMPLETE: {s.get('hand_id', 'Unknown')}")
            display("="*60)
            
            # Show the final board
            if s.get('community_cards'):
                display(f"Final Board: {' '.join(s['community_cards'])}")
            else:
                display("Final Board: (None)")
                
            # Winners
            winners = s.get("winners", [])
            display(f"\nWinners ({len(winners)}):")
            for w in winners:
                display(f"  🏆 {w.get('bot_id', 'Unknown')} wins {w.get('amount', 0)}")
                
            # Show all players, their stacks, and revealed cards
            display("\nPlayer Hands (All cards revealed for diagnostics):")
            final_stacks = s.get("final_stacks", {})
            revealed = s.get("revealed_cards", {})
            all_hole_cards = s.get("all_hole_cards", {})
            hand_strengths = s.get("hand_strengths", {})
            
            # Use SEAT_TO_BOT if final_stacks empty or fallback
            all_bots = list(final_stacks.keys())
            if not all_bots:
                all_bots = list(SEAT_TO_BOT.values())
            
            # Try to print out what we know about each bot
            for bot_id in all_bots:
                stack = final_stacks.get(bot_id, "?")
                
                # Check if this player revealed cards at showdown, otherwise use the diagnostic all_hole_cards
                bot_cards = revealed.get(bot_id)
                hand_str = hand_strengths.get(bot_id, "")
                
                actual_cards = s.get("all_hole_cards", {}).get(bot_id, [])
                cards_str = " ".join(actual_cards) if actual_cards else "(Unknown)"
                
                if bot_cards:
                    display(f"  [{bot_id}] Stack: {stack} -> Showed: {cards_str} ({hand_str})")
                else:
                    display(f"  [{bot_id}] Stack: {stack} -> Folded/Mucked (Cards were: {cards_str})")

            display("\nFull Action Log:")
            current_street = None
            for e in s.get('events', []):
                street = e.get("street", "").upper()
                
                if e.get("type") == "street_start":
                    if street != current_street:
                        display_str = f"\n  --- {street} ---"
                        if e.get("community_cards"):
                            display_str += f" [{' '.join(e['community_cards'])}]"
                        display(display_str)
                        current_street = street
                        
                elif e.get("type") in ("blind", "action"):
                    # Catch blinds which happen before the explicit street_start event
                    if street != current_street:
                        display(f"\n  --- {street} ---")
                        current_street = street
                        
                    bot_id = e.get('bot_id', SEAT_TO_BOT.get(e.get('seat'), 'Unknown'))
                    action = e.get('action')
                    amt = e.get('amount', 0)
                    amt_str = f" {amt}" if amt > 0 or action in ('call', 'raise', 'small_blind', 'big_blind') else ""
                    display(f"    {bot_id}: {action}{amt_str}")
            
            display("\n" + "="*60)
            display("Press [ENTER] to start the next hand...", end="")
            tty_in.readline()
            return {}

        # Normal action request
        display(f"\n=== {s['street'].upper()} ===")
        display(f"Hand: {s.get('hand_id', 'Unknown')}")
        display(f"Hole: {' '.join(s.get('your_cards', []))}", end="")
        if s.get('community_cards'):
            display(f"   Board: {' '.join(s['community_cards'])}")
        else:
            display("")
        display(f"Pot: {s['pot']}   Your stack: {s['your_stack']}   Owed: {s['amount_owed']}")
        
        for e in s.get('action_log', [])[-6:]:
            seat = e.get('seat')
            bot_id = SEAT_TO_BOT.get(seat, f"seat{seat}")
            display(f"  {bot_id}: {e.get('action')} {e.get('amount', '')}")

        valid = "[f]old, [ch]eck, [ca]ll, [r]aise <amt>, [a]ll-in"
        while True:
            display(f"\n{valid}\n> ", end="")
            cmd_line = tty_in.readline()
            if not cmd_line: # EOF
                return {"action": "fold"}
            
            cmd = cmd_line.strip().lower().split()
            if not cmd: continue
            a = cmd[0]
            if a in ("f", "fold"):    return {"action": "fold"}
            if a in ("ch", "check"):
                if not s['can_check']: display("can't check"); continue
                return {"action": "check"}
            if a in ("ca", "call"):   return {"action": "call"}
            if a in ("a", "all_in", "allin", "shove"): return {"action": "all_in"}
            if a in ("r", "raise") and len(cmd) > 1:
                try:
                    amt = int(cmd[1])
                    return {"action": "raise", "amount": amt}
                except ValueError:
                    display("invalid amount")
                    continue
            display("didn't parse")
