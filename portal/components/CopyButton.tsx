"use client";

import { useState } from "react";

export default function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button
      onClick={copy}
      className={`w-full text-sm font-medium py-2.5 rounded-lg border transition-colors ${
        copied
          ? "text-green-400 bg-green-400/10 border-green-400/20"
          : "text-[#888] bg-[#111] border-[#2a2a2a] hover:text-white hover:border-[#444]"
      }`}
    >
      {copied ? "✓ Copied!" : "Copy link"}
    </button>
  );
}
