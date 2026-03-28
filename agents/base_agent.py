"""
基礎代理類 - 所有部門的共同基底

每個部門都繼承此類，實現各自的 analyze() 與 generate_report()。
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class BaseAgent(ABC):
    """所有部門代理的基礎類別"""

    name: str = "未命名部門"
    role: str = "未定義職責"
    emoji: str = "🤖"

    def __init__(self, config: dict, exchange=None, notifier=None):
        """
        Args:
            config: 完整設定檔字典
            exchange: BinanceExchange 實例（可選）
            notifier: TelegramNotifier 實例（可選）
        """
        self.config = config
        self.exchange = exchange
        self.notifier = notifier
        self.logger = logging.getLogger(self.__class__.__name__)
        self._last_report: str = ""
        self._last_analysis: dict = {}

    @abstractmethod
    def analyze(self) -> dict[str, Any]:
        """
        執行部門核心分析。

        Returns:
            分析結果字典，內容由各部門自定義
        """

    @abstractmethod
    def generate_report(self) -> str:
        """
        根據最新分析結果生成文字報告。

        Returns:
            格式化的純文字報告（適合 Telegram 發送）
        """

    def run(self) -> str:
        """
        執行分析並返回報告（標準流程）。

        Returns:
            報告文字
        """
        self.logger.info(f"[{self.name}] 開始執行分析...")
        try:
            self._last_analysis = self.analyze()
            self._last_report = self.generate_report()
            self.logger.info(f"[{self.name}] 分析完成")
        except Exception as e:
            self.logger.error(f"[{self.name}] 分析失敗: {e}")
            self._last_report = f"{self.emoji} [{self.name}] 分析失敗: {e}"
        return self._last_report

    def send_report(self, custom_message: str = None) -> bool:
        """
        通過 Telegram 發送報告。

        Args:
            custom_message: 若指定，發送此訊息而非自動生成的報告

        Returns:
            True 表示發送成功
        """
        if self.notifier is None:
            self.logger.warning(f"[{self.name}] 未配置通知器，無法發送報告")
            return False

        message = custom_message or self._last_report
        if not message:
            message = self.run()

        try:
            self.notifier.send_message(message)
            self.logger.info(f"[{self.name}] 報告已發送至 Telegram")
            return True
        except Exception as e:
            self.logger.error(f"[{self.name}] 發送報告失敗: {e}")
            return False

    def get_last_analysis(self) -> dict:
        """取得最近一次分析結果"""
        return self._last_analysis

    def get_last_report(self) -> str:
        """取得最近一次報告文字"""
        return self._last_report

    @staticmethod
    def _now_str() -> str:
        """返回當前時間字串"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.name}>"
