// Fullhouse Tournament Controller
// Manages the Swiss-system tournament: seeding, round scheduling, standings.
// This is the brain that decides who plays who each round.
//
// Swiss system rules:
//   - No elimination — everyone plays every round
//   - After each round, bots are ranked by cumulative chip delta
//   - Next round pairs similarly-ranked bots at the same table
//   - Top N after all rounds advance to the finale

const { scheduleRound, getQueueStats } = require("./producer");

// ---------------------------------------------------------------------------
// Swiss pairing
// ---------------------------------------------------------------------------

/**
 * Pair bots into 6-player tables using Swiss seeding.
 * Bots sorted by chip delta, grouped into sequential tables of 6.
 * Leftover bots (if total not divisible by 6) get a bye or join a smaller table.
 *
 * @param {Array} standings  — [{ bot_id, bot_path, cumulative_delta }, ...]
 * @param {number} tableSize — players per table (default 6)
 * @returns {Array}          — array of tables, each table = [{ bot_id, bot_path }]
 */
function swissPairing(standings, tableSize = 6) {
  // Sort by cumulative chip delta descending (best bots first)
  const sorted = [...standings].sort((a, b) => b.cumulative_delta - a.cumulative_delta);

  const tables = [];
  let i = 0;

  while (i < sorted.length) {
    const remaining = sorted.length - i;

    // If we have fewer than tableSize left, fold them into the previous table
    // (making it slightly bigger) rather than a tiny unfair table
    if (remaining < tableSize && tables.length > 0) {
      tables[tables.length - 1].push(...sorted.slice(i).map(strip));
      break;
    }

    tables.push(sorted.slice(i, i + tableSize).map(strip));
    i += tableSize;
  }

  return tables;
}

function strip({ bot_id, bot_path }) {
  return { bot_id, bot_path };
}

// ---------------------------------------------------------------------------
// Round management
// ---------------------------------------------------------------------------

/**
 * Schedule round 1 (random seeding — standings not yet established).
 */
async function scheduleRound1({ tournament, bots, nHands = 200 }) {
  // Shuffle for round 1
  const shuffled = [...bots].sort(() => Math.random() - 0.5);
  const tables   = swissPairing(shuffled.map((b) => ({ ...b, cumulative_delta: 0 })));

  console.log(`[tournament] Round 1: ${tables.length} tables, ${bots.length} bots`);
  return scheduleRound({ tournament, round: 1, tables, nHands });
}

/**
 * Schedule subsequent rounds based on current standings.
 */
async function scheduleNextRound({ tournament, round, standings, nHands = 200 }) {
  const tables = swissPairing(standings);
  console.log(
    `[tournament] Round ${round}: ${tables.length} tables, ${standings.length} bots`
  );
  return scheduleRound({ tournament, round, tables, nHands });
}

/**
 * Compute standings from match results.
 * results: [{ bot_id, chip_delta }] across all matches this tournament.
 */
function computeStandings(allResults) {
  const totals = {};

  for (const { bot_id, chip_delta, bot_path } of allResults) {
    if (!totals[bot_id]) {
      totals[bot_id] = { bot_id, bot_path, cumulative_delta: 0, matches: 0 };
    }
    totals[bot_id].cumulative_delta += chip_delta;
    totals[bot_id].matches++;
  }

  return Object.values(totals).sort(
    (a, b) => b.cumulative_delta - a.cumulative_delta
  );
}

/**
 * Select top N bots for the finale.
 */
function selectFinalists(standings, n = 32) {
  return standings.slice(0, n);
}

// ---------------------------------------------------------------------------
// Monitoring
// ---------------------------------------------------------------------------

/**
 * Poll until all jobs for a round are complete.
 * In prod you'd use a webhook/event instead — this is for dev/testing.
 */
async function waitForRound(expectedCount, pollIntervalMs = 2000) {
  console.log(`[tournament] Waiting for ${expectedCount} matches to complete...`);

  while (true) {
    const stats = await getQueueStats();
    const done  = stats.completed;
    const failed = stats.failed;

    process.stdout.write(
      `\r  waiting: ${stats.waiting}  active: ${stats.active}  done: ${done}  failed: ${failed}   `
    );

    if (stats.waiting === 0 && stats.active === 0) {
      console.log("\n[tournament] Round complete.");
      return { completed: done, failed };
    }

    await new Promise((r) => setTimeout(r, pollIntervalMs));
  }
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

module.exports = {
  swissPairing,
  scheduleRound1,
  scheduleNextRound,
  computeStandings,
  selectFinalists,
  waitForRound,
};
