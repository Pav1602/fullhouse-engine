// Fullhouse Queue — Producer
// Schedules match jobs for one tournament round.
// Called by the tournament controller after seedings are computed.
//
// Usage:
//   const { scheduleRound } = require('./producer');
//   await scheduleRound({ tournament, round, tables, nHands });

const { Queue } = require("bullmq");
const { QUEUE_NAMES, JOB_TYPES, DEFAULT_JOB_OPTIONS, REDIS_CONFIG } = require("./config");

let _queue = null;

function getQueue() {
  if (!_queue) {
    _queue = new Queue(QUEUE_NAMES.MATCHES, { connection: REDIS_CONFIG });
  }
  return _queue;
}

/**
 * Schedule all tables for one tournament round.
 *
 * @param {object} opts
 * @param {string} opts.tournament   - tournament id, e.g. "day1"
 * @param {number} opts.round        - round number
 * @param {Array}  opts.tables       - array of tables, each: [{ bot_id, bot_path }, ...]
 * @param {number} opts.nHands       - hands per match (default 200)
 * @returns {Promise<string[]>}      - list of job IDs added
 */
async function scheduleRound({ tournament, round, tables, nHands = 200 }) {
  const queue = getQueue();

  const jobs = tables.map((bots, tableIndex) => {
    const match_id = `${tournament}_r${round}_t${String(tableIndex).padStart(3, "0")}`;
    return {
      name: JOB_TYPES.RUN_MATCH,
      data: { match_id, tournament, round, n_hands: nHands, bots },
      opts: {
        ...DEFAULT_JOB_OPTIONS,
        jobId: match_id,   // idempotent — safe to re-queue on retry
      },
    };
  });

  await queue.addBulk(jobs);

  console.log(
    `[producer] Scheduled ${jobs.length} matches for ${tournament} round ${round}`
  );
  return jobs.map((j) => j.opts.jobId);
}

/**
 * Schedule a single match (used for playoff brackets).
 */
async function scheduleMatch({ match_id, tournament, round, bots, nHands = 200 }) {
  const queue = getQueue();
  const job = await queue.add(
    JOB_TYPES.RUN_MATCH,
    { match_id, tournament, round, n_hands: nHands, bots },
    { ...DEFAULT_JOB_OPTIONS, jobId: match_id }
  );
  console.log(`[producer] Scheduled match ${match_id} (job ${job.id})`);
  return job.id;
}

/**
 * Get queue depth — useful for the dashboard.
 */
async function getQueueStats() {
  const queue = getQueue();
  const [waiting, active, completed, failed] = await Promise.all([
    queue.getWaitingCount(),
    queue.getActiveCount(),
    queue.getCompletedCount(),
    queue.getFailedCount(),
  ]);
  return { waiting, active, completed, failed };
}

async function close() {
  if (_queue) await _queue.close();
}

module.exports = { scheduleRound, scheduleMatch, getQueueStats, close };
