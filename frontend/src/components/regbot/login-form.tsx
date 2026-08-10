"use client";

import { type FormEvent, useState } from "react";
import {
  ArrowRight,
  BookOpenCheck,
  Eye,
  Globe2,
  Loader2,
  LockKeyhole,
  ShieldCheck,
} from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { continueAsViewer, login } from "@/lib/api";

export function LoginForm() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState<"viewer" | "account" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading("account");
    setError(null);
    try {
      await login(username, password);
      router.replace("/");
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign in failed.");
    } finally {
      setLoading(null);
    }
  }

  async function onViewerEntry() {
    setLoading("viewer");
    setError(null);
    try {
      await continueAsViewer();
      router.replace("/");
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Viewer access failed.");
    } finally {
      setLoading(null);
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#f4f8fc] text-slate-950">
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-[radial-gradient(circle_at_12%_15%,rgba(79,174,220,0.18),transparent_30%),radial-gradient(circle_at_88%_78%,rgba(139,197,63,0.12),transparent_28%),linear-gradient(135deg,#f8fbfe_0%,#eef5fb_52%,#f9fbf7_100%)]"
      />
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-35 [background-image:linear-gradient(rgba(27,117,187,0.06)_1px,transparent_1px),linear-gradient(90deg,rgba(27,117,187,0.06)_1px,transparent_1px)] [background-size:40px_40px] [mask-image:linear-gradient(to_bottom,black,transparent_85%)]"
      />

      <div className="relative mx-auto grid min-h-screen w-full max-w-7xl items-center gap-8 px-5 py-7 sm:gap-10 sm:px-8 sm:py-10 lg:grid-cols-[1.08fr_0.92fr] lg:gap-16 lg:px-12">
        <section className="mx-auto w-full max-w-2xl lg:mx-0">
          <div className="mb-7 inline-flex rounded-2xl border border-white/90 bg-white/85 p-5 shadow-[0_18px_50px_-30px_rgba(15,74,122,0.55)] backdrop-blur-sm sm:mb-10 sm:p-6">
            <Image
              src="/global-alliance-logo.svg"
              alt="Global Alliance for Genomics and Health"
              width={384}
              height={100}
              priority
              className="h-auto w-[17rem] sm:w-[22rem]"
            />
          </div>

          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-[#1b75bb]/15 bg-[#1b75bb]/8 px-3 py-1.5 text-xs font-semibold tracking-wide text-[#1769a6] uppercase">
            <ShieldCheck className="size-3.5" />
            Regulatory &amp; Ethics Work Stream
          </div>

          <h1 className="max-w-xl text-4xl leading-[1.05] font-semibold tracking-[-0.035em] text-slate-950 sm:text-5xl lg:text-6xl">
            RegBot
            <span className="mt-2 block text-2xl leading-tight font-medium tracking-[-0.02em] text-slate-600 sm:text-3xl lg:text-4xl">
              Regulatory navigation, grounded in evidence.
            </span>
          </h1>
          <p className="mt-4 max-w-xl text-base leading-7 text-slate-600 sm:mt-6 sm:text-lg">
            Explore policy sources across jurisdictions, review citation-linked guidance,
            and prepare questions for expert oversight.
          </p>

          <div className="mt-9 hidden gap-3 sm:grid sm:grid-cols-3">
            {[
              {
                icon: BookOpenCheck,
                title: "Source-linked",
                detail: "Trace guidance to corpus evidence.",
              },
              {
                icon: Globe2,
                title: "Cross-border",
                detail: "Review regional policy context.",
              },
              {
                icon: ShieldCheck,
                title: "Role-protected",
                detail: "Management stays admin-only.",
              },
            ].map(({ icon: Icon, title, detail }) => (
              <div
                key={title}
                className="rounded-2xl border border-white/90 bg-white/65 p-4 shadow-[0_12px_35px_-28px_rgba(15,74,122,0.8)] backdrop-blur-sm"
              >
                <Icon className="mb-3 size-5 text-[#1b75bb]" />
                <p className="text-sm font-semibold text-slate-800">{title}</p>
                <p className="mt-1 text-xs leading-5 text-slate-500">{detail}</p>
              </div>
            ))}
          </div>

          <p className="mt-8 hidden max-w-xl text-xs leading-5 text-slate-500 sm:block">
            RegBot supports regulatory navigation and human review. It does not provide
            legal advice or make compliance decisions.
          </p>
        </section>

        <section className="mx-auto w-full max-w-[31rem] lg:mx-0 lg:justify-self-end">
          <Card className="gap-0 border-white/90 bg-white/92 py-0 shadow-[0_28px_80px_-36px_rgba(15,74,122,0.5)] ring-1 ring-slate-900/5 backdrop-blur-xl">
            <CardHeader className="gap-2 border-b border-slate-100 px-6 py-6 sm:px-8 sm:py-7">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="flex size-11 items-center justify-center rounded-2xl bg-[#1b75bb] text-white shadow-lg shadow-[#1b75bb]/20">
                  <ShieldCheck className="size-5" />
                </div>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 ring-1 ring-emerald-600/10">
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                  Read-only access available
                </span>
              </div>
              <CardTitle className="text-2xl tracking-tight">Welcome to RegBot</CardTitle>
              <CardDescription className="hidden text-sm leading-6 sm:block">
                Use public access to explore the workspace, or sign in with an authorised
                account.
              </CardDescription>
            </CardHeader>

            <CardContent className="space-y-6 px-6 py-6 sm:px-8 sm:py-7">
              <div className="rounded-2xl border border-[#1b75bb]/15 bg-[#1b75bb]/[0.045] p-4">
                <div className="mb-3 flex items-start gap-3">
                  <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl bg-white text-[#1b75bb] shadow-sm ring-1 ring-[#1b75bb]/10">
                    <Eye className="size-4" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-900">
                      Public user workspace
                    </p>
                    <p className="mt-1 text-xs leading-5 text-slate-600">
                      Search, review, check, and chat. No account is required, and corpus
                      changes remain locked.
                    </p>
                  </div>
                </div>
                <Button
                  type="button"
                  className="h-11 w-full rounded-xl bg-[#1168ad] shadow-lg shadow-[#1b75bb]/15 hover:bg-[#0d5996]"
                  onClick={onViewerEntry}
                  disabled={loading !== null}
                >
                  {loading === "viewer" ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Eye className="size-4" />
                  )}
                  Continue as public user
                  {loading !== "viewer" ? <ArrowRight className="ml-auto size-4" /> : null}
                </Button>
              </div>

              <div className="flex items-center gap-3" aria-hidden="true">
                <div className="h-px flex-1 bg-slate-200" />
                <span className="text-xs font-medium text-slate-400">Authorised account</span>
                <div className="h-px flex-1 bg-slate-200" />
              </div>

              <form className="space-y-4" onSubmit={onSubmit}>
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                  <LockKeyhole className="size-4 text-slate-500" />
                  Administrator or named reviewer
                </div>
                <div className="space-y-2">
                  <Label htmlFor="username">Username</Label>
                  <Input
                    id="username"
                    name="username"
                    autoComplete="username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    className="h-10 rounded-xl bg-white"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className="h-10 rounded-xl bg-white"
                    required
                  />
                </div>
                {error ? (
                  <Alert variant="destructive" className="rounded-xl">
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                ) : null}
                <Button
                  type="submit"
                  variant="outline"
                  className="h-10 w-full rounded-xl border-slate-200 bg-white hover:bg-slate-50"
                  disabled={loading !== null}
                >
                  {loading === "account" ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <LockKeyhole className="size-4" />
                  )}
                  Sign in securely
                </Button>
              </form>

              <div className="flex items-center justify-center gap-2 border-t border-slate-100 pt-5 text-xs text-slate-500">
                <ShieldCheck className="size-3.5 text-[#1b75bb]" />
                Role-based access protects corpus management
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}
