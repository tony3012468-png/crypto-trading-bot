import pandas as pd
import ta

from strategies.base_strategy import BaseStrategy
from strategies.grid_strategy import GridStrategy
from strategies.trend_strategy import TrendStrategy


class StrategySelector:
    """
    策略自動選擇器 - 根據市場狀態自動選擇最佳策略。

    使用 ADX（平均方向性指標）判斷市場狀態：
    - ADX > 25：趨勢市場 -> 使用趨勢策略
    - ADX < 20：震盪市場 -> 使用網格策略
    - ADX 20-25：混合狀態 -> 使用網格策略（較安全）
    """

    def __init__(
        self,
        grid_strategy: GridStrategy,
        trend_strategy: TrendStrategy,
        config: dict | None = None,
    ):
        """
        初始化策略選擇器。

        參數：
            grid_strategy: 網格策略實例
            trend_strategy: 趨勢策略實例
            config: 完整設定檔字典（可選）
        """
        self.grid_strategy = grid_strategy
        self.trend_strategy = trend_strategy

        # 從設定檔讀取策略選擇器參數
        selector_cfg = (config or {}).get("strategy_selector", {})
        self.adx_period: int = selector_cfg.get("adx_period", 14)
        self.adx_trend_threshold: float = selector_cfg.get("adx_trend_threshold", 25)
        self.adx_range_threshold: float = selector_cfg.get("adx_range_threshold", 20)
        self.recheck_interval: int = selector_cfg.get("recheck_interval", 300)

    def select_strategy(self, df: pd.DataFrame) -> BaseStrategy:
        """
        根據市場狀態選擇最佳策略。

        參數：
            df: 價格資料 DataFrame

        回傳：
            適合目前市場狀態的策略實例
        """
        market_state = self.get_market_state(df)

        if market_state == "trending":
            return self.trend_strategy
        else:
            # 震盪或混合狀態都使用網格策略（較安全）
            return self.grid_strategy

    def get_market_state(self, df: pd.DataFrame) -> str:
        """
        使用 ADX 指標判斷目前市場狀態。

        參數：
            df: 價格資料 DataFrame

        回傳：
            "trending"（趨勢）、"ranging"（震盪）或 "mixed"（混合）
        """
        if df.empty or len(df) < self.adx_period + 10:
            # 資料不足時預設為震盪（較保守）
            return "ranging"

        # 計算 ADX
        adx_indicator = ta.trend.ADXIndicator(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=self.adx_period,
        )
        adx_values = adx_indicator.adx()

        if adx_values.empty:
            return "ranging"

        current_adx: float = float(adx_values.iloc[-1])

        if pd.isna(current_adx):
            return "ranging"

        # 根據 ADX 數值判斷市場狀態
        if current_adx > self.adx_trend_threshold:
            return "trending"
        elif current_adx < self.adx_range_threshold:
            return "ranging"
        else:
            return "mixed"
