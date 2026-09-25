"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "./session";

/** Redirects unauthenticated visitors to /login and reports loading state. */
export function useAuthGuard() {
  const { user, loading, health } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  return {
    user,
    health,
    loading,
    authorized: !loading && Boolean(user),
  };
}
