"""
智慧資金概念策略 (Smart Money Concepts Strategy)

核心概念：
1. 市場結構 (Market Structure)：識別 HH/HL（上升）或 LH/LL（下降）
2. 訂單區塊 (Order Block)：強勢移動前最後一根反向K線，視為機構佈局區
3. 公允價值缺口 (Fair Value Gap / FVG)：三根K線留下的流動性缺口
4. 流動性獵取 (Liquidity Sweep)：掃過前高/前低後快速反轉

進場邏輯：
- 做多：下降結構中 → 流動性掃除前低 → 反轉進入看漲訂單區塊 → FVG 填補確認
- 做空：上升結構中 → 流動性掃除前高 → 反轉進入看跌訂單區塊 → FVG 填補確認
"""

import pandas as pd
import ta
from strategies.base_strategy import BaseStrategy


class SMCStrategy(BaseStrategy):
    """智慧資金概念策略"""

    def __init__(self, config: dict, params: dict = None):
        super().__init__(config)
        self.name = "smc"
        p = params or {}

        self.swing_lookback: int = p.get("swing_lookback", 10)    # 辨識擺動高低點的回溯根數
        self.ob_lookback: int = p.get("ob_lookback", 5)           # 訂單區塊回溯範圍
        self.fvg_min_size: float = p.get("fvg_min_size", 0.001)   # FVG 最小尺寸（佔價格比例）
        self.atr_period: int = p.get("atr_period", 14)
        self.atr_sl_multiplier: float = p.get("atr_sl_multiplier", 1.2)
        self.atr_tp_multiplier: float = p.get("atr_tp_multiplier", 3.0)   # SMC 通常追求更高風報比
        self.rsi_period: int = p.get("rsi_period", 14)

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df["atr"] = ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=self.atr_period
        ).average_true_range()

        df["rsi"] = ta.momentum.RSIIndicator(
            close=df["close"], window=self.rsi_period
        ).rsi()

        # 辨識擺動高低點
        df["swing_high"] = df["high"].rolling(window=self.swing_lookback, center=True).max()
        df["swing_low"] = df["low"].rolling(window=self.swing_lookback, center=True).min()
        df["is_swing_high"] = df["high"] == df["swing_high"]
        df["is_swing_low"] = df["low"] == df["swing_low"]

        # 市場結構：使用 EMA200 判斷整體偏向
        df["ema200"] = ta.trend.EMAIndicator(close=df["close"], window=200).ema_indicator()

        # FVG 偵測（看漲：第1根low > 第3根high，看跌：第1根high < 第3根low）
        df["bullish_fvg"] = (df["low"] > df["high"].shift(2))
        df["bearish_fvg"] = (df["high"] < df["low"].shift(2))

        return df

    def _find_order_block(self, df: pd.DataFrame, direction: str) -> dict | None:
        """
        找最近的訂單區塊。
        看漲訂單區塊：強勢上漲前最後一根陰線
        看跌訂單區塊：強勢下跌前最後一根陽線
        """
        lookback = min(self.ob_lookback * 3, len(df) - 1)
        segment = df.iloc[-lookback:]

        if direction == "bullish":
            # 找最近一段強勢上漲（3根內漲幅 > 1%）
            for i in range(len(segment) - 3, 0, -1):
                move = (segment["close"].iloc[i+2] - segment["close"].iloc[i]) / segment["close"].iloc[i]
                if move > 0.01:
                    # 找這波上漲前最後一根陰線
                    for j in range(i, max(i - self.ob_lookback, 0), -1):
                        candle = segment.iloc[j]
                        if candle["close"] < candle["open"]:  # 陰線
                            return {
                                "top": candle["open"],
                                "bottom": candle["close"],
                                "index": j,
                            }
        elif direction == "bearish":
            # 找最近一段強勢下跌（3根內跌幅 > 1%）
            for i in range(len(segment) - 3, 0, -1):
                move = (segment["close"].iloc[i] - segment["close"].iloc[i+2]) / segment["close"].iloc[i]
                if move > 0.01:
                    # 找這波下跌前最後一根陽線
                    for j in range(i, max(i - self.ob_lookback, 0), -1):
                        candle = segment.iloc[j]
                        if candle["close"] > candle["open"]:  # 陽線
                            return {
                                "top": candle["close"],
                                "bottom": candle["open"],
                                "index": j,
                            }
        return None

    def _detect_liquidity_sweep(self, df: pd.DataFrame, direction: str) -> bool:
        """
        偵測流動性獵取：
        看漲：前 swing_lookback 根的最低點被刺破後，當根收回之上（掃除賣方流動性）
        看跌：前 swing_lookback 根的最高點被刺破後，當根收回之下（掃除買方流動性）
        """
        if len(df) < self.swing_lookback + 2:
            return False

        recent = df.iloc[-(self.swing_lookback + 2):-1]
        last = df.iloc[-1]

        if direction == "bullish":
            prev_low = recent["low"].min()
            return last["low"] < prev_low and last["close"] > prev_low

        elif direction == "bearish":
            prev_high = recent["high"].max()
            return last["high"] > prev_high and last["close"] < prev_high

        return False

    def get_signal(self, df: pd.DataFrame) -> dict | None:
        min_bars = max(200, self.swing_lookback * 3 + 10)
        if len(df) < min_bars:
            return None

        df = self.calculate_indicators(df)
        last = df.iloc[-1]

        if pd.isna(last["atr"]) or last["atr"] == 0 or pd.isna(last["ema200"]):
            return None

        # 整體偏向
        bullish_bias = last["close"] > last["ema200"]
        bearish_bias = last["close"] < last["ema200"]

        # 做多：整體偏多 + 流動性掃除前低 + 回到看漲訂單區塊
        if bullish_bias:
            sweep = self._detect_liquidity_sweep(df, "bullish")
            if sweep:
                ob = self._find_order_block(df, "bullish")
                if ob and ob["bottom"] <= last["close"] <= ob["top"] * 1.002:
                    # 是否有 FVG 填補確認
                    fvg_confirm = df["bullish_fvg"].iloc[-3:].any()
                    entry = last["close"]
                    sl = ob["bottom"] - last["atr"] * self.atr_sl_multiplier
                    tp = entry + last["atr"] * self.atr_tp_multiplier
                    return {
                        "side": "LONG",
                        "entry": entry,
                        "stop_loss": sl,
                        "take_profit": tp,
                        "reason": (
                            f"SMC做多：掃除流動性+看漲OB({ob['bottom']:.4f}-{ob['top']:.4f})"
                            f"{'+ FVG確認' if fvg_confirm else ''}、RSI={last['rsi']:.1f}"
                        ),
                    }

        # 做空：整體偏空 + 流動性掃除前高 + 回到看跌訂單區塊
        if bearish_bias:
            sweep = self._detect_liquidity_sweep(df, "bearish")
            if sweep:
                ob = self._find_order_block(df, "bearish")
                if ob and ob["bottom"] * 0.998 <= last["close"] <= ob["top"]:
                    fvg_confirm = df["bearish_fvg"].iloc[-3:].any()
                    entry = last["close"]
                    sl = ob["top"] + last["atr"] * self.atr_sl_multiplier
                    tp = entry - last["atr"] * self.atr_tp_multiplier
                    return {
                        "side": "SHORT",
                        "entry": entry,
                        "stop_loss": sl,
                        "take_profit": tp,
                        "reason": (
                            f"SMC做空：掃除流動性+看跌OB({ob['bottom']:.4f}-{ob['top']:.4f})"
                            f"{'+ FVG確認' if fvg_confirm else ''}、RSI={last['rsi']:.1f}"
                        ),
                    }

        return None

    def get_strategy_name(self) -> str:
        return f"SMCStrategy(swing={self.swing_lookback},ob={self.ob_lookback})"
