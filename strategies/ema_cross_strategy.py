"""
多重 EMA 交叉策略 (Multi EMA Cross Strategy)

邏輯：
- 三條 EMA（短/中/長期）形成排列
- 做多：短 > 中 > 長（多頭排列）+ RSI 動能確認 + 成交量放大
- 做空：短 < 中 < 長（空頭排列）+ RSI 動能確認 + 成交量放大
- ATR 動態止損
- 適合：中長期趨勢行情
"""

import pandas as pd
import ta
from strategies.base_strategy import BaseStrategy


class EMACrossStrategy(BaseStrategy):
    """多重 EMA 交叉趨勢策略"""

    def __init__(self, config: dict, params: dict = None):
        super().__init__(config)
        self.name = "ema_cross"
        p = params or {}

        self.ema_short: int = p.get("ema_short", 9)
        self.ema_mid: int = p.get("ema_mid", 21)
        self.ema_long: int = p.get("ema_long", 55)
        self.rsi_period: int = p.get("rsi_period", 14)
        self.rsi_min: float = p.get("rsi_min", 45)    # 做多時 RSI 須大於此值
        self.rsi_max: float = p.get("rsi_max", 55)    # 做空時 RSI 須小於此值
        self.atr_period: int = p.get("atr_period", 14)
        self.atr_sl_multiplier: float = p.get("atr_sl_multiplier", 1.5)
        self.atr_tp_multiplier: float = p.get("atr_tp_multiplier", 2.2)
        self.volume_filter: bool = p.get("volume_filter", True)

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df["ema_s"] = ta.trend.EMAIndicator(close=df["close"], window=self.ema_short).ema_indicator()
        df["ema_m"] = ta.trend.EMAIndicator(close=df["close"], window=self.ema_mid).ema_indicator()
        df["ema_l"] = ta.trend.EMAIndicator(close=df["close"], window=self.ema_long).ema_indicator()

        df["rsi"] = ta.momentum.RSIIndicator(close=df["close"], window=self.rsi_period).rsi()

        df["atr"] = ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=self.atr_period
        ).average_true_range()

        df["vol_ma"] = df["volume"].rolling(window=20).mean()

        # EMA 斜率（動能方向）
        df["ema_s_slope"] = df["ema_s"].diff(3)

        return df

    def get_signal(self, df: pd.DataFrame) -> dict | None:
        if len(df) < self.ema_long + 10:
            return None

        df = self.calculate_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]

        if pd.isna(last["atr"]) or last["atr"] == 0:
            return None

        vol_ok = (not self.volume_filter) or (last["volume"] > last["vol_ma"] * 1.3)

        # 多頭排列條件：短>中>長，剛發生交叉（前一根短<=中 或 中<=長），RSI 動能
        bull_alignment = last["ema_s"] > last["ema_m"] > last["ema_l"]
        bull_cross = (prev["ema_s"] <= prev["ema_m"]) or (prev["ema_m"] <= prev["ema_l"])
        long_condition = (
            bull_alignment
            and bull_cross
            and last["rsi"] > self.rsi_min
            and last["ema_s_slope"] > 0
            and vol_ok
        )

        # 空頭排列條件：短<中<長，剛發生死叉
        bear_alignment = last["ema_s"] < last["ema_m"] < last["ema_l"]
        bear_cross = (prev["ema_s"] >= prev["ema_m"]) or (prev["ema_m"] >= prev["ema_l"])
        short_condition = (
            bear_alignment
            and bear_cross
            and last["rsi"] < self.rsi_max
            and last["ema_s_slope"] < 0
            and vol_ok
        )

        if long_condition:
            entry = last["close"]
            sl = last["ema_l"] - last["atr"] * self.atr_sl_multiplier
            tp = entry + last["atr"] * self.atr_tp_multiplier
            return {
                "side": "LONG",
                "entry": entry,
                "stop_loss": sl,
                "take_profit": tp,
                "reason": f"EMA多頭排列：{self.ema_short}/{self.ema_mid}/{self.ema_long} 黃金交叉、RSI={last['rsi']:.1f}",
            }

        if short_condition:
            entry = last["close"]
            sl = last["ema_l"] + last["atr"] * self.atr_sl_multiplier
            tp = entry - last["atr"] * self.atr_tp_multiplier
            return {
                "side": "SHORT",
                "entry": entry,
                "stop_loss": sl,
                "take_profit": tp,
                "reason": f"EMA空頭排列：{self.ema_short}/{self.ema_mid}/{self.ema_long} 死叉、RSI={last['rsi']:.1f}",
            }

        return None

    def get_strategy_name(self) -> str:
        return f"EMACrossStrategy({self.ema_short}/{self.ema_mid}/{self.ema_long})"
