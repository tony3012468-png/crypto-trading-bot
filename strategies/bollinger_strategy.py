"""
布林通道策略 (Bollinger Bands Strategy)

邏輯：
- 做多：價格跌破下軌後反彈回上軌方向 + RSI 超賣 + 成交量確認
- 做空：價格突破上軌後反轉向下軌方向 + RSI 超買 + 成交量確認
- 止損：ATR 動態止損
- 適合：均值回歸市場（盤整時表現優於趨勢策略）
"""

import pandas as pd
import ta
from strategies.base_strategy import BaseStrategy


class BollingerStrategy(BaseStrategy):
    """布林通道均值回歸策略"""

    def __init__(self, config: dict, params: dict = None):
        super().__init__(config)
        self.name = "bollinger"
        p = params or {}

        self.bb_period: int = p.get("bb_period", 20)
        self.bb_std: float = p.get("bb_std", 2.0)
        self.rsi_period: int = p.get("rsi_period", 14)
        self.rsi_oversold: float = p.get("rsi_oversold", 35)
        self.rsi_overbought: float = p.get("rsi_overbought", 65)
        self.atr_period: int = p.get("atr_period", 14)
        self.atr_sl_multiplier: float = p.get("atr_sl_multiplier", 1.5)
        self.atr_tp_multiplier: float = p.get("atr_tp_multiplier", 2.0)
        self.volume_filter: bool = p.get("volume_filter", True)

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # 布林通道
        bb = ta.volatility.BollingerBands(
            close=df["close"], window=self.bb_period, window_dev=self.bb_std
        )
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_mid"] = bb.bollinger_mavg()
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

        # RSI
        df["rsi"] = ta.momentum.RSIIndicator(
            close=df["close"], window=self.rsi_period
        ).rsi()

        # ATR
        df["atr"] = ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=self.atr_period
        ).average_true_range()

        # 成交量均線
        df["vol_ma"] = df["volume"].rolling(window=20).mean()

        # 布林通道位置（%B）
        df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"] + 1e-10)

        return df

    def get_signal(self, df: pd.DataFrame) -> dict | None:
        if len(df) < self.bb_period + 10:
            return None

        df = self.calculate_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]

        if pd.isna(last["atr"]) or last["atr"] == 0:
            return None

        vol_ok = (not self.volume_filter) or (last["volume"] > last["vol_ma"] * 1.2)

        # 做多條件：前根跌破下軌，當根收回下軌之上，RSI 超賣
        long_condition = (
            prev["close"] < prev["bb_lower"]
            and last["close"] > last["bb_lower"]
            and last["rsi"] < self.rsi_oversold + 10
            and vol_ok
        )

        # 做空條件：前根突破上軌，當根收回上軌之下，RSI 超買
        short_condition = (
            prev["close"] > prev["bb_upper"]
            and last["close"] < last["bb_upper"]
            and last["rsi"] > self.rsi_overbought - 10
            and vol_ok
        )

        if long_condition:
            entry = last["close"]
            sl = entry - last["atr"] * self.atr_sl_multiplier
            tp = entry + last["atr"] * self.atr_tp_multiplier
            return {
                "side": "LONG",
                "entry": entry,
                "stop_loss": sl,
                "take_profit": tp,
                "reason": f"BB反彈做多：價格跌破下軌後反彈、RSI={last['rsi']:.1f}、BB寬度={last['bb_width']:.3f}",
            }

        if short_condition:
            entry = last["close"]
            sl = entry + last["atr"] * self.atr_sl_multiplier
            tp = entry - last["atr"] * self.atr_tp_multiplier
            return {
                "side": "SHORT",
                "entry": entry,
                "stop_loss": sl,
                "take_profit": tp,
                "reason": f"BB反轉做空：價格突破上軌後反轉、RSI={last['rsi']:.1f}、BB寬度={last['bb_width']:.3f}",
            }

        return None

    def get_strategy_name(self) -> str:
        return f"BollingerStrategy(period={self.bb_period},std={self.bb_std})"
