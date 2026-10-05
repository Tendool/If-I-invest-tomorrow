export type Risk = "low" | "medium" | "high";
export type Autonomy = "auto" | "ask";

export interface Profile {
  amount: number;
  horizon_years: number;
  risk: Risk;
  target_return_pct: number;
  preferred_sectors: string[];
}

export interface WalletSummary {
  cash: number;
  total_value: number;
  pnl: number;
  pnl_pct: number;
  starting_cash: number;
  pending: boolean;
}

export interface Ticker {
  nifty: number;
  nifty_1d: number;
  vix: number;
  usdinr: number;
  brent: number;
  banknifty: number | null;
}

export interface TapeItem {
  label: string;
  value: number;
  change: number;
  kind: string;
  fmt: "num" | "usd";
}

export interface AppState {
  as_of: string;
  ticker?: Ticker;
  tape?: TapeItem[];
  profile: Profile;
  profile_set: boolean;
  autonomy: Autonomy;
  autopilot: boolean;
  strategies: string[];
  regime: string;
  llm: string;
  sectors: string[];
  recommended: string | null;
  wallet: WalletSummary;
}

export interface MCStats {
  exp_return_mean: number;
  exp_return_median: number;
  exp_volatility: number;
  prob_positive: number;
  prob_beat_riskfree: number;
  prob_target: number | null;
  prob_loss_gt_10: number;
  expected_final: number;
  median_final: number;
  best_case_p95: number;
  worst_case_p5: number;
  absolute_best: number;
  absolute_worst: number;
  var95_horizon: number;
  cvar95_horizon: number;
  var95_1y: number;
  cvar95_1y: number;
  prob_loss_1y: number;
  exp_max_drawdown: number;
  p95_max_drawdown: number;
  median_max_drawdown: number;
}

export interface FanPoint {
  year: number;
  p5: number;
  p25: number;
  p50: number;
  p75: number;
  p95: number;
}

export interface MC {
  years: number;
  amount: number;
  target: number | null;
  n_paths: number;
  stats: MCStats;
  fan: FanPoint[];
  hist?: { x: number; pct: number }[];
  paths?: number[][];
  grid_years?: number[];
}

export interface WeightRow {
  symbol: string;
  ticker: string;
  name: string;
  sector: string;
  asset_class: string;
  weight: number;
}

export interface StressRow {
  scenario: string;
  portfolio_return: number;
  pnl: number;
  survives: boolean;
  top_hits: string;
}

export interface Evaluation {
  strategy: string;
  blurb: string;
  recommended: boolean;
  weights: WeightRow[];
  stats: { exp_return: number; volatility: number; sharpe: number; beta: number; near_term_vol?: number };
  mc: MC;
  stress: StressRow[];
  breaches: string[];
  within_limits: boolean;
  n_holdings: number;
}

export interface PlanRow {
  symbol: string;
  ticker: string;
  name: string;
  sector: string;
  asset_class: string;
  weight: number;
  target_amount: number;
  price: number;
  shares: number;
  invested: number;
}

export interface PlanData {
  strategy: string;
  recommended: string | null;
  profile: Profile;
  plan: PlanRow[];
  cash_left: number;
  evaluation: Evaluation;
  data_as_of: string;
}

export interface StrategiesData {
  recommended: string;
  why: string;
  profile: Profile;
  strategies: Evaluation[];
}

export interface MCData {
  strategy: string;
  profile: Profile;
  mc: MC;
  regime: string;
}

export interface ShockRow {
  scenario: string;
  day0_impact: number;
  median_final: number;
  median_cagr: number;
  prob_positive: number;
  prob_target: number | null;
  worst_case_p5: number;
  prob_loss_gt_10: number;
}

export interface StressData {
  strategy: string;
  profile: Profile;
  stress: StressRow[];
  shock_mc: ShockRow[];
  loss_limit: number;
}

export interface TimingRow {
  strategy: string;
  expected_final: number;
  median_final: number;
  p5_final: number;
  p95_final: number;
  prob_beats_lump_sum: number | null;
  prob_profit: number;
  median_cagr: number;
}

export interface TimingData {
  strategy: string;
  profile: Profile;
  table: TimingRow[];
  regime: string;
}

