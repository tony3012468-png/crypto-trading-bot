import numpy as np
import pandas as pd
import ta

from strategies.base_strategy import BaseStrategy


class GridStrategy(BaseStrategy):
    """
    網格交易策略 - 適用於震盪/橫盤市場。

    運作原理：
    1. 使用近期最高/最低價偵測目前價格區間
    2. 在區間內建立買賣網格
    3. 當價格觸及網格線時：
       - 在下方網格買入（做多）
       - 在上方網格賣出（做空）
    4. 每次網格交易設定小額停利（grid_spacing / 2）
    5. 透過價格在區間內的來回震盪獲利
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "grid"

        # 從設定檔讀取網格參數
        grid_cfg = config.get("grid", {})
        self.grid_count: int = grid_cfg.get("grid_count", 8)
        self.grid_spacing_pct: float = grid_cfg.get("grid_spacing_pct", 0.4) / 100.0
        self.position_per_grid: float = grid_cfg.get("position_per_grid", 0.10)
        self.take_profit_pct: float = grid_cfg.get("take_profit_pct", 0.3) / 100.0
        self.lookback_bars: int = grid_cfg.get("lookback_bars", 96)

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        計算網格策略所需的技術指標。

        包含：支撐/阻力位、區間邊界、ATR。
        """
        df = df.copy()

        # 計算 ATR（平均真實範圍）
        df["atr"] = ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=14
        ).average_true_range()

        # 計算近期最高/最低（用於偵測價格區間）
        df["range_high"] = df["high"].rolling(window=self.lookback_bars).max()
        df["range_low"] = df["low"].rolling(window=self.lookback_bars).min()

        # 計算價格在區間中的相對位置（0 = 最低, 1 = 最高）
        range_size = df["range_high"] - df["range_low"]
        df["range_position"] = np.where(
            range_size > 0,
            (df["close"] - df["range_low"]) / range_size,
            0.5,
        )

        return df

    def get_signal(self, df: pd.DataFrame) -> dict | None:
        """
        檢查價格是否接近網格線，回傳買/賣訊號。

        回傳訊號包含：
        - side: LONG 或 SHORT
        - entry: 目前價格
        - stop_loss: 區間外側
        - take_profit: 下一個網格線
        - reason: 訊號原因
        """
        df = self.calculate_indicators(df)

        if df.empty or len(df) < self.lookback_bars:
            return None

        # 取得最新一根 K 線的資料
        latest = df.iloc[-1]
        current_price: float = float(latest["close"])
        atr: float = float(latest["atr"])

        # 偵測目前價格區間
        range_high, range_low = self._detect_range(df)
        if range_high is None or range_low is None:
            return None

        # 區間太小則不交易（避免手續費吃掉利潤）
        range_size = range_high - range_low
        if range_size <= 0 or range_size / current_price < 0.005:
            return None

        # 建立網格線
        grid_levels = self._calculate_grid_levels(range_high, range_low)
        if not grid_levels:
            return None

        # 找到最接近的網格線
        nearest_level, level_index = self._find_nearest_grid(current_price, grid_levels)
        if nearest_level is None:
            return None

        # 計算價格與最近網格線的距離（百分比）
        distance_pct = abs(current_price - nearest_level) / current_price

        # 價格必須足夠接近網格線才觸發訊號（在 grid_spacing 的一半範圍內）
        trigger_threshold = self.grid_spacing_pct / 2.0
        if distance_pct > trigger_threshold:
            return None

        # 根據網格位置決定方向
        mid_index = len(grid_levels) // 2

        # 計算網格間距（用於控制停損距離）
        grid_step = (range_high - range_low) / max(self.grid_count - 1, 1)

        if level_index < mid_index:
            # 下半部網格 -> 買入（做多）
            # 停損：入場價下方 2 倍網格間距（不用整個區間）
            stop_loss = current_price - (grid_step * 2.0)
            # 停利：入場價上方 1.5 倍網格間距（R:R ≈ 0.75:1）
            take_profit = current_price * (1 + self.take_profit_pct * 2)

            return {
                "side": "LONG",
                "entry": current_price,
                "stop_loss": round(stop_loss, 6),
                "take_profit": round(take_profit, 6),
                "reason": f"網格買入：第 {level_index + 1} 層 @ {nearest_level:.6f}",
            }

        elif level_index > mid_index:
            # 上半部網格 -> 賣出（做空）
            stop_loss = current_price + (grid_step * 2.0)
            take_profit = current_price * (1 - self.take_profit_pct * 2)

            return {
                "side": "SHORT",
                "entry": current_price,
                "stop_loss": round(stop_loss, 6),
                "take_profit": round(take_profit, 6),
                "reason": f"網格賣出：第 {level_index + 1} 層 @ {nearest_level:.6f}",
            }

        # 中間層不交易
        return None

    def get_strategy_name(self) -> str:
        """回傳策略名稱"""
        return "GridStrategy"

    def _detect_range(self, df: pd.DataFrame) -> tuple[float | None, float | None]:
        """
        使用近期最高/最低價偵測目前價格區間。

        回傳 (區間上緣, 區間下緣)，若無法偵測則回傳 (None, None)。
        """
        if df.empty or len(df) < self.lookback_bars:
            return None, None

        latest = df.iloc[-1]
        range_high: float = float(latest["range_high"])
        range_low: float = float(latest["range_low"])

        if pd.isna(range_high) or pd.isna(range_low):
            return None, None

        return range_high, range_low

    def _calculate_grid_levels(
        self, range_high: float, range_low: float
    ) -> list[float]:
        """
        在價格區間內產生等距的網格線。

        參數：
            range_high: 區間上緣
            range_low: 區間下緣

        回傳：
            由低到高排序的網格價格列表
        """
        if self.grid_count < 2:
            return []

        grid_step = (range_high - range_low) / (self.grid_count - 1)
        if grid_step <= 0:
            return []

        grid_levels = [
            round(range_low + i * grid_step, 8) for i in range(self.grid_count)
        ]

        return grid_levels

    def _find_nearest_grid(
        self, current_price: float, grid_levels: list[float]
    ) -> tuple[float | None, int]:
        """
        找到目前價格最接近的網格線。

        參數：
            current_price: 目前價格
            grid_levels: 網格價格列表

        回傳：
            (最接近的網格價格, 該網格的索引)
        """
        if not grid_levels:
            return None, -1

        distances = [abs(current_price - level) for level in grid_levels]
        min_index = int(np.argmin(distances))

        return grid_levels[min_index], min_index
