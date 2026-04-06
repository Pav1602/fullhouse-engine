"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const [email, setEmail]     = useState("");
  const [sent, setSent]       = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim().toLowerCase(),
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
        shouldCreateUser: false, // only allow registered participants
      },
    });
    if (error) {
      // If user not found, give a friendly message
      if (error.message.includes("not found") || error.status === 422) {
        setError("No registration found for this email. Make sure you signed up at fullhousehackathon.com first.");
      } else {
        setError(error.message);
      }
    } else {
      setSent(true);
    }
    setLoading(false);
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">

        {/* Logo / header */}
        <div className="text-center mb-10">
          <div className="text-4xl mb-4">♠</div>
          <h1 className="text-2xl font-bold text-white">Fullhouse Portal</h1>
          <p className="text-sm text-[#666] mt-1">1 June 2026 · One Canada Square · London</p>
        </div>

        {sent ? (
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-8 text-center">
            <div className="text-3xl mb-4">📬</div>
            <h2 className="text-lg font-semibold text-white mb-2">Check your email</h2>
            <p className="text-sm text-[#888] leading-relaxed">
              We sent a sign-in link to <span className="text-white">{email}</span>.
              Click it to access your portal — no password needed.
            </p>
            <p className="text-xs text-[#555] mt-4">Link expires in 1 hour.</p>
            <button
              onClick={() => { setSent(false); setEmail(""); }}
              className="mt-6 text-xs text-[#555] hover:text-[#888] underline"
            >
              Use a different email
            </button>
          </div>
        ) : (
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-8">
            <h2 className="text-base font-semibold text-white mb-1">Sign in</h2>
            <p className="text-sm text-[#666] mb-6">
              Enter your registration email. We'll send you a magic link.
            </p>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs text-[#666] mb-1.5 uppercase tracking-wide">
                  Email address
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@university.ac.uk"
                  className="w-full bg-[#0a0a0a] border border-[#2a2a2a] rounded-lg px-4 py-3 text-white text-sm placeholder-[#444] focus:outline-none focus:border-[#555] transition-colors"
                />
              </div>
              {error && (
                <p className="text-xs text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-3">
                  {error}
                </p>
              )}
              <button
                type="submit"
                disabled={loading || !email}
                className="w-full bg-white text-black font-semibold text-sm py-3 rounded-lg hover:bg-[#e5e5e5] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {loading ? "Sending…" : "Send sign-in link →"}
              </button>
            </form>
            <p className="text-xs text-[#444] text-center mt-6">
              Not registered?{" "}
              <a
                href="https://fullhousehackathon.com"
                target="_blank"
                rel="noreferrer"
                className="text-[#666] hover:text-white underline transition-colors"
              >
                Sign up first
              </a>
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
