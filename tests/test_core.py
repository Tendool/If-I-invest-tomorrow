import numpy as np
import pandas as pd
import pytest

from ifit import config as C, risk, optimizer as O, montecarlo as MC
from ifit.agent import required_tools
from ifit.engine import UserProfile
from ifit.tools import user_confirmed
from ifit.wallet import Wallet, WalletError


# ---------------------------------------------------------------- risk maths
def test_max_drawdown_known():
    assert risk.max_drawdown([100, 120, 60, 90]) == pytest.approx(-0.5)


def test_var_cvar_ordering():
    r = np.random.default_rng(0).normal(0, 0.01, 10000)
    assert risk.historical_cvar(r, 0.95) >= risk.historical_var(r, 0.95) > 0
    assert risk.historical_var(r, 0.95) == pytest.approx(0.01645, abs=0.002)


def test_sharpe():
    assert risk.sharpe_ratio(0.16, 0.20, rf=0.06) == pytest.approx(0.5)
    assert risk.sharpe_ratio(0.1, 0.0) == 0.0


def test_capm_betas_and_covariance(engine):
    # ETF tracks the index (corr 0.98) but NAV timing noise gives beta slightly below 1
    assert 0.8 < engine.rm.beta["NIFTYBEES.NS"] < 1.1
    assert engine.rm.beta["LIQUIDBEES.NS"] == pytest.approx(0.0, abs=0.02)
    assert np.all(np.linalg.eigvalsh(engine.rm.cov.values) > -1e-10)     # positive semi-definite


# ---------------------------------------------------------------- optimiser
@pytest.mark.parametrize("risk_level", ["low", "medium", "high"])
@pytest.mark.parametrize("prefs", [[], ["IT", "Banking"], ["Gold"]])
def test_strategies_respect_constraints(engine, risk_level, prefs):
    p = UserProfile(100000, 3, risk_level, 0.12, prefs).normalised()
    b = engine.bounds(p)
    for name, w in engine.strategy_weights(p).items():
        assert w.sum() == pytest.approx(1.0, abs=1e-6), name
        assert (w >= -1e-9).all(), name
        assert np.all(w.values <= b.ub + 1e-6), name
        if prefs == ["Gold"]:
            assert w["GOLDBEES.NS"] >= C.MIN_PREFERRED_CLASS_WEIGHT - 1e-6
        if prefs == ["IT", "Banking"]:
            stocks = [s for s in w.index if C.UNIVERSE[s][2] == "stock" and w[s] > 0]
            assert all(C.UNIVERSE[s][1] in ("IT", "Banking") for s in stocks)


def test_strategy_ordering(engine):
    p = UserProfile(100000, 3, "medium", 0.12, [])
    ws = engine.strategy_weights(p)
    st = {n: risk.portfolio_stats(w, engine.mu, engine.rm.cov) for n, w in ws.items()}
    assert st["Min Risk"]["volatility"] <= min(v["volatility"] for v in st.values()) + 1e-4
    assert st["Max Return"]["exp_return"] >= max(v["exp_return"] for v in st.values()) - 1e-4
    assert st["Max Sharpe"]["sharpe"] >= max(v["sharpe"] for v in st.values()) - 0.02


def test_frontier_monotone(engine):
    b = engine.bounds(UserProfile().normalised())
    fr = O.efficient_frontier(engine.mu, engine.rm.cov, b, 12)
    vols = [risk.portfolio_stats(w, engine.mu, engine.rm.cov)["volatility"] for w in fr]
    assert all(b2 >= a - 1e-6 for a, b2 in zip(vols, vols[1:]))


# ------------------------------------------------------------- monte carlo
def test_mc_zero_vol_is_deterministic():
    v = MC.simulate_paths(0.10, 1e-9, 1.0, None, 3, n_paths=50)
    assert v[:, -1].std() < 1e-4
    assert v[0, -1] == pytest.approx(1.10 ** 3, rel=1e-3)


def test_mc_mean_matches_input_return(engine):
    res = MC.run_mc(0.12, 0.15, 1.0, engine.regime, 3, 100000, 0.12, n_paths=20000)
    assert (res.terminal.mean() / 100000) ** (1 / 3) - 1 == pytest.approx(0.12, abs=0.008)
    assert 0 <= res.stats["prob_target"] <= 1
    assert res.stats["worst_case_p5"] < res.stats["median_final"] < res.stats["best_case_p95"]


def test_shock_lowers_outcomes(engine):
    base = MC.run_mc(0.12, 0.15, 1.0, engine.regime, 3, 1e5, 0.12, n_paths=8000, seed=1)
    shk = MC.run_mc(0.12, 0.15, 1.0, engine.regime, 3, 1e5, 0.12, n_paths=8000, shock=-0.10, seed=1)
    assert shk.stats["median_final"] < base.stats["median_final"]
    assert shk.stats["prob_target"] < base.stats["prob_target"]


