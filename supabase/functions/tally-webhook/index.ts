/**
 * Fullhouse — Tally Registration Webhook
 *
 * Receives POST from Tally when someone submits the registration form.
 * 1. Parses fields (email, name, university, course, CV)
 * 2. Handles referral code from ?ref= query param
 * 3. Saves to registrations table
 * 4. Resolves referral relationship if applicable
 * 5. Sends confirmation email via Resend with referral link + portal magic link
 *
 * Deploy:
 *   supabase functions deploy tally-webhook --no-verify-jwt
 *
 * Env vars required (set in Supabase dashboard → Edge Functions → Secrets):
 *   RESEND_API_KEY      — from resend.com
 *   TALLY_SIGNING_SECRET — from Tally webhook settings (optional but recommended)
 *   SITE_URL            — e.g. https://fullhousehackathon.com
 *   PORTAL_URL          — e.g. https://portal.fullhousehackathon.com
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL    = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const RESEND_API_KEY  = Deno.env.get("RESEND_API_KEY")!;
const TALLY_SECRET    = Deno.env.get("TALLY_SIGNING_SECRET") ?? "";
const SITE_URL        = Deno.env.get("SITE_URL") ?? "https://fullhousehackathon.com";
const PORTAL_URL      = Deno.env.get("PORTAL_URL") ?? "https://portal.fullhousehackathon.com";
const FROM_EMAIL      = "Fullhouse Hackathon <noreply@fullhousehackathon.com>";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getField(fields: any[], label: string): string {
  const f = fields.find(
    (f: any) => f.label?.toLowerCase() === label.toLowerCase()
  );
  if (!f) return "";
  // Tally can return value as string, array, or object
  if (Array.isArray(f.value)) return f.value[0] ?? "";
  if (typeof f.value === "object" && f.value !== null) return JSON.stringify(f.value);
  return String(f.value ?? "");
}

function getFileUrl(fields: any[], label: string): string {
  const f = fields.find(
    (f: any) => f.label?.toLowerCase() === label.toLowerCase()
  );
  if (!f || !f.value) return "";
  if (Array.isArray(f.value)) return f.value[0]?.url ?? "";
  if (typeof f.value === "object") return f.value?.url ?? "";
  return "";
}

async function sendEmail(to: string, subject: string, html: string) {
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ from: FROM_EMAIL, to, subject, html }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Resend error ${res.status}: ${body}`);
  }
  return res.json();
}

function confirmationEmailHtml(params: {
  name: string;
  referralCode: string;
  referralLink: string;
  magicLink: string;
}): string {
  const { name, referralCode, referralLink, magicLink } = params;
  const firstName = name?.split(" ")[0] || "there";

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>You're registered — Fullhouse Hackathon</title>
</head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:'Inter',system-ui,sans-serif;color:#e5e5e5;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:48px 16px;">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#111;border-radius:12px;border:1px solid #222;">

          <!-- Header -->
          <tr>
            <td style="padding:40px 40px 32px;border-bottom:1px solid #1e1e1e;">
              <p style="margin:0;font-size:13px;letter-spacing:0.1em;text-transform:uppercase;color:#666;">
                FULLHOUSE HACKATHON · 1 JUNE 2026
              </p>
              <h1 style="margin:12px 0 0;font-size:28px;font-weight:700;color:#fff;line-height:1.2;">
                You're in, ${firstName}. ♠
              </h1>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:32px 40px;">
              <p style="margin:0 0 20px;font-size:16px;line-height:1.6;color:#aaa;">
                Your registration for the UK's first quantitative poker bot competition
                is confirmed. One Canada Square, London — 1 June 2026.
              </p>

              <p style="margin:0 0 8px;font-size:14px;color:#666;">
                Prize pool: <strong style="color:#fff;">£3,000</strong> &nbsp;·&nbsp;
                Lead sponsor: <strong style="color:#fff;">Quadrature Capital</strong>
              </p>

              <!-- Portal access -->
              <table width="100%" cellpadding="0" cellspacing="0" style="margin:32px 0;background:#1a1a1a;border-radius:8px;border:1px solid #2a2a2a;">
                <tr>
                  <td style="padding:24px;">
                    <p style="margin:0 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:0.08em;color:#666;">
                      PARTICIPANT PORTAL
                    </p>
                    <p style="margin:0 0 20px;font-size:14px;color:#aaa;line-height:1.5;">
                      Submit your bot, run test matches, and track the leaderboard.
                      Click below — you'll be signed in automatically, no password needed.
                    </p>
                    <a href="${magicLink}"
                       style="display:inline-block;padding:12px 28px;background:#fff;color:#000;font-weight:600;font-size:14px;border-radius:6px;text-decoration:none;">
                      Access the portal →
                    </a>
                    <p style="margin:12px 0 0;font-size:12px;color:#555;">
                      Link expires in 24 hours. You can request a new one at ${PORTAL_URL}
                    </p>
                  </td>
                </tr>
              </table>

              <!-- Referral -->
              <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 32px;background:#0f1a0f;border-radius:8px;border:1px solid #1a3a1a;">
                <tr>
                  <td style="padding:24px;">
                    <p style="margin:0 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:0.08em;color:#4a9a4a;">
                      REFER A FRIEND
                    </p>
                    <p style="margin:0 0 16px;font-size:14px;color:#aaa;line-height:1.5;">
                      Know someone who'd build a great bot? Share your link.
                    </p>
                    <p style="margin:0 0 16px;font-size:13px;font-family:monospace;background:#0a0a0a;border:1px solid #1e1e1e;border-radius:4px;padding:10px 14px;color:#4a9a4a;word-break:break-all;">
                      ${referralLink}
                    </p>
                    <p style="margin:0;font-size:12px;color:#555;">
                      Your referral code: <strong style="color:#888;">${referralCode}</strong>
                    </p>
                  </td>
                </tr>
              </table>

              <!-- What's next -->
              <p style="margin:0 0 12px;font-size:15px;font-weight:600;color:#fff;">What happens next</p>
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="padding:0 0 10px;">
                    <span style="color:#666;font-size:13px;">📅 May 2026</span>
                    <span style="color:#aaa;font-size:14px;margin-left:12px;">Portal opens — submit your first bot</span>
                  </td>
                </tr>
                <tr>
                  <td style="padding:0 0 10px;">
                    <span style="color:#666;font-size:13px;">🃏 1 Jun</span>
                    <span style="color:#aaa;font-size:14px;margin-left:12px;">Day 1 — Swiss qualifier, top 32 advance</span>
                  </td>
                </tr>
                <tr>
                  <td style="padding:0 0 10px;">
                    <span style="color:#666;font-size:13px;">🔧 2 Jun</span>
                    <span style="color:#aaa;font-size:14px;margin-left:12px;">Patch window — update your bot overnight</span>
                  </td>
                </tr>
                <tr>
                  <td>
                    <span style="color:#666;font-size:13px;">🏆 3 Jun</span>
                    <span style="color:#aaa;font-size:14px;margin-left:12px;">Finale — live-streamed bracket, £3,000 prize</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 40px;border-top:1px solid #1e1e1e;">
              <p style="margin:0;font-size:12px;color:#444;line-height:1.6;">
                Questions? Reply to this email or visit
                <a href="${SITE_URL}" style="color:#666;">${SITE_URL}</a><br/>
                Fullhouse Hackathon · One Canada Square · London E14 5AB
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  let body: any;
  try {
    body = await req.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }

  // Optional: verify Tally signature
  if (TALLY_SECRET) {
    const sig = req.headers.get("tally-signature") ?? "";
    // Tally uses HMAC-SHA256 — verify here if needed
    // For now we just log if missing
    if (!sig) console.warn("No Tally signature header received");
  }

  // Parse referral code from hidden field or query param
  // Tally can pass ref= via hidden field or URL param depending on setup
  const url         = new URL(req.url);
  const refFromUrl  = url.searchParams.get("ref") ?? "";

  // Extract fields from Tally payload
  // Tally sends: { data: { fields: [{ label, value, ... }] } }
  const fields: any[] = body?.data?.fields ?? [];

  const email      = getField(fields, "email")?.toLowerCase().trim();
  const name       = getField(fields, "name") ||
                     getField(fields, "full name") ||
                     getField(fields, "your name") || "";
  const university = getField(fields, "university") ||
                     getField(fields, "school") || "";
  const course     = getField(fields, "course") ||
                     getField(fields, "your course") ||
                     getField(fields, "degree") || "";
  const cvUrl      = getFileUrl(fields, "cv") ||
                     getFileUrl(fields, "upload cv") ||
                     getFileUrl(fields, "resume") || "";
  const refFromField = getField(fields, "ref") ||
                       getField(fields, "referral") ||
                       getField(fields, "referred by") || "";

  const referredBy = (refFromUrl || refFromField).toUpperCase().trim() || null;

  if (!email) {
    return new Response(JSON.stringify({ error: "No email in payload" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

  // Upsert registration (handle duplicate submissions gracefully)
  const { data: reg, error: regError } = await supabase
    .from("registrations")
    .upsert(
      { email, name, university, course, cv_url: cvUrl || null, referred_by: referredBy },
      { onConflict: "email", ignoreDuplicates: false }
    )
    .select()
    .single();

  if (regError) {
    console.error("Registration insert error:", regError);
    return new Response(JSON.stringify({ error: regError.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Resolve referral relationship
  if (referredBy) {
    const { data: referrer } = await supabase
      .from("registrations")
      .select("id")
      .eq("referral_code", referredBy)
      .single();

    if (referrer) {
      await supabase
        .from("referrals")
        .upsert(
          { referrer_id: referrer.id, referee_id: reg.id },
          { onConflict: "referrer_id,referee_id", ignoreDuplicates: true }
        );
    }
  }

  // Generate Supabase magic link for portal access
  let magicLink = PORTAL_URL; // fallback
  try {
    const { data: linkData, error: linkErr } = await supabase.auth.admin.generateLink({
      type: "magiclink",
      email,
      options: {
        redirectTo: `${PORTAL_URL}/onboarding`,
        data: {
          display_name: name,
          referral_code: reg.referral_code,
          university,
          course,
        },
      },
    });
    if (!linkErr && linkData?.properties?.action_link) {
      magicLink = linkData.properties.action_link;
      // Mark as invited
      await supabase
        .from("registrations")
        .update({ portal_invited: true })
        .eq("id", reg.id);
    }
  } catch (e) {
    console.error("Magic link error:", e);
  }

  // Send confirmation email
  const referralLink = `${SITE_URL}?ref=${reg.referral_code}`;
  try {
    await sendEmail(
      email,
      "You're registered — Fullhouse Hackathon ♠",
      confirmationEmailHtml({
        name,
        referralCode: reg.referral_code,
        referralLink,
        magicLink,
      })
    );
  } catch (e) {
    console.error("Email send error:", e);
    // Don't fail the whole request if email fails — registration is saved
  }

  return new Response(
    JSON.stringify({
      success: true,
      registration_id: reg.id,
      referral_code: reg.referral_code,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } }
  );
});
