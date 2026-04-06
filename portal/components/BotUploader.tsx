"use client";

import { useState, useRef } from "react";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";

interface Props {
  userId: string;
  existingBot?: { id: string; bot_name: string; version: number };
}

export default function BotUploader({ userId, existingBot }: Props) {
  const router          = useRouter();
  const fileRef         = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [botName, setBotName] = useState(existingBot?.bot_name ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");
  const [success, setSuccess] = useState(false);

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.endsWith(".py")) { setError("File must be a .py file"); return; }
    if (f.size > 512 * 1024) { setError("File must be under 512 KB"); return; }
    setFile(f);
    setError("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setError("Please select a bot.py file"); return; }
    if (!botName.trim()) { setError("Bot name is required"); return; }
    setLoading(true);
    setError("");

    try {
      const supabase = createClient();
      const version  = (existingBot?.version ?? 0) + 1;
      const path     = `${userId}/bot_v${version}.py`;

      // Upload to Supabase Storage
      const { error: uploadErr } = await supabase.storage
        .from("bots")
        .upload(path, file, { upsert: true, contentType: "text/plain" });

      if (uploadErr) throw new Error(uploadErr.message);

      // Upsert bot record
      const { error: dbErr } = await supabase.from("bots").upsert({
        ...(existingBot?.id ? { id: existingBot.id } : {}),
        user_id:      userId,
        bot_name:     botName.trim(),
        storage_path: path,
        version,
        status:       "pending",
        error_message: null,
      });

      if (dbErr) throw new Error(dbErr.message);

      setSuccess(true);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      setTimeout(() => { setSuccess(false); router.refresh(); }, 2000);
    } catch (err: any) {
      setError(err.message ?? "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Bot name */}
      {!existingBot && (
        <div>
          <label className="block text-xs text-[#666] mb-1.5 uppercase tracking-wide">
            Bot name
          </label>
          <input
            type="text"
            value={botName}
            onChange={e => setBotName(e.target.value)}
            placeholder="TheSharknado"
            maxLength={32}
            minLength={2}
            className="w-full bg-[#0a0a0a] border border-[#2a2a2a] rounded-lg px-4 py-3 text-white text-sm placeholder-[#444] focus:outline-none focus:border-[#555] transition-colors"
          />
        </div>
      )}

      {/* File drop zone */}
      <div
        onClick={() => fileRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          file
            ? "border-green-500/40 bg-green-500/5"
            : "border-[#2a2a2a] hover:border-[#444] bg-[#0a0a0a]"
        }`}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".py"
          onChange={onFileChange}
          className="hidden"
        />
        {file ? (
          <div>
            <p className="text-green-400 font-medium text-sm">{file.name}</p>
            <p className="text-xs text-[#555] mt-1">{(file.size / 1024).toFixed(1)} KB</p>
          </div>
        ) : (
          <div>
            <p className="text-[#555] text-sm mb-1">Drop <code>bot.py</code> here or click to browse</p>
            <p className="text-xs text-[#444]">Max 512 KB · .py only</p>
          </div>
        )}
      </div>

      {error && (
        <p className="text-xs text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-3">
          {error}
        </p>
      )}

      {success && (
        <p className="text-xs text-green-400 bg-green-400/10 border border-green-400/20 rounded-lg px-4 py-3">
          ✓ Bot submitted! Validation running…
        </p>
      )}

      <button
        type="submit"
        disabled={loading || !file}
        className="w-full bg-white text-black font-semibold text-sm py-3 rounded-lg hover:bg-[#e5e5e5] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {loading ? "Uploading…" : existingBot ? `Submit update (v${(existingBot.version ?? 0) + 1})` : "Submit bot"}
      </button>
    </form>
  );
}
