"""
compute_features_live(buf15: pd.DataFrame) -> pd.DataFrame (one row)

• buf15 is a rolling 15-minute OHLCV DataFrame
  indexed by timestamp and containing columns:
  ["open", "high", "low", "close", "volume"]

• returns the most-recent row of engineered features
  with **no NaNs**, ready for model.predict().
"""

import pandas as pd
import numpy as np

# ------- parameters used in back-test ---------
LAG_BARS   = [1, 2, 4]     # 15, 30, 60 minutes
ROLL_BARS  = [2, 4, 8]     # 30, 60, 120 minutes
POC_BUCKET = 200           # $200 price buckets

def compute_features_live(buf15: pd.DataFrame) -> pd.DataFrame:
    df = buf15.copy()

    # --- log-return & lags ----------------------
    df["log_ret"] = np.log(df["close"]).diff()
    for lag in LAG_BARS:
        df[f"log_lag_{lag}"] = df["log_ret"].shift(lag)

    # --- rolling stats --------------------------
    for w in ROLL_BARS:
        df[f"ret_mean_{w}"] = df["log_ret"].rolling(w).mean()
        df[f"ret_std_{w}"]  = df["log_ret"].rolling(w).std()
        df[f"vol_mean_{w}"] = df["volume"].rolling(w).mean()

    # --- daily anchored VWAP gap ----------------
    d_idx = df.index.floor("D")
    pv_d  = (df["close"] * df["volume"]).groupby(d_idx).cumsum()
    vv_d  = df["volume"].groupby(d_idx).cumsum().replace(0, np.nan)
    df["gap_dvwap"] = df["close"] - pv_d / vv_d

    # --- weekly anchored VWAP gap ---------------
    w_idx = (df.index - pd.to_timedelta(df.index.weekday, "D")).floor("D")
    pv_w  = (df["close"] * df["volume"]).groupby(w_idx).cumsum()
    vv_w  = df["volume"].groupby(w_idx).cumsum().replace(0, np.nan)
    df["gap_wvwap"] = df["close"] - pv_w / vv_w

    # --- daily POC gap --------------------------
    bucket = (df["close"] / POC_BUCKET).round() * POC_BUCKET
    vol_by_bucket = df.groupby([d_idx, bucket])["volume"].sum()
    poc_price = (
        vol_by_bucket.groupby(level=0).idxmax()   # (day, bucket)
                     .apply(lambda t: t[1])       # keep bucket price
    )
    df["gap_poc"] = df["close"] - d_idx.map(poc_price)

    # --- drop rows with any NaNs ----------------
    latest = df.iloc[-1:].dropna(axis=1)
    return latest