export interface BacktestRow {
  strategy: string;
  total_return: number;
  cagr: number;
  volatility: number;
  sharpe: number;
  max_drawdown: number;
  final_value: number;
}

export interface BacktestData {
  start: string;
  end: string;
  years: number;
  series: string[];
  curves: Record<string, number | string>[];
  table: BacktestRow[];
}

export interface MarketOverview {
  as_of: string;
  nifty_close: number;
  nifty_1d: number;
  nifty_1m: number;
  nifty_1y: number;
  nifty_drawdown_from_peak: number;
  nifty_vol_1m: number;
  india_vix: number;
  brent: number;
  usdinr: number;
  regime: string;
  regime_probabilities: Record<string, number>;
  anomaly_today: boolean;
  anomaly_percentile: number;
  unusual_stock_moves: { symbol: string; ret: number; z: number }[];
  risk_free: number;
  market_expected_return: number;
  ml_model: string;
  ml_skill_weight: number;
}

export interface RegimeStat {
  regime: string;
  days: number;
  share: number;
  ann_return: number;
  ann_vol: number;
  avg_vix: number;
  avg_drawdown: number;
}

export interface MarketData {
  overview: MarketOverview;
  timeline: { date: string; nifty: number; regime: number }[];
  anomalies: { date: string; score: number; flagged: boolean }[];
  regimes: RegimeStat[];
  transition: number[][];
  regime_names: string[];
}

export interface AssetRow {
  symbol: string;
  ticker: string;
  name: string;
  sector: string;
  asset_class: string;
  price: number;
  beta: number;
  capm_return: number;
  hist_return: number;
  expected_return: number;
  vol: number;
  mdd: number;
  sharpe: number;
  ml_tilt: number;
}

export interface AssetDetail {
  symbol: string;
  name: string;
  sector: string;
  asset_class: string;
  last_price: number;
  ret_today: number;
  ret_1m: number;
  ret_6m: number;
  ret_1y: number;
  beta: number;
  capm_expected_return: number;
  hist_return_5y: number;
  volatility: number;
  max_drawdown: number;
  var95_1d: number;
  cvar95_1d: number;
  sharpe_hist: number;
  ml_forecast_21d: number;
  final_expected_return: number;
  rsi14: number;
  above_200dma: boolean;
  series: { date: string; asset: number; nifty: number }[];
}

export interface SearchRow {
  ic?: number;
  icir?: number;
  ic_pos?: number;
  hit?: number;
  top_hit?: number;
  spread_21d?: number;
  spread_t?: number;
  r2?: number;
  corr?: number;
  mape?: number;
}

export interface ModelSearch {
  relative_return: { results: Record<string, SearchRow> };
}

export interface VolMeta {
  asof: string;
  model: string;
  rows: number;
  years: string;
  r2: number;
  naive_21d_r2: number;
  naive_63d_r2: number;
  err: number;
  naive_21d_err: number;
  naive_63d_err: number;
  within_asset_r2: number;
  corr: number;
}

export interface ModelsData {
  search?: ModelSearch | null;
  volatility?: VolMeta | null;
  metrics: Record<string, number | string | null>[];
  regimes?: RegimeStat[];
  importance: { feature: string; value: number }[];
  selected?: string;
  skill_weight?: number;
}

export interface Position {
  symbol: string;
  ticker: string;
  name: string;
  sector: string;
  qty: number;
  avg_cost: number;
  price: number;
  value: number;
  cost: number;
  pnl: number;
  pnl_pct: number;
}

export interface Valuation {
  cash: number;
  invested_value: number;
  total_value: number;
  starting_cash: number;
  pnl: number;
  pnl_pct: number;
  positions: Position[];
}

export interface PendingOrders {
  created: string;
  label: string;
  buy_cost: number;
  sell_proceeds: number;
  orders: OrderRow[];
}

export interface OrderRow {
  side: "BUY" | "SELL";
  symbol: string;
  ticker: string;
  name: string;
  sector?: string;
  qty: number;
  price: number;
  value: number;
}

export interface Trade {
  id: number;
  ts: string;
  symbol: string;
  ticker: string;
  name: string;
  side: "BUY" | "SELL";
  qty: number;
  price: number;
  fee: number;
  note: string;
}

