"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";

import { RegBotApp } from "@/components/regbot/regbot-app";
import { ApiError, getCurrentUser, type AuthUser } from "@/lib/api";

export function AuthGuard() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getCurrentUser()
      .then((current) => {
        if (!cancelled) setUser(current);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        if (reason instanceof ApiError && reason.status === 401) {
          router.replace("/login");
          return;
        }
        setError(reason instanceof Error ? reason.message : "Could not verify session.");
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center p-6">
        <div className="border-destructive/40 bg-destructive/5 max-w-lg rounded-xl border p-5">
          <h1 className="font-semibold">Authentication service unavailable</h1>
          <p className="text-muted-foreground mt-2 whitespace-pre-line text-sm">{error}</p>
        </div>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="text-muted-foreground flex min-h-screen items-center justify-center gap-2">
        <Loader2 className="size-4 animate-spin" />
        Checking session…
      </main>
    );
  }

  return <RegBotApp user={user} />;
}
