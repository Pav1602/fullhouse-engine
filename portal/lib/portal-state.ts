/**
 * Portal feature flags. Flip booleans here, no DB needed.
 */

// When false: the bot uploader is replaced with a "submissions opening soon" card.
// When true: uploader works normally.
export const SUBMISSIONS_OPEN = false;

// Shown to participants while submissions are locked.
export const SUBMISSIONS_OPEN_DATE_LABEL = "May 2026";

// Number of bots advancing from the qualifier to finals.
export const FINALISTS = 64;
