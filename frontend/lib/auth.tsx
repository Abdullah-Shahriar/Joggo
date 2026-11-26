"use client";

import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useState, type ReactNode } from "react";

import { apiRequest } from "./api";
import type { AuthUser } from "./types";

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  refetchUser: () => Promise<void>;
  setUser: (user: AuthUser | null) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function AuthStateProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<AuthUser | null>({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      try {
        return await apiRequest<AuthUser>("/me", {
          redirectOn401: false,
          silentErrorToast: true,
        });
      } catch {
        return null;
      }
    },
    staleTime: 60_000,
    retry: false,
  });

  const setUser = (nextUser: AuthUser | null) => {
    queryClient.setQueryData(["auth", "me"], nextUser);
  };

  const refetchUser = async () => {
    await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
  };

  const logout = async () => {
    try {
      await apiRequest("/auth/logout", {
        method: "POST",
        redirectOn401: false,
        silentErrorToast: true,
      });
    } finally {
      queryClient.clear();
      queryClient.setQueryData(["auth", "me"], null);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user: data ?? null,
        isLoading,
        refetchUser,
        setUser,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthStateProvider>{children}</AuthStateProvider>
    </QueryClientProvider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside AppProviders");
  }
  return ctx;
}
