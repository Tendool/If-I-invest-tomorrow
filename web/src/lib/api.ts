import type {
  ActionResponse,
  AppState,
  AssetDetail,
  AssetRow,
  BacktestData,
  ChatEvent,
  FrontierData,
  HealthData,
  MarketData,
  MCData,
  ModelsData,
  PlanData,
  Profile,
  StrategiesData,
  StressData,
  TimingData,
  WalletData,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("Cannot reach the API server. Is it running on " + API_BASE + "?", 0);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(String(detail), res.status);
  }
  return (await res.json()) as T;
}

const post = <T,>(path: string, body: unknown = {}) =>
  req<T>(path, { method: "POST", body: JSON.stringify(body) });

const slug = (s: string) => s.toLowerCase().replace(/\s+/g, "-");

export const api = {
  health: () => req<{ status: string; llm: string; llm_available: boolean }>("/api/health"),
  state: () => req<AppState>("/api/state"),
  setProfile: (p: Partial<Profile>) => post<AppState>("/api/profile", p),
  setAutonomy: (mode: "auto" | "ask") => post<AppState>("/api/autonomy", { mode }),
  setAutopilot: (on: boolean) => post<AppState>("/api/autopilot", { on }),
  plan: () => post<{ strategies: StrategiesData; state: AppState }>("/api/plan"),
  planFor: (strategy: string) => req<PlanData>(`/api/plan/${slug(strategy)}`),
  monteCarlo: (strategy: string) => req<MCData>(`/api/montecarlo/${slug(strategy)}`),
  stress: (strategy: string) => req<StressData>(`/api/stress/${slug(strategy)}`),
  timing: (strategy: string) => req<TimingData>(`/api/timing/${slug(strategy)}`),
  backtest: (years: number) => req<BacktestData>(`/api/backtest?years=${years}`),
  frontier: () => req<FrontierData>("/api/frontier"),
  market: () => req<MarketData>("/api/market"),
  correlation: () => req<{ labels: string[]; matrix: number[][] }>("/api/correlation"),
  assets: () => req<AssetRow[]>("/api/assets"),
  asset: (ticker: string) => req<AssetDetail>(`/api/assets/${encodeURIComponent(ticker)}`),
  models: () => req<ModelsData>("/api/models"),
  wallet: () => req<WalletData>("/api/wallet"),
  walletHealth: () => req<HealthData>("/api/wallet/health"),
  invest: (strategy?: string) => post<ActionResponse>("/api/wallet/invest", { strategy }),
  trade: (b: { side: "BUY" | "SELL"; asset: string; quantity?: number; amount_rs?: number }) =>
    post<ActionResponse>("/api/wallet/trade", b),
  rebalance: (strategy?: string) => post<ActionResponse>("/api/wallet/rebalance", { strategy }),
  autoManage: () => post<ActionResponse>("/api/wallet/auto-manage"),
  confirm: () => post<{ wallet: WalletData; state: AppState }>("/api/wallet/confirm"),
  cancel: () => post<{ wallet: WalletData; state: AppState }>("/api/wallet/cancel"),
  addFunds: (amount: number) => post<{ wallet: WalletData; state: AppState }>("/api/wallet/funds", { amount }),
  resetWallet: () => post<{ wallet: WalletData; state: AppState }>("/api/wallet/reset"),
  autopilotRun: () => post<ActionResponse>("/api/autopilot/run"),
  refreshData: () => post<ActionResponse>("/api/data/refresh"),
  chatReset: () => post<{ ok: boolean }>("/api/chat/reset"),
};

/** POST /api/chat and parse the server-sent events stream. */
export async function streamChat(
  message: string,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
      signal,
    });
  } catch {
    throw new ApiError("Cannot reach the API server.", 0);
  }
  if (!res.ok || !res.body) throw new ApiError(`Chat failed (${res.status})`, res.status);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (line) onEvent(JSON.parse(line.slice(6)) as ChatEvent);
    }
  }
}
