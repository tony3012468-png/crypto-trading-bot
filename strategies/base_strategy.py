from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    """所有交易策略的抽象基礎類別"""

    def __init__(self, config: dict):
        self.config = config
        self.name = "base"

    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """計算策略專用的技術指標"""
        pass

    @abstractmethod
    def get_signal(self, df: pd.DataFrame) -> dict | None:
        """
        回傳交易訊號字典，或 None 表示無訊號。

        回傳格式:
        {
            'side': 'LONG' | 'SHORT',
            'entry': float,       # 進場價格
            'stop_loss': float,   # 停損價格
            'take_profit': float, # 停利價格
            'reason': str         # 訊號原因說明
        }
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """回傳策略名稱"""
        pass
