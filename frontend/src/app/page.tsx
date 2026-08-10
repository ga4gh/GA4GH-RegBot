import { AuthGuard } from "@/components/regbot/auth-guard";

export default function Home() {
  return <AuthGuard />;
}
