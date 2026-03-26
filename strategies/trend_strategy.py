import pandas as pd
import ta

from strategies.base_strategy import BaseStrategy


class TrendStrategy(BaseStrategy):
    """
    改良版趨勢跟隨策略 - 使用多時間框架確認。

    相較於簡單 EMA 交叉的改進：
    1. 使用 MACD 方式（快線=12, 慢線=26, 訊號線=9）取代簡單交叉
    2. RSI 確認使用更嚴格的範圍（35-65 而非 30-70）
    3. 成交量過濾 - 僅在成交量 > 1.5 倍平均時交易
    4. 多時間框架：15 分鐘產生訊號，1 小時確認趨勢
    5. ATR 動態停損停利，更佳風險報酬比（1.8x ATR 停損, 2.5x ATR 停利）
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "trend"

        # 從設定檔讀取趨勢策略參數
        trend_cfg = config.get("trend", {})
        self.fast_ema: int = trend_cfg.get("fast_ema", 12)
        self.slow_ema: int = trend_cfg.get("slow_ema", 26)
        self.signal_ema: int = trend_cfg.get("signal_ema", 9)
        self.rsi_period: int = trend_cfg.get("rsi_period", 14)
        self.rsi_overbought: float = trend_cfg.get("rsi_overbought", 65)
        self.rsi_oversold: float = trend_cfg.get("rsi_oversold", 35)
        self.atr_period: int = trend_cfg.get("atr_period", 14)
        self.atr_sl_multiplier: float = trend_cfg.get("atr_sl_multiplier", 1.8)
        self.atr_tp_multiplier: float = trend_cfg.get("atr_tp_multiplier", 2.5)
        self.volume_filter: bool = trend_cfg.get("volume_filter", True)

        # 較高時間框架資料（1 小時 K 線）
        self._htf_data: pd.DataFrame | None = None

    def set_htf_data(self, df_1h: pd.DataFrame) -> None:
        """
        設定較高時間框架資料（1 小時 K 線），用於確認趨勢方向。

        參數：
            df_1h: 1 小時 K 線 DataFrame
        """
        self._htf_data = df_1h.copy()

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        計算趨勢策略所需的技術指標。

        包含：MACD、RSI、EMA、ATR、成交量均線。
        """
        df = df.copy()

        # EMA（指數移動平均線）
        df["ema_fast"] = ta.trend.EMAIndicator(
            close=df["close"], window=self.fast_ema
        ).ema_indicator()

        df["ema_slow"] = ta.trend.EMAIndicator(
            close=df["close"], window=self.slow_ema
        ).ema_indicator()

        # MACD（移動平均收斂散度）
        macd_indicator = ta.trend.MACD(
            close=df["close"],
            window_slow=self.slow_ema,
            window_fast=self.fast_ema,
            window_sign=self.signal_ema,
        )
        df["macd"] = macd_indicator.macd()
        df["macd_signal"] = macd_indicator.macd_signal()
        df["macd_histogram"] = macd_indicator.macd_diff()

        # RSI（相對強弱指標）
        df["rsi"] = ta.momentum.RSIIndicator(
            close=df["close"], window=self.rsi_period
        ).rsi()

        # ATR（平均真實範圍）
        df["atr"] = ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=self.atr_period
        ).average_true_range()

        # 成交量移動平均（20 根 K 線）
        df["volume_ma"] = df["volume"].rolling(window=20).mean()

        # MACD 交叉訊號偵測
        df["macd_cross_up"] = (df["macd"] > df["macd_signal"]) & (
            df["macd"].shift(1) <= df["macd_signal"].shift(1)
        )
        df["macd_cross_down"] = (df["macd"] < df["macd_signal"]) & (
            df["macd"].shift(1) >= df["macd_signal"].shift(1)
        )

        return df

    def get_signal(self, df: pd.DataFrame) -> dict | None:
        """
        根據多重條件產生交易訊號。

        做多條件：
        - MACD 上穿訊號線
        - RSI < 65（未過度買入）
        - 價格 > 慢線 EMA
        - 成交量 > 平均值
        - 1 小時趨勢向上

        做空條件：
        - MACD 下穿訊號線
        - RSI > 35（未過度賣出）
        - 價格 < 慢線 EMA
        - 成交量 > 平均值
        - 1 小時趨勢向下
        """
        df = self.calculate_indicators(df)

        # 需要足夠的資料來計算所有指標
        min_bars = max(self.slow_ema, self.rsi_period, self.atr_period) + 10
        if len(df) < min_bars:
            return None

        # 使用倒數第二根 K 線（已完成的 K 線，避免用未完成的數據做判斷）
        latest = df.iloc[-2]
        current_price: float = float(df.iloc[-1]["close"])  # 使用最新價作為入場參考
        atr: float = float(latest["atr"])

        # 檢查指標數值是否有效
        if any(
            pd.isna(latest[col])
            for col in [
                "macd",
                "macd_signal",
                "rsi",
                "atr",
                "ema_slow",
                "volume_ma",
            ]
        ):
            return None

        # === 條件檢查 ===

        # MACD 交叉
        macd_cross_up: bool = bool(latest["macd_cross_up"])
        macd_cross_down: bool = bool(latest["macd_cross_down"])

        # RSI 過濾
        rsi: float = float(latest["rsi"])
        rsi_ok_long: bool = rsi < self.rsi_overbought
        rsi_ok_short: bool = rsi > self.rsi_oversold

        # 價格與慢線 EMA 的關係
        ema_slow: float = float(latest["ema_slow"])
        price_above_ema: bool = current_price > ema_slow
        price_below_ema: bool = current_price < ema_slow

        # 成交量過濾（降低門檻：高於平均即可）
        volume_ok: bool = True
        if self.volume_filter:
            volume: float = float(latest["volume"])
            volume_ma: float = float(latest["volume_ma"])
            volume_ok = volume > volume_ma * 1.0  # 只要高於平均

        # 較高時間框架趨勢確認
        htf_trend_up, htf_trend_down = self._check_htf_trend()

        # === 訊號產生 ===

        # 做多訊號
        if (
            macd_cross_up
            and rsi_ok_long
            and price_above_ema
            and volume_ok
            and htf_trend_up
        ):
            stop_loss = current_price - (atr * self.atr_sl_multiplier)
            take_profit = current_price + (atr * self.atr_tp_multiplier)

            reasons: list[str] = [
                "MACD 金叉",
                f"RSI={rsi:.1f}",
                "價格在慢線上方",
            ]
            if self.volume_filter:
                reasons.append("成交量確認")
            if self._htf_data is not None:
                reasons.append("1H 趨勢向上")

            return {
                "side": "LONG",
                "entry": current_price,
                "stop_loss": round(stop_loss, 6),
                "take_profit": round(take_profit, 6),
                "reason": "趨勢做多：" + "、".join(reasons),
            }

        # 做空訊號
        if (
            macd_cross_down
            and rsi_ok_short
            and price_below_ema
            and volume_ok
            and htf_trend_down
        ):
            stop_loss = current_price + (atr * self.atr_sl_multiplier)
            take_profit = current_price - (atr * self.atr_tp_multiplier)

            reasons = [
                "MACD 死叉",
                f"RSI={rsi:.1f}",
                "價格在慢線下方",
            ]
            if self.volume_filter:
                reasons.append("成交量確認")
            if self._htf_data is not None:
                reasons.append("1H 趨勢向下")

            return {
                "side": "SHORT",
                "entry": current_price,
                "stop_loss": round(stop_loss, 6),
                "take_profit": round(take_profit, 6),
                "reason": "趨勢做空：" + "、".join(reasons),
            }

        return None

    def get_strategy_name(self) -> str:
        """回傳策略名稱"""
        return "TrendStrategy"

    def _check_htf_trend(self) -> tuple[bool, bool]:
        """
        檢查較高時間框架（1 小時）的趨勢方向。

        使用 EMA 判斷：
        - 快線 EMA > 慢線 EMA -> 趨勢向上
        - 快線 EMA < 慢線 EMA -> 趨勢向下

        回傳：
            (趨勢向上, 趨勢向下)
        """
        # 若無較高時間框架資料，預設允許交易
        if self._htf_data is None or self._htf_data.empty:
            return True, True

        df_htf = self._htf_data.copy()

        # 計算 1 小時 EMA
        htf_ema_fast = ta.trend.EMAIndicator(
            close=df_htf["close"], window=self.fast_ema
        ).ema_indicator()

        htf_ema_slow = ta.trend.EMAIndicator(
            close=df_htf["close"], window=self.slow_ema
        ).ema_indicator()

        if htf_ema_fast.empty or htf_ema_slow.empty:
            return True, True

        latest_fast: float = float(htf_ema_fast.iloc[-1])
        latest_slow: float = float(htf_ema_slow.iloc[-1])

        if pd.isna(latest_fast) or pd.isna(latest_slow):
            return True, True

        trend_up: bool = latest_fast > latest_slow
        trend_down: bool = latest_fast < latest_slow

        return trend_up, trend_down
