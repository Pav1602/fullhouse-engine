import { createClient } from "@/lib/supabase/server";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/dashboard";

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      // Check if first login (no display_name set)
      const { data: { user } } = await supabase.auth.getUser();
      const { data: profile } = await supabase
        .from("users")
        .select("display_name")
        .eq("id", user?.id)
        .single();

      const isNewUser = !profile?.display_name ||
        profile.display_name === user?.email?.split("@")[0];

      return NextResponse.redirect(
        new URL(isNewUser ? "/onboarding" : next, origin)
      );
    }
  }

  return NextResponse.redirect(new URL("/?error=auth", origin));
}
