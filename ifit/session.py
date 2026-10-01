"""Shared state between the chat agent and the dashboard."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .engine import Engine, UserProfile, Evaluation
from .wallet import Wallet


@dataclass
class Session:
    engine: Engine
    wallet: Wallet
    profile: UserProfile = field(default_factory=UserProfile)
    profile_confirmed: bool = False          # True once the user (or the agent) set a profile
    board: dict[str, Evaluation] | None = None
    board_key: tuple | None = None
    recommended: str | None = None
    recommended_why: str = ""
    selected_strategy: str | None = None
    last_plan: pd.DataFrame | None = None
    artifacts: list[dict] = field(default_factory=list)   # UI-renderable outputs of tool calls
    last_user_text: str = ""
    force_action: bool = False               # True when the app (not the chat) triggers an action

    @property
    def autonomy(self) -> str:
        """'auto' = the agent executes trades itself when asked; 'ask' = stage + user confirms."""
        return self.wallet.get_setting("autonomy", "auto")

    def set_autonomy(self, mode: str) -> str:
        mode = "auto" if str(mode).lower().startswith("auto") else "ask"
        self.wallet.set_setting("autonomy", mode)
        return mode

    @property
    def autopilot(self) -> bool:
        return self.wallet.get_setting("autopilot", "0") == "1"

    def set_autopilot(self, on: bool) -> None:
        self.wallet.set_setting("autopilot", "1" if on else "0")

    def emit(self, kind: str, title: str, payload) -> None:
        self.artifacts.append(dict(kind=kind, title=title, payload=payload))

    def take_artifacts(self) -> list[dict]:
        out, self.artifacts = self.artifacts, []
        return out

    def ensure_board(self) -> dict[str, Evaluation]:
        p = self.profile.normalised()
        if self.board is None or self.board_key != p.key():
            self.board = self.engine.run_all(p)
            self.board_key = p.key()
            self.recommended, self.recommended_why = self.engine.recommend(self.board, p)
        return self.board

    def set_profile(self, **kw) -> UserProfile:
        cur = self.profile
        new = UserProfile(
            amount=kw.get("amount", cur.amount),
            horizon_years=kw.get("horizon_years", cur.horizon_years),
            risk=kw.get("risk", cur.risk),
            target_return=kw.get("target_return", cur.target_return),
            preferred_sectors=kw.get("preferred_sectors", cur.preferred_sectors),
        ).normalised()
        if new.key() != cur.normalised().key():
            self.selected_strategy = None            # a new profile means a new recommendation
            self.last_plan = None
        self.profile = new
        self.profile_confirmed = True
        return new

    @classmethod
    def create(cls) -> "Session":
        return cls(engine=Engine(), wallet=Wallet())