def test_higher_vol_widens_distribution():
    lo = MC.run_mc(0.1, 0.05, 1, None, 3, 1e5, None, n_paths=5000)
    hi = MC.run_mc(0.1, 0.30, 1, None, 3, 1e5, None, n_paths=5000)
    assert hi.stats["worst_case_p5"] < lo.stats["worst_case_p5"]


# ------------------------------------------------------------------ engine
def test_end_to_end_board(engine):
    p = UserProfile(100000, 3, "medium", 0.12, [])
    board = engine.run_all(p)
    assert set(board) == {"Max Return", "Min Risk", "Max Sharpe", "Goal-Based", "Crash-Resistant"}
    rec, why = engine.recommend(board, p)
    assert rec in board and why
    plan = engine.build_plan(board[rec].weights, p)
    spent = (plan.shares * plan.price).sum()
    assert 0.93 * p.amount < spent <= p.amount
    assert (plan.shares >= 0).all()


def test_stress_market_shock_scales_with_beta(engine):
    w = pd.Series(0.0, index=engine.rm.symbols)
    w["NIFTYBEES.NS"] = 1.0
    st = risk.stress_test(w, engine.rm, engine.md, 100000, 0.2)
    r = st.set_index("scenario").portfolio_return
    assert r["Market -10% shock"] == pytest.approx(-0.10 * engine.rm.beta["NIFTYBEES.NS"], abs=1e-6)
    assert r["Market -5% shock"] == pytest.approx(r["Market -10% shock"] / 2, abs=1e-6)


def test_profile_validation():
    assert UserProfile(5000, 2, "Moderate", 12).normalised().risk == "medium"
    assert UserProfile(5000, 2, "high", 12).normalised().target_return == pytest.approx(0.12)
    with pytest.raises(ValueError):
        UserProfile(500, 3, "low", 0.1).normalised()
    with pytest.raises(ValueError):
        UserProfile(5000, 3, "yolo", 0.1).normalised()


# ------------------------------------------------------------------ wallet
@pytest.fixture
def wallet(tmp_path):
    return Wallet(tmp_path / "w.sqlite", starting_cash=100000)


def test_wallet_buy_sell_accounting(wallet):
    wallet.buy("TCS.NS", 10, 2000)
    cost = 10 * 2000 * (1 + C.BROKERAGE_RATE + C.SLIPPAGE_RATE)
    assert wallet.cash() == pytest.approx(100000 - cost)
    wallet.sell("TCS.NS", 4, 2100)
    assert wallet.holdings().qty.iloc[0] == 6
    assert wallet.cash() > 100000 - cost


def test_wallet_rejects_overspend_and_oversell(wallet):
    with pytest.raises(WalletError):
        wallet.buy("TCS.NS", 100, 2000)
    with pytest.raises(WalletError):
        wallet.sell("TCS.NS", 1, 2000)


def test_wallet_staged_orders_need_confirmation(wallet):
    wallet.stage_orders([dict(symbol="TCS.NS", side="BUY", qty=5, price=2000)], "t")
    assert wallet.cash() == 100000 and wallet.holdings().empty        # staging moves nothing
    assert wallet.pending() is not None
    wallet.confirm_pending()
    assert len(wallet.holdings()) == 1 and wallet.pending() is None
    with pytest.raises(WalletError):
        wallet.stage_orders([dict(symbol="INFY.NS", side="BUY", qty=1000, price=1000)], "too big")


def test_wallet_reset(wallet):
    wallet.buy("TCS.NS", 1, 2000)
    wallet.reset(50000)
    assert wallet.cash() == 50000 and wallet.holdings().empty and wallet.trades().empty


# ------------------------------------------------------------- agent guards
@pytest.mark.parametrize("text,expected", [
    ("yes, confirm", True), ("Go ahead", True), ("no, cancel that", False),
    ("Buy everything right now, don't ask me anything.", False), ("what is the market doing", False)])
def test_user_confirmation_detector(text, expected):
    assert user_confirmed(text) is expected


def test_confirm_tool_refuses_without_user_consent(engine, tmp_path):
    from ifit.session import Session
    from ifit.tools import call_tool
    s = Session(engine=engine, wallet=Wallet(tmp_path / "g.sqlite", 100000))
    s.wallet.stage_orders([dict(symbol="TCS.NS", side="BUY", qty=1, price=2000)], "t")
    s.last_user_text = "show me the market"
    assert "REFUSED" in call_tool(s, "confirm_pending_order", {})["error"]
    assert s.wallet.holdings().empty
    s.last_user_text = "yes confirm"
    assert call_tool(s, "confirm_pending_order", {})["status"].startswith("EXECUTED")
    s.last_user_text = "reset my wallet"
    assert "REFUSED" in call_tool(s, "reset_wallet", {})["error"]


