"""
Telegram 通知模組 - 即時推播交易訊息到手機
"""

import os
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram 通知推播"""

    def __init__(self, config: dict):
        load_dotenv()
        self.enabled = config.get("notifications", {}).get("telegram_enabled", False)
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.notify_on_trade = config.get("notifications", {}).get("notify_on_trade", True)
        self.notify_on_error = config.get("notifications", {}).get("notify_on_error", True)

        if self.enabled and (not self.bot_token or not self.chat_id):
            logger.warning("Telegram 已啟用但缺少 BOT_TOKEN 或 CHAT_ID，已自動停用")
            self.enabled = False

        if self.enabled:
            logger.info("Telegram 通知已啟用")

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """發送訊息到 Telegram"""
        if not self.enabled:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            else:
                logger.warning(f"Telegram 發送失敗: {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"Telegram 發送錯誤: {e}")
            return False

    def notify_trade_open(
        self, symbol: str, side: str, entry_price: float,
        amount: float, stop_loss: float, take_profit: float,
        strategy: str = ""
    ):
        """通知開倉"""
        if not self.notify_on_trade:
            return

        emoji = "\U0001f7e2" if side == "LONG" else "\U0001f534"
        msg = (
            f"{emoji} <b>開倉 | {side}</b>\n"
            f"交易對: <code>{symbol}</code>\n"
            f"策略: {strategy}\n"
            f"進場價: <code>{entry_price:.6f}</code>\n"
            f"數量: <code>{amount}</code>\n"
            f"停損: <code>{stop_loss:.6f}</code>\n"
            f"停利: <code>{take_profit:.6f}</code>\n"
            f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.send_message(msg)

    def notify_trade_close(
        self, symbol: str, side: str, pnl: float,
        pnl_pct: float, exit_reason: str = ""
    ):
        """通知平倉"""
        if not self.notify_on_trade:
            return

        emoji = "\U0001f4b0" if pnl >= 0 else "\U0001f4b8"
        result = "獲利" if pnl >= 0 else "虧損"
        msg = (
            f"{emoji} <b>平倉 | {result}</b>\n"
            f"交易對: <code>{symbol}</code>\n"
            f"方向: {side}\n"
            f"盈虧: <code>{pnl:+.2f} USDT ({pnl_pct:+.2f}%)</code>\n"
            f"原因: {exit_reason}\n"
            f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.send_message(msg)

    def notify_error(self, error_msg: str):
        """通知錯誤"""
        if not self.notify_on_error:
            return

        msg = (
            f"\u26a0\ufe0f <b>機器人警告</b>\n"
            f"<code>{error_msg}</code>\n"
            f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.send_message(msg)

    def notify_daily_summary(
        self, balance: float, daily_pnl: float,
        total_trades: int, win_rate: float, drawdown: float
    ):
        """每日摘要通知"""
        emoji = "\U0001f4c8" if daily_pnl >= 0 else "\U0001f4c9"
        msg = (
            f"\U0001f4ca <b>每日摘要</b>\n"
            f"{'='*30}\n"
            f"帳戶餘額: <code>{balance:.2f} USDT</code>\n"
            f"今日盈虧: <code>{daily_pnl:+.2f} USDT</code> {emoji}\n"
            f"總交易數: <code>{total_trades}</code>\n"
            f"勝率: <code>{win_rate:.1f}%</code>\n"
            f"當前回撤: <code>{drawdown:.1f}%</code>\n"
            f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.send_message(msg)

    def notify_bot_start(self, symbols: list, strategy: str):
        """通知機器人啟動"""
        msg = (
            f"\U0001f916 <b>機器人已啟動</b>\n"
            f"交易對: {', '.join(symbols)}\n"
            f"策略: {strategy}\n"
            f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.send_message(msg)

    def notify_bot_stop(self, reason: str = "手動停止"):
        """通知機器人停止"""
        msg = (
            f"\U0001f6d1 <b>機器人已停止</b>\n"
            f"原因: {reason}\n"
            f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.send_message(msg)

    def send_document(self, file_path: str, caption: str = "") -> bool:
        """發送文檔/圖片到 Telegram"""
        if not self.enabled:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"
            with open(file_path, 'rb') as f:
                files = {'document': f}
                payload = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                }
                response = requests.post(url, data=payload, files=files, timeout=30)
                if response.status_code == 200:
                    return True
                else:
                    logger.warning(f"Telegram 文檔發送失敗: {response.status_code}")
                    return False
        except Exception as e:
            logger.warning(f"Telegram 文檔發送錯誤: {e}")
            return False

    def send_photo(self, file_path: str, caption: str = "") -> bool:
        """發送照片到 Telegram"""
        if not self.enabled:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            with open(file_path, 'rb') as f:
                files = {'photo': f}
                payload = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                }
                response = requests.post(url, data=payload, files=files, timeout=30)
                if response.status_code == 200:
                    return True
                else:
                    logger.warning(f"Telegram 照片發送失敗: {response.status_code}")
                    return False
        except Exception as e:
            logger.warning(f"Telegram 照片發送錯誤: {e}")
            return False

    def notify_daily_report(self, report: dict):
        """發送每日報告（含圖表）"""
        # 先發送摘要文本
        self.send_message(report["summary"])

        # 如果有圖表，發送圖表
        if report.get("chart_path"):
            try:
                self.send_photo(
                    report["chart_path"],
                    caption=f"📊 {report['date']} 詳細圖表"
                )
            except Exception as e:
                logger.warning(f"無法發送圖表: {e}")