export interface SipRow {
  id: number;
  strategy: string;
  monthly_amount_rs: number;
  instalments_done: number;
  instalments_total: number;
  invested_rs: number;
  next_date: string | null;
  status: string;
}

export interface WalletData {
  valuation: Valuation;
  equity: { asof: string; total: number; cash: number }[];
  pending: PendingOrders | null;
  trades?: Trade[];
  sips?: SipRow[];
  autonomy?: Autonomy;
  autopilot?: boolean;
}

export interface OrdersData {
  executed: boolean;
  label: string;
  orders: OrderRow[];
  cash: number;
  total_value: number;
}

export interface HealthIssue {
  code: string;
  severity: "high" | "medium" | "info";
  message: string;
  symbol?: string;
}

export interface HealthData {
  issues: HealthIssue[];
  orders: OrderRow[];
  label: string;
  metrics: Record<string, number>;
  regime: string;
  total_value: number;
  cash: number;
}

export type Artifact =
  | { kind: "plan"; title: string; data: PlanData }
  | { kind: "strategies"; title: string; data: StrategiesData }
  | { kind: "montecarlo"; title: string; data: MCData }
  | { kind: "stress"; title: string; data: StressData }
  | { kind: "timing"; title: string; data: TimingData }
  | { kind: "backtest"; title: string; data: BacktestData }
  | { kind: "market"; title: string; data: MarketOverview }
  | { kind: "models"; title: string; data: ModelsData }
  | { kind: "asset"; title: string; data: AssetDetail }
  | { kind: "wallet"; title: string; data: WalletData }
  | { kind: "trades"; title: string; data: { trades: Trade[] } }
  | { kind: "orders"; title: string; data: OrdersData }
  | { kind: "health"; title: string; data: HealthData }
  | { kind: "sips"; title: string; data: { sips: SipRow[] } };

export interface ActionResponse {
  result: Record<string, unknown>;
  artifacts: Artifact[];
  wallet: WalletData;
  state: AppState;
}

export type ChatEvent =
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; ok: boolean; result: Record<string, unknown> }
  | { type: "text"; delta: string }
  | { type: "error"; message: string }
  | { type: "done"; text: string; artifacts: Artifact[]; wallet: WalletData; state: AppState };

export interface FrontierData {
  frontier: { vol: number; ret: number }[];
  cloud: { vol: number; ret: number }[];
  assets: { ticker: string; vol: number; ret: number }[];
  strategies: { strategy: string; vol: number; ret: number }[];
}

export interface SimHolding {
  asset: string;
  weight: number;
}

export interface SimPreset {
  id: string;
  label: string;
  description: string;
  holdings: { symbol: string; ticker: string; name: string; weight: number }[];
}

export interface SimFanPoint {
  month: number;
  year: number;
  invested: number;
  p5: number;
  p25: number;
  p50: number;
  p75: number;
  p95: number;
  fd: number;
  nifty: number;
}

export interface SimYearRow {
  year: number;
  invested: number;
  p5: number;
  p25: number;
  median: number;
  p75: number;
  p95: number;
  expected: number;
  median_gain: number;
  median_return: number;
  prob_profit: number;
  fd: number;
  nifty: number;
  beats_fd: number;
}

export interface SimBreakdown {
  symbol: string;
  ticker: string;
  name: string;
  sector: string;
  asset_class: string;
  weight: number;
  amount: number;
  monthly: number;
  price: number;
  expected_return: number;
  volatility: number;
  contribution: number;
  beta: number;
  projected: number;
}

export interface SimResult {
  inputs: { amount: number; monthly: number; years: number; n_paths: number };
  portfolio: { expected_return: number; volatility: number; next_month_volatility: number; beta: number; sharpe: number; regime: string };
  summary: {
    total_invested: number;
    expected_final: number;
    median_final: number;
    p5_final: number;
    p95_final: number;
    expected_gain: number;
    median_gain: number;
    median_annual_return: number;
    prob_profit: number;
    prob_beat_fd: number;
    prob_beat_nifty: number;
    prob_loss_10: number;
    fd_final: number;
    nifty_final: number;
    fd_rate: number;
    nifty_rate: number;
  };
  fan: SimFanPoint[];
  table: SimYearRow[];
  hist: { x: number; pct: number }[];
  breakdown: SimBreakdown[];
}
