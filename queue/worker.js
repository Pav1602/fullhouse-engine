// Fullhouse Queue — Worker
// Pulls match jobs from Redis, runs match.py via subprocess, stores results.
// Run N of these in parallel: node worker.js
//
// Env vars:
//   CONCURRENCY     how many matches this worker runs in parallel (default 4)
//   USE_DOCKER      passed through to match.py (default false)
//   DATABASE_URL    Postgres connection string for result storage
//   REDIS_HOST/PORT/PASSWORD/TLS

const { Worker, MetricsTime } = require("bullmq");
const { spawn } = require("child_process");
const path = require("path");
const { QUEUE_NAMES, JOB_TYPES, REDIS_CONFIG } = require("./config");

const CONCURRENCY  = parseInt(process.env.CONCURRENCY  || "4");
const MATCH_SCRIPT = path.resolve(__dirname, "../sandbox/match.py");
const PYTHON       = process.env.PYTHON_BIN || "python3";

// ---------------------------------------------------------------------------
// Match runner — calls match.py as a subprocess
// ---------------------------------------------------------------------------

function runMatch(jobData) {
  return new Promise((resolve, reject) => {
    const { match_id, bots, n_hands } = jobData;

    // Build arg list:  match.py bot1.py bot2.py ... --hands N --match-id ID
    const botPaths = bots.map((b) => b.bot_path);
    const args = [
      MATCH_SCRIPT,
      ...botPaths,
      "--hands", String(n_hands),
      "--json",
      "--match-id", match_id,
    ];

    const env = {
      ...process.env,
      MATCH_ID:   match_id,
      USE_DOCKER: process.env.USE_DOCKER || "false",
    };

    const proc = spawn(PYTHON, args, { env });
    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (d) => (stdout += d));
    proc.stderr.on("data", (d) => (stderr += d));

    proc.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`match.py exited ${code}\n${stderr}`));
        return;
      }

      // match.py prints a summary to stdout. We need structured results.
      // In prod, match.py writes JSON to a file; we read it here.
      // For now, parse the chip delta lines from stdout as a fallback.
      try {
        const result = parseMatchOutput(stdout, match_id, bots);
        resolve(result);
      } catch (e) {
        reject(new Error(`Failed to parse match output: ${e.message}\n${stdout}`));
      }
    });

    proc.on("error", reject);
  });
}

function parseMatchOutput(stdout, match_id, bots) {
  // match.py --json prints a single JSON line to stdout
  const line = stdout.trim().split("\n").pop();
  const data = JSON.parse(line);

  const results = {};
  for (const bot_id of data.bot_ids || Object.keys(data.chip_delta)) {
    results[bot_id] = {
      final_stack: data.final_stacks[bot_id] ?? 0,
      chip_delta:  data.chip_delta[bot_id]   ?? 0,
    };
  }
  return { match_id: data.match_id, bots: Object.keys(results), results };
}

// ---------------------------------------------------------------------------
// Result storage — writes to Postgres via simple HTTP to your Next.js API
// Swap this for a direct pg call if you prefer.
// ---------------------------------------------------------------------------

async function storeResult(result) {
  const apiUrl = process.env.RESULTS_API_URL;
  if (!apiUrl) {
    // Dev mode: just log it
    console.log("[worker] Result:", JSON.stringify(result, null, 2));
    return;
  }

  const res = await fetch(`${apiUrl}/api/internal/match-result`, {
    method:  "POST",
    headers: { "Content-Type": "application/json",
                "x-internal-key": process.env.INTERNAL_API_KEY || "" },
    body: JSON.stringify(result),
  });

  if (!res.ok) {
    throw new Error(`API returned ${res.status}: ${await res.text()}`);
  }
}

// ---------------------------------------------------------------------------
// Worker
// ---------------------------------------------------------------------------

const worker = new Worker(
  QUEUE_NAMES.MATCHES,
  async (job) => {
    if (job.name !== JOB_TYPES.RUN_MATCH) {
      throw new Error(`Unknown job type: ${job.name}`);
    }

    const { match_id, tournament, round } = job.data;
    console.log(`[worker] Starting ${match_id} (attempt ${job.attemptsMade + 1})`);

    await job.updateProgress(10);

    const result = await runMatch(job.data);
    await job.updateProgress(90);

    await storeResult({ ...result, tournament, round });
    await job.updateProgress(100);

    console.log(`[worker] Completed ${match_id}`);
    return result;
  },
  {
    connection:  REDIS_CONFIG,
    concurrency: CONCURRENCY,
    metrics: { maxDataPoints: MetricsTime.ONE_WEEK },
  }
);

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

worker.on("completed", (job) => {
  console.log(`[worker] ✓ ${job.data.match_id}`);
});

worker.on("failed", (job, err) => {
  console.error(`[worker] ✗ ${job?.data?.match_id}: ${err.message}`);
});

worker.on("error", (err) => {
  console.error("[worker] Error:", err);
});

// Graceful shutdown
async function shutdown(signal) {
  console.log(`\n[worker] ${signal} received — draining...`);
  await worker.close();
  process.exit(0);
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT",  () => shutdown("SIGINT"));

console.log(
  `[worker] Started — concurrency=${CONCURRENCY}, queue=${QUEUE_NAMES.MATCHES}`
);
