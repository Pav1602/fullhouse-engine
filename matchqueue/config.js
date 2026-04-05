// Fullhouse Queue — shared config
// All queue names and job schemas live here so producer and workers stay in sync.

const QUEUE_NAMES = {
  MATCHES:  "fh:matches",   // match jobs (one per table)
  RESULTS:  "fh:results",   // completed match results waiting for ingestion
};

const JOB_TYPES = {
  RUN_MATCH: "run_match",
};

// Match job payload schema:
// {
//   match_id:    string      — unique, e.g. "t1_r2_table_007"
//   tournament:  string      — tournament identifier
//   round:       number      — swiss round number (1, 2, ...)
//   n_hands:     number      — hands to play (default 200)
//   bots: [                  — 2-9 entries
//     { bot_id: string, bot_path: string }
//   ]
// }

const DEFAULT_JOB_OPTIONS = {
  attempts:    3,                   // retry up to 3x on worker crash
  backoff: { type: "exponential", delay: 2000 },
  removeOnComplete: { count: 500 }, // keep last 500 completed for debugging
  removeOnFail:     { count: 200 },
};

// Redis connection — Upstash in prod, local in dev
const REDIS_CONFIG = {
  host: process.env.REDIS_HOST || "localhost",
  port: parseInt(process.env.REDIS_PORT || "6379"),
  password: process.env.REDIS_PASSWORD || undefined,
  tls: process.env.REDIS_TLS === "true" ? {} : undefined,
  maxRetriesPerRequest: null,  // required by BullMQ
};

module.exports = { QUEUE_NAMES, JOB_TYPES, DEFAULT_JOB_OPTIONS, REDIS_CONFIG };