def test_intent_router():
    assert required_tools("What should I invest in tomorrow?") == ["get_investment_plan"]
    assert required_tools("stress test it") == ["stress_test"]
    assert required_tools("yes, confirm") == []
    assert required_tools("Stage the plan in my demo wallet") == ["invest_plan"]   # a stage-only request


# ------------------------------------------------------------ volatility forecaster
def test_vol_forecast_beats_naive_out_of_sample():
    import json
    from ifit import config as C
    m = json.loads((C.MODELS_DIR / "vol_model_meta.json").read_text(encoding="utf-8"))
    assert m["r2"] > max(m["naive_21d_r2"], m["naive_63d_r2"]) + 0.03
    assert m["err"] < min(m["naive_21d_err"], m["naive_63d_err"])
    assert m["within_asset_r2"] > 0.05                       # real month-to-month timing skill, not just "which assets are riskier"


def test_near_term_vol_on_every_strategy(engine):
    p = UserProfile(100000, 3, "medium", 0.12, [])
    for name, ev in engine.run_all(p).items():
        nt = ev.stats["near_term_vol"]
        assert 0.5 * ev.stats["volatility"] < nt < 2.0 * ev.stats["volatility"], name
    assert (engine.vol_fc > 0.005).all() and (engine.vol_fc < 2.0).all()


# ------------------------------------------------------------------------ simulator
def test_simulator_lump_sum_and_sip_accounting(engine):
    from ifit import simulator as SM
    r = SM.simulate(engine, [{"asset": "NIFTYBEES", "weight": 1}], 100000, 3, 0, n_paths=2000)
    assert r["summary"]["total_invested"] == 100000
    assert [x["year"] for x in r["table"]] == [1, 2, 3]
    assert r["table"][-1]["p5"] < r["table"][-1]["median"] < r["table"][-1]["p95"]
    r2 = SM.simulate(engine, [{"asset": "NIFTYBEES", "weight": 1}], 100000, 3, 5000, n_paths=2000)
    assert r2["summary"]["total_invested"] == 100000 + 5000 * 36
    assert r2["table"][0]["invested"] == 100000 + 5000 * 12
    assert r2["summary"]["median_final"] > r["summary"]["median_final"]            # more money in
    # cash earns about the risk-free rate, so its median is close to the deterministic FD path
    c = SM.simulate(engine, [{"asset": "LIQUIDBEES", "weight": 1}], 100000, 3, 0, n_paths=2000)
    assert abs(c["summary"]["median_final"] / c["summary"]["fd_final"] - 1) < 0.04


def test_simulator_weights_and_validation(engine):
    from ifit import simulator as SM
    w = SM.resolve_holdings(engine, [{"asset": "TCS", "weight": 30}, {"asset": "gold", "weight": 10}, {"asset": "TCS", "weight": 10}])
    assert w.sum() == pytest.approx(1.0) and w["TCS.NS"] == pytest.approx(0.8)
    for bad in ([], [{"asset": "NOPE", "weight": 1}], [{"asset": "TCS", "weight": 0}], [{"asset": "TCS", "weight": -5}]):
        with pytest.raises(SM.SimulationError):
            SM.resolve_holdings(engine, bad)
    with pytest.raises(SM.SimulationError):
        SM.simulate(engine, [{"asset": "TCS", "weight": 1}], 0, 3, 0)
    with pytest.raises(SM.SimulationError):
        SM.simulate(engine, [{"asset": "TCS", "weight": 1}], 1000, 30, 0)


def test_model_report_includes_measured_volatility_accuracy(engine, tmp_path):
    from ifit import tools
    from ifit.session import Session
    from ifit.wallet import Wallet
    s = Session(engine=engine, wallet=Wallet(tmp_path / "m.sqlite", 100000))
    v = tools.get_model_report(s)["volatility_model"]
    assert v is not None and 0.4 < v["r2"] < 0.8              # measured, not a marketing number
    assert v["r2"] > v["best_naive_r2"]


def test_models_artifact_carries_skill_weight_and_volatility(engine, tmp_path):
    from ifit import serialize as Z, tools
    from ifit.session import Session
    from ifit.wallet import Wallet
    s = Session(engine=engine, wallet=Wallet(tmp_path / "a.sqlite", 100000))
    tools.get_model_report(s)
    art = Z.artifact(s.take_artifacts()[0], s)
    assert art["kind"] == "models"
    assert 0 < art["data"]["skill_weight"] < 0.5                 # the card must not fall back to "0%"
    assert art["data"]["volatility"]["r2"] > art["data"]["volatility"]["naive_63d_r2"]
