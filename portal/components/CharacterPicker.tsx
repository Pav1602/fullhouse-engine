/**
 * CharacterPicker — grid of robot colours + hats, saves to public.users.
 *
 * Drop this anywhere (onboarding page, dashboard settings panel, a new
 * /profile route). It reads current avatar/hat from the `users` row and
 * updates it on every click.
 *
 * Expects @/lib/supabase/client.ts exporting `createClient()` — which your
 * portal already has.
 */

"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import {
  PixelRobot,
  AVATAR_KEYS,
  HAT_KEYS,
  HAT_LABELS,
  type AvatarKey,
  type HatKey,
} from "./PixelRobot";

interface Props {
  userId: string;
  initialAvatar?: AvatarKey;
  initialHat?: HatKey;
  onChange?: (avatar: AvatarKey, hat: HatKey) => void;
}

export default function CharacterPicker({
  userId,
  initialAvatar = "robot_1",
  initialHat = "none",
  onChange,
}: Props) {
  const supabase = createClient();
  const [avatar, setAvatar] = useState<AvatarKey>(initialAvatar);
  const [hat, setHat] = useState<HatKey>(initialHat);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  async function save(next: { avatar?: AvatarKey; hat?: HatKey }) {
    const newAvatar = next.avatar ?? avatar;
    const newHat = next.hat ?? hat;
    setSaving(true);
    const { error } = await supabase
      .from("users")
      .update({ avatar_key: newAvatar, hat_key: newHat })
      .eq("id", userId);
    setSaving(false);
    if (error) {
      console.error("[CharacterPicker] save error:", error.message);
      return;
    }
    setSavedAt(Date.now());
    onChange?.(newAvatar, newHat);
  }

  function pickAvatar(k: AvatarKey) {
    setAvatar(k);
    void save({ avatar: k });
  }
  function pickHat(k: HatKey) {
    setHat(k);
    void save({ hat: k });
  }

  return (
    <div className="w-full max-w-xl">
      {/* Preview */}
      <div className="flex items-center gap-6 rounded-2xl border border-neutral-800 bg-neutral-900/60 p-6">
        <div className="shrink-0 rounded-xl bg-neutral-950 p-3">
          <PixelRobot avatar={avatar} hat={hat} size={120} />
        </div>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-white">Your character</h2>
          <p className="mt-1 text-sm text-neutral-400">
            Shown next to your bot on the leaderboard and match replays.
          </p>
          <p className="mt-2 text-xs text-neutral-500">
            {saving ? "Saving…" : savedAt ? "Saved." : "Click a robot or hat to change."}
          </p>
        </div>
      </div>

      {/* Robot colours */}
      <section className="mt-6">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.08em] text-neutral-500">
          Robot
        </h3>
        <div className="grid grid-cols-4 gap-3 sm:grid-cols-8">
          {AVATAR_KEYS.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => pickAvatar(k)}
              aria-pressed={avatar === k}
              className={`group flex items-center justify-center rounded-xl border p-2 transition
                ${avatar === k
                  ? "border-emerald-400 bg-emerald-400/10"
                  : "border-neutral-800 bg-neutral-900/60 hover:border-neutral-600"}`}
            >
              <PixelRobot avatar={k} hat="none" size={56} />
            </button>
          ))}
        </div>
      </section>

      {/* Hats */}
      <section className="mt-6">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.08em] text-neutral-500">
          Hat
        </h3>
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
          {HAT_KEYS.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => pickHat(k)}
              aria-pressed={hat === k}
              className={`flex flex-col items-center rounded-xl border p-2 transition
                ${hat === k
                  ? "border-emerald-400 bg-emerald-400/10"
                  : "border-neutral-800 bg-neutral-900/60 hover:border-neutral-600"}`}
            >
              <PixelRobot avatar={avatar} hat={k} size={56} />
              <span className="mt-1 text-[10px] uppercase tracking-wider text-neutral-500">
                {HAT_LABELS[k]}
              </span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

/**
 * Small wrapper that fetches the current user + profile row and renders
 * the picker. Use this if you want a fully plug-and-play component.
 */
export function CharacterPickerForCurrentUser() {
  const supabase = createClient();
  const [state, setState] = useState<{
    userId: string;
    avatar: AvatarKey;
    hat: HatKey;
  } | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      const { data: auth } = await supabase.auth.getUser();
      const uid = auth.user?.id;
      if (!uid) return;
      const { data } = await supabase
        .from("users")
        .select("avatar_key, hat_key")
        .eq("id", uid)
        .maybeSingle();
      if (!alive) return;
      setState({
        userId: uid,
        avatar: (data?.avatar_key as AvatarKey) ?? "robot_1",
        hat: (data?.hat_key as HatKey) ?? "none",
      });
    })();
    return () => {
      alive = false;
    };
  }, [supabase]);

  if (!state) {
    return (
      <div className="h-48 w-full animate-pulse rounded-2xl border border-neutral-800 bg-neutral-900/40" />
    );
  }
  return (
    <CharacterPicker
      userId={state.userId}
      initialAvatar={state.avatar}
      initialHat={state.hat}
    />
  );
}
