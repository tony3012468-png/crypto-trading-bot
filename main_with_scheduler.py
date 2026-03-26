"""
Crypto Trading Bot with Daily Report Scheduler
帶每日報告調度的交易機器人主程序
"""

import sys
import time
import logging
import threading
from datetime import datetime, date, timedelta
from pathlib import Path

import yaml
from apscheduler.schedulers.background import BackgroundScheduler

# 設定專案根目錄
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from main import main as run_trading_bot
from report_generator import DailyReportGenerator
from notifications.telegram_bot import TelegramNotifier


logger = logging.getLogger(__name__)


class BotWithScheduler:
    """帶報告調度的交易機器人"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = PROJECT_DIR / config_path

        # 載入設定
        with open(self.config_path, "r", encoding="utf-8-sig") as f:
            self.config = yaml.safe_load(f)

        self.notifier = TelegramNotifier(self.config)
        self.report_hour = 19  # 每天 19:00 (7 PM)
        self.report_minute = 0

    def setup_logging(self):
        """設定日誌"""
        log_file = self.config.get("system", {}).get("log_file", "trading.log")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_file, encoding="utf-8"),
            ],
        )

    def generate_daily_report(self):
        """生成並發送每日報告"""
        try:
            logger.info("=" * 60)
            logger.info("開始生成每日報告...")
            logger.info("=" * 60)

            generator = DailyReportGenerator(self.config)
            report = generator.generate_report()

            # 通過 Telegram 發送報告
            if self.notifier.enabled:
                logger.info("正在發送 Telegram 報告...")
                self.notifier.notify_daily_report(report)
                logger.info("報告已發送到 Telegram")
            else:
                logger.warning("Telegram 未啟用，報告未發送")

            logger.info("=" * 60)
            logger.info("每日報告生成完成")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"生成每日報告時出錯: {e}")
            self.notifier.notify_error(f"報告生成失敗: {str(e)}")

    def start_scheduler(self):
        """啟動報告調度器"""
        scheduler = BackgroundScheduler()

        # 每天 19:00 運行報告生成
        scheduler.add_job(
            self.generate_daily_report,
            'cron',
            hour=self.report_hour,
            minute=self.report_minute,
            id='daily_report',
            name='Daily Report Generation',
            replace_existing=True
        )

        scheduler.start()
        logger.info(f"✅ 報告調度器已啟動 - 每天 {self.report_hour:02d}:{self.report_minute:02d} 生成報告")

        return scheduler

    def run(self):
        """運行機器人和調度器"""
        self.setup_logging()

        logger.info("=" * 60)
        logger.info("Crypto Trading Bot with Scheduler v2.0")
        logger.info("=" * 60)

        # 啟動報告調度器（後台線程）
        scheduler = self.start_scheduler()

        # 運行交易機器人（主線程）
        try:
            logger.info("啟動交易機器人...")
            run_trading_bot()
        except KeyboardInterrupt:
            logger.info("收到中止信號，正在清理...")
            scheduler.shutdown()
            logger.info("程式已停止")
        except Exception as e:
            logger.error(f"機器人運行出錯: {e}")
            scheduler.shutdown()
            raise


def main():
    """主入口"""
    bot = BotWithScheduler()
    bot.run()


if __name__ == "__main__":
    main()
