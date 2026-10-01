"use client";

import * as React from "react";
import { toast } from "sonner";
import { api, ApiError } from "./api";
import type { ActionResponse, AppState, WalletData } from "./types";

interface Ctx {
  state: AppState | null;
  wallet: WalletData | null;
  error: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
  setState: (s: AppState) => void;
  setWallet: (w: WalletData) => void;
  /** apply the wallet + state returned by an action endpoint */
  apply: (r: { wallet?: WalletData; state?: AppState }) => void;
  /** run an async action with toast error handling */
  run: <T>(fn: () => Promise<T>, okMsg?: string) => Promise<T | undefined>;
  /** show a toast summarising an executed/staged action */
  announce: (r: ActionResponse) => void;
}

const AppCtx = React.createContext<Ctx | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<AppState | null>(null);
  const [wallet, setWallet] = React.useState<WalletData | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  const refresh = React.useCallback(async () => {
    try {
      const [s, w] = await Promise.all([api.state(), api.wallet()]);
      setState(s);
      setWallet(w);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    // initial data fetch on mount
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  const apply = React.useCallback((r: { wallet?: WalletData; state?: AppState }) => {
    if (r.wallet) setWallet(r.wallet);
    if (r.state) setState(r.state);
  }, []);

  const run = React.useCallback(async <T,>(fn: () => Promise<T>, okMsg?: string) => {
    try {
      const out = await fn();
      if (okMsg) toast.success(okMsg);
      return out;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
      return undefined;
    }
  }, []);

  const announce = React.useCallback(
    (r: ActionResponse) => {
      apply(r);
      const res = r.result as { status?: string; error?: string; message?: string };
      if (res.error) toast.error(res.error);
      else if (res.status?.startsWith("EXECUTED")) toast.success("Orders executed with demo money");
      else if (res.status?.startsWith("STAGED")) toast.info("Orders staged - confirm them in the wallet");
      else toast.message(res.status ?? res.message ?? "Done");
    },
    [apply],
  );

  return (
    <AppCtx.Provider value={{ state, wallet, error, loading, refresh, setState, setWallet, apply, run, announce }}>
      {children}
    </AppCtx.Provider>
  );
}

export function useApp() {
  const c = React.useContext(AppCtx);
  if (!c) throw new Error("useApp must be used inside <AppProvider>");
  return c;
}
