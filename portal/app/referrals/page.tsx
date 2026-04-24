import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import NavBar from "@/components/NavBar";
import CopyButton from "@/components/CopyButton";

export default async function ReferralsPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/");

  const [{ data: profile }, { data: reg }] = await Promise.all([
    supabase.from("users").select("display_name").eq("id", user.id).single(),
    supabase.from("registrations").select("id, referral_code, referred_by").eq("email", user.email!).single(),
  ]);

  let referrals: any[] = [];
  if (reg) {
    const { data } = await supabase
      .from("referrals")
      .select("created_at, referrals_referee_id_fkey:registrations!referee_id(email, university, created_at)")
      .eq("referrer_id", reg.id)
      .order("created_at", { ascending: false });
    referrals = data ?? [];
  }

  const referralLink = `https://tally.so/r/b5OREg?ref=${reg?.referral_code ?? ""}`;

  return (
    <>
      <NavBar displayName={profile?.display_name} />
      <main className="max-w-5xl mx-auto px-4 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white">Referrals</h1>
          <p className="text-[#666] text-sm mt-1">
            Invite friends to compete — track who signed up through your link
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">

            {/* Stat */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-5">
                <p className="text-xs text-[#666] uppercase tracking-wide mb-2">Friends referred</p>
                <p className="text-3xl font-bold text-white">{referrals.length}</p>
              </div>
              <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-5">
                <p className="text-xs text-[#666] uppercase tracking-wide mb-2">Your code</p>
                <p className="text-3xl font-bold text-green-400 font-mono">
                  {reg?.referral_code ?? "—"}
                </p>
              </div>
            </div>

            {/* Referral list */}
            {referrals.length === 0 ? (
              <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-10 text-center">
                <div className="text-3xl mb-3">🤝</div>
                <h2 className="text-base font-semibold text-white mb-2">No referrals yet</h2>
                <p className="text-sm text-[#666]">
                  Share your link and get your friends building bots.
                </p>
              </div>
            ) : (
              <div className="bg-[#111] border border-[#1e1e1e] rounded-xl overflow-hidden">
                <div className="grid grid-cols-12 px-6 py-3 border-b border-[#1e1e1e] text-xs text-[#555] uppercase tracking-wide">
                  <div className="col-span-6">Email</div>
                  <div className="col-span-3">University</div>
                  <div className="col-span-3 text-right">Joined</div>
                </div>
                {referrals.map((r, i) => {
                  const referee = r.referrals_referee_id_fkey;
                  return (
                    <div
                      key={i}
                      className={`grid grid-cols-12 px-6 py-4 border-b border-[#0f0f0f] items-center text-sm ${
                        i % 2 === 0 ? "" : "bg-[#0d0d0d]"
                      }`}
                    >
                      <div className="col-span-6 text-[#aaa] truncate">
                        {referee?.email ?? "—"}
                      </div>
                      <div className="col-span-3 text-[#555] truncate">
                        {referee?.university ?? "—"}
                      </div>
                      <div className="col-span-3 text-right text-[#444] text-xs">
                        {referee?.created_at
                          ? new Date(referee.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
                          : "—"}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Share panel */}
          <div className="space-y-4">
            <div className="bg-[#0f1a0f] border border-[#1a3a1a] rounded-xl p-5">
              <p className="text-xs text-[#4a9a4a] uppercase tracking-wide mb-4">Your referral link</p>
              <p className="text-xs text-[#4a9a4a] font-mono break-all mb-4">{referralLink}</p>
              <CopyButton text={referralLink} />
            </div>

            <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-5">
              <p className="text-xs text-[#666] uppercase tracking-wide mb-3">Share</p>
              <div className="space-y-2">
                <a
                  href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(
                    `Building a poker bot for Fullhouse Hackathon 🃏 Compete online on 1 June 2026, finals in person at UCL East on 5 June — £4,000 prize pool. Use my link: ${referralLink}`
                  )}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 text-xs text-[#666] hover:text-white transition-colors py-1"
                >
                  <span>Share on X / Twitter</span>
                  <span className="text-[#333]">↗</span>
                </a>
                <a
                  href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(referralLink)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 text-xs text-[#666] hover:text-white transition-colors py-1"
                >
                  <span>Share on LinkedIn</span>
                  <span className="text-[#333]">↗</span>
                </a>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
