"""Demo-money paper-trading wallet (SQLite). No real money, broker or exchange is ever touched.

Orders execute at the latest available close; brokerage + slippage are charged so P&L is realistic.
A plan is first *staged* and only executed after an explicit ``confirm_pending`` call.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import pandas as pd

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK (id = 1), cash REAL NOT NULL,
    starting_cash REAL NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS holdings (symbol TEXT PRIMARY KEY, qty INTEGER NOT NULL, avg_cost REAL NOT NULL);
CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, symbol TEXT NOT NULL,
    side TEXT NOT NULL, qty INTEGER NOT NULL, price REAL NOT NULL, fee REAL NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS pending (id INTEGER PRIMARY KEY CHECK (id = 1), created TEXT NOT NULL,
    strategy TEXT NOT NULL, orders TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS equity (asof TEXT PRIMARY KEY, total REAL NOT NULL, cash REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sips (id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, strategy TEXT NOT NULL,
    weights TEXT NOT NULL, amount REAL NOT NULL, months INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0,
    invested REAL NOT NULL DEFAULT 0, next_date TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
"""


class WalletError(Exception):
    pass


class Wallet:
    def __init__(self, path=C.DB_PATH, starting_cash: float = C.DEMO_STARTING_CASH):
        self.path = str(path)
        with self._conn() as c:
            c.executescript(SCHEMA)
            if c.execute("SELECT COUNT(*) FROM account").fetchone()[0] == 0:
                c.execute("INSERT INTO account VALUES (1, ?, ?, ?)",
                          (starting_cash, starting_cash, datetime.now().isoformat(timespec="seconds")))

    @contextmanager
    def _conn(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    # ------------------------------------------------------------------ cash
    def cash(self) -> float:
        with self._conn() as c:
            return float(c.execute("SELECT cash FROM account").fetchone()[0])

    def starting_cash(self) -> float:
        with self._conn() as c:
            return float(c.execute("SELECT starting_cash FROM account").fetchone()[0])

    def add_demo_funds(self, amount: float) -> float:
        if amount <= 0:
            raise WalletError("amount must be positive")
        with self._conn() as c:
            c.execute("UPDATE account SET cash = cash + ?, starting_cash = starting_cash + ?", (amount, amount))
        return self.cash()

    def reset(self, starting_cash: float = C.DEMO_STARTING_CASH) -> None:
        with self._conn() as c:
            for t in ("holdings", "trades", "pending", "equity", "sips"):
                c.execute(f"DELETE FROM {t}")
            c.execute("DELETE FROM sqlite_sequence WHERE name IN ('trades', 'sips')")
            c.execute("UPDATE account SET cash=?, starting_cash=?, created=?",
                      (starting_cash, starting_cash, datetime.now().isoformat(timespec="seconds")))

    # ---------------------------------------------------------------- trading
    @staticmethod
    def _cost_rate() -> float:
        return C.BROKERAGE_RATE + C.SLIPPAGE_RATE

    def buy(self, symbol: str, qty: int, price: float, note: str = "", _c=None) -> dict:
        qty = int(qty)
        if qty <= 0:
            raise WalletError("quantity must be positive")
        gross = qty * price
        fee = gross * self._cost_rate()
        total = gross + fee

        def run(c):
            cash = float(c.execute("SELECT cash FROM account").fetchone()[0])
            if total > cash + 1e-6:
                raise WalletError(f"insufficient demo cash: need Rs.{total:,.2f}, have Rs.{cash:,.2f}")
            row = c.execute("SELECT qty, avg_cost FROM holdings WHERE symbol=?", (symbol,)).fetchone()
            if row:
                nq = row["qty"] + qty
                avg = (row["qty"] * row["avg_cost"] + total) / nq
                c.execute("UPDATE holdings SET qty=?, avg_cost=? WHERE symbol=?", (nq, avg, symbol))
            else:
                c.execute("INSERT INTO holdings VALUES (?,?,?)", (symbol, qty, total / qty))
            c.execute("UPDATE account SET cash = cash - ?", (total,))
            c.execute("INSERT INTO trades (ts,symbol,side,qty,price,fee,note) VALUES (?,?,?,?,?,?,?)",
                      (datetime.now().isoformat(timespec="seconds"), symbol, "BUY", qty, price, fee, note))

        if _c is not None:
            run(_c)
        else:
            with self._conn() as c:
                run(c)
        return dict(symbol=symbol, side="BUY", qty=qty, price=price, fee=fee, total=total)

    def sell(self, symbol: str, qty: int, price: float, note: str = "", _c=None) -> dict:
        qty = int(qty)
        if qty <= 0:
            raise WalletError("quantity must be positive")
        gross = qty * price
        fee = gross * self._cost_rate()
        proceeds = gross - fee

        def run(c):
            row = c.execute("SELECT qty, avg_cost FROM holdings WHERE symbol=?", (symbol,)).fetchone()
            if not row or row["qty"] < qty:
                have = row["qty"] if row else 0
                raise WalletError(f"cannot sell {qty} {symbol}: only {have} held")
            if row["qty"] == qty:
                c.execute("DELETE FROM holdings WHERE symbol=?", (symbol,))
            else:
                c.execute("UPDATE holdings SET qty=qty-? WHERE symbol=?", (qty, symbol))
            c.execute("UPDATE account SET cash = cash + ?", (proceeds,))
            c.execute("INSERT INTO trades (ts,symbol,side,qty,price,fee,note) VALUES (?,?,?,?,?,?,?)",
                      (datetime.now().isoformat(timespec="seconds"), symbol, "SELL", qty, price, fee, note))

        if _c is not None:
            run(_c)
        else:
            with self._conn() as c:
                run(c)
        return dict(symbol=symbol, side="SELL", qty=qty, price=price, fee=fee, total=proceeds)

    # ------------------------------------------------------- staged execution
    def stage_orders(self, orders: list[dict], label: str) -> dict:
        """Stage BUY/SELL orders [{symbol, side, qty, price}] for later confirmation."""
        orders = [dict(symbol=o["symbol"], side=o.get("side", "BUY").upper(), qty=int(o["qty"]),
                       price=float(o["price"])) for o in orders if int(o["qty"]) > 0]
        if not orders:
            raise WalletError("nothing to stage: all quantities are zero")
        cash = self.cash()
        held = {r.symbol: r.qty for r in self.holdings().itertuples()}
        buys = sum(o["qty"] * o["price"] for o in orders if o["side"] == "BUY") * (1 + self._cost_rate())
        sells = sum(o["qty"] * o["price"] for o in orders if o["side"] == "SELL") * (1 - self._cost_rate())
        for o in orders:
            if o["side"] == "SELL" and held.get(o["symbol"], 0) < o["qty"]:
                raise WalletError(f"cannot sell {o['qty']} {o['symbol']}: only {held.get(o['symbol'], 0)} held")
        if buys > cash + sells + 1e-6:
            raise WalletError(f"orders need Rs.{buys:,.0f} but the demo wallet has only Rs.{cash:,.0f}. "
                              f"Add demo funds or reduce the amount.")
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO pending VALUES (1, ?, ?, ?)",
                      (datetime.now().isoformat(timespec="seconds"), label, json.dumps(orders)))
        return dict(label=label, n_orders=len(orders), buy_cost=buys, sell_proceeds=sells, orders=orders)

    def stage_plan(self, plan: pd.DataFrame, strategy: str) -> dict:
        return self.stage_orders([dict(symbol=r.symbol, side="BUY", qty=int(r.shares), price=float(r.price))
                                  for r in plan.itertuples() if int(r.shares) > 0], strategy)

    def pending(self) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM pending WHERE id=1").fetchone()
        if not row:
            return None
        orders = json.loads(row["orders"])
        cr = self._cost_rate()
        buys = sum(o["qty"] * o["price"] for o in orders if o["side"] == "BUY") * (1 + cr)
        sells = sum(o["qty"] * o["price"] for o in orders if o["side"] == "SELL") * (1 - cr)
        return dict(created=row["created"], label=row["strategy"], orders=orders, buy_cost=buys, sell_proceeds=sells)

    def cancel_pending(self) -> bool:
        with self._conn() as c:
            n = c.execute("DELETE FROM pending").rowcount
        return n > 0

    def execute_orders(self, orders: list[dict], label: str) -> list[dict]:
        """Atomically execute BUY/SELL orders now (sells first). All fill or none."""
        orders = [dict(symbol=o["symbol"], side=o.get("side", "BUY").upper(), qty=int(o["qty"]),
                       price=float(o["price"])) for o in orders if int(o["qty"]) > 0]
        if not orders:
            raise WalletError("nothing to execute")
        results = []
        with self._conn() as c:
            for o in sorted(orders, key=lambda o: o["side"] != "SELL"):
                fn = self.buy if o["side"] == "BUY" else self.sell
                results.append(fn(o["symbol"], o["qty"], o["price"], note=f"order:{label}", _c=c))
            c.execute("DELETE FROM pending")
        return results

    def confirm_pending(self) -> list[dict]:
        pend = self.pending()
        if not pend:
            raise WalletError("there is no staged order to execute")
        res = self.execute_orders(pend["orders"], pend["label"])
        m = re.match(r"SIP #(\d+) instalment", pend["label"] or "")
        if m:                                       # a staged SIP instalment now counts as invested
            spent = sum(o["qty"] * o["price"] for o in pend["orders"] if o["side"] == "BUY")
            with self._conn() as c:
                c.execute("UPDATE sips SET done = done + 1, invested = invested + ?, "
                          "active = CASE WHEN done + 1 >= months THEN 0 ELSE active END WHERE id = ?", (spent, int(m.group(1))))
        return res

    # ---------------------------------------------------------------- settings
    def get_setting(self, key: str, default: str = "") -> str:
        with self._conn() as c:
            row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, str(value)))

    # ------------------------------------------------------------------ SIPs
    def add_sip(self, strategy: str, weights: dict, amount: float, months: int, next_date: str) -> int:
        """A monthly SIP: `amount` per month into fixed target `weights`, `months` instalments in total."""
        with self._conn() as c:
            cur = c.execute("INSERT INTO sips (created, strategy, weights, amount, months, done, invested, next_date, active) "
                            "VALUES (?,?,?,?,?,0,0,?,1)", (datetime.now().isoformat(timespec="seconds"), strategy,
                                                            json.dumps(weights), float(amount), int(months), next_date))
            return int(cur.lastrowid)

    def sips(self, active_only: bool = False) -> list[dict]:
        with self._conn() as c:
            q = "SELECT * FROM sips" + (" WHERE active=1" if active_only else "") + " ORDER BY id"
            rows = [dict(r) for r in c.execute(q).fetchall()]
        for r in rows:
            r["weights"] = json.loads(r["weights"])
        return rows

    def record_sip_instalment(self, sip_id: int, spent: float, next_date: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE sips SET done = done + 1, invested = invested + ?, next_date = ?, "
                      "active = CASE WHEN done + 1 >= months THEN 0 ELSE active END WHERE id = ?", (float(spent), next_date, int(sip_id)))

    def delete_sip(self, sip_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM sips WHERE id = ?", (int(sip_id),))

    def stop_sip(self, sip_id: int | None = None) -> int:
        with self._conn() as c:
            if sip_id is None:
                return c.execute("UPDATE sips SET active = 0 WHERE active = 1").rowcount
            return c.execute("UPDATE sips SET active = 0 WHERE active = 1 AND id = ?", (int(sip_id),)).rowcount

    # -------------------------------------------------------------- reporting
    def holdings(self) -> pd.DataFrame:
        with self._conn() as c:
            rows = c.execute("SELECT symbol, qty, avg_cost FROM holdings ORDER BY symbol").fetchall()
        return pd.DataFrame([dict(r) for r in rows], columns=["symbol", "qty", "avg_cost"])

    def trades(self, limit: int = 100) -> pd.DataFrame:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return pd.DataFrame([dict(r) for r in rows])

    def valuation(self, prices: pd.Series, asof: str | None = None, record: bool = True) -> dict:
        h = self.holdings()
        cash = self.cash()
        if len(h):
            h["price"] = h.symbol.map(prices)
            h["value"] = h.qty * h.price
            h["cost"] = h.qty * h.avg_cost
            h["pnl"] = h.value - h.cost
            h["pnl_pct"] = h.pnl / h.cost
            h["name"] = h.symbol.map(lambda s: C.UNIVERSE[s][0])
            h["sector"] = h.symbol.map(lambda s: C.UNIVERSE[s][1])
        invested = float(h["value"].sum()) if len(h) else 0.0
        total = cash + invested
        start = self.starting_cash()
        if record and asof:
            with self._conn() as c:
                c.execute("INSERT OR REPLACE INTO equity VALUES (?,?,?)", (asof, total, cash))
        return dict(cash=cash, invested_value=invested, total_value=total, starting_cash=start,
                    pnl=total - start, pnl_pct=(total / start - 1) if start else 0.0, positions=h)

    def equity_curve(self) -> pd.DataFrame:
        with self._conn() as c:
            rows = c.execute("SELECT asof, total, cash FROM equity ORDER BY asof").fetchall()
        return pd.DataFrame([dict(r) for r in rows])
