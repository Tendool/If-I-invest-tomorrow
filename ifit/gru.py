"""Optional GRU forecaster (Module 3, "LSTM-GRU (optional forecasting)").

A small GRU reads the last ``LOOKBACK`` days of standardised features of an asset and predicts its
forward 21-day return.  Used only inside the walk-forward comparison - it must earn its place.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LOOKBACK = 20


def _windows(df: pd.DataFrame, feats: list[str], mean, std) -> tuple[np.ndarray, np.ndarray]:
    X, idx = [], []
    for sym, g in df.groupby(level=1, sort=False):
        a = ((g[feats].values - mean) / std).astype(np.float32)
        pad = np.vstack([np.repeat(a[:1], LOOKBACK - 1, axis=0), a])
        w = np.lib.stride_tricks.sliding_window_view(pad, (LOOKBACK, a.shape[1]))[:, 0]
        X.append(w)
        idx.extend(g.index)
    return np.concatenate(X), idx


def fit_predict_gru(tr: pd.DataFrame, te: pd.DataFrame, feats: list[str], epochs: int = 6, seed: int = 7) -> np.ndarray:
    import torch
    import torch.nn as nn

    torch.manual_seed(seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    mean, std = tr[feats].values.mean(0), tr[feats].values.std(0) + 1e-9
    Xtr, itr = _windows(tr, feats, mean, std)
    ytr = tr.loc[itr, "target"].values.astype(np.float32)
    ym, ys = ytr.mean(), ytr.std()
    Xte, ite = _windows(te, feats, mean, std)

    class Net(nn.Module):
        def __init__(self, d):
            super().__init__()
            self.gru = nn.GRU(d, 32, batch_first=True)
            self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(32, 1))

        def forward(self, x):
            o, _ = self.gru(x)
            return self.head(o[:, -1]).squeeze(-1)

    net = Net(len(feats)).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-3)
    Xt = torch.tensor(np.clip(Xtr, -5, 5)).to(dev)
    yt = torch.tensor((ytr - ym) / ys).to(dev)
    for _ in range(epochs):
        perm = torch.randperm(len(Xt), device=dev)
        for i in range(0, len(Xt), 1024):
            b = perm[i:i + 1024]
            opt.zero_grad()
            loss = nn.functional.mse_loss(net(Xt[b]), yt[b])
            loss.backward()
            opt.step()
    net.eval()
    with torch.no_grad():
        p = net(torch.tensor(np.clip(Xte, -5, 5)).to(dev)).cpu().numpy() * ys + ym
    out = pd.Series(p, index=pd.MultiIndex.from_tuples(ite)).reindex(te.index)
    return out.values
