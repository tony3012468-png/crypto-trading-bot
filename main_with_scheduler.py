"""
Crypto Trading Bot with Daily Report Scheduler
帶每日報告調度的交易機器人主程序

排程時間表：
  每天 19:00  → 每日整合報告（8 個部門）
  每週日 20:00 → 老闆週報（KPI 進度）
  每天 00:00  → 每日情報員警報重置
"""

import sys
import time
import logging
from datetime import datetime
from pathlib import Path

import yaml
from apscheduler.schedulers.background import BackgroundScheduler

# 設定專案根目錄
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from main import main as run_trading_bot
from report_generator import DailyReportGenerator
from notifications.telegram_bot import TelegramNotifier
from core.exchange import BinanceExchange
from agents import TradingCompany


logger = logging.getLogger(__name__)


class BotWithScheduler:
    """帶報告調度的交易機器人 + TradingCompany 整合"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = PROJECT_DIR / config_path

        with open(self.config_path, "r", encoding="utf-8-sig") as f:
            self.config = yaml.safe_load(f)

        self.notifier = TelegramNotifier(self.config)

        # 初始化交易所連線（供回測工程師使用）
        try:
            self.exchange = BinanceExchange(self.config)
        except Exception as e:
            logger.warning(f"排程器交易所初始化失敗: {e}")
            self.exchange = None

        # 初始化公司（8 個部門）
        self.company = TradingCompany(
            config=self.config,
            exchange=self.exchange,
            notifier=self.notifier,
            risk_manager=None,
        )

        self.report_hour = self.config.get("scheduler", {}).get("daily_report_hour", 19)
        self.report_minute = self.config.get("scheduler", {}).get("daily_report_minute", 0)

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

    # ──────────────────────────────────────────────
    # 排程任務
    # ──────────────────────────────────────────────

    def generate_daily_report(self):
        """每天 19:00 → 原始每日報告 + 各部門整合報告"""
        try:
            logger.info("=" * 60)
            logger.info("開始生成每日報告...")
            logger.info("=" * 60)

            # 1. 原始圖表報告（保留原有功能）
            generator = DailyReportGenerator(self.config)
            report = generator.generate_report()
            if self.notifier.enabled:
                self.notifier.notify_daily_report(report)

            # 2. 各部門整合報告
            self.company.send_daily_report()

            logger.info("每日報告生成完成")
        except Exception as e:
            logger.error(f"生成每日報告時出錯: {e}")
            try:
                self.notifier.notify_error(f"報告生成失敗: {str(e)}")
            except Exception:
                pass

    def generate_weekly_report(self):
        """每週日 20:00 → 老闆週報"""
        try:
            logger.info("開始生成每週老闆週報...")
            # 嘗試從 risk_manager 取得績效數據
            risk_status = None
            if self.company.risk_officer.risk_manager:
                risk_status = self.company.risk_officer.risk_manager.get_status()

            self.company.send_weekly_report(risk_status)
            logger.info("每週老闆週報已發送")
        except Exception as e:
            logger.error(f"生成週報失敗: {e}")

    def reset_daily_intelligence(self):
        """每天 00:00 → 重置情報員的每日警報"""
        try:
            self.company.reset_daily()
            logger.info("情報員每日警報已重置")
        except Exception as e:
            logger.error(f"重置情報員失敗: {e}")

    def run_daily_research(self):
        """
        每天 09:00 → 策略開發員選策略 → 回測工程師多策略競賽 → 量化研究員評估
        目標：每天自動探索更優策略，複合評分排名，持續進化
        """
        try:
            logger.info("開始每日策略研究（多策略競賽模式）...")

            # 步驟 1：策略開發員選出今日候選策略
            today_strategies = self.company.strategy_developer.get_today_strategies()
            logger.info(f"[策略開發員] 共 {len(today_strategies)} 個策略待競賽")

            # 步驟 2：回測工程師執行多策略競賽回測
            multi_results = self.company.backtest_engineer.run_multi_strategy_backtest(today_strategies)

            # 步驟 3：策略開發員更新評分與淘汰
            if multi_results:
                self.company.strategy_developer.update_scores(multi_results)

            # 步驟 4：當前實盤策略基準回測
            backtest_results = self.company.backtest_engineer.run_auto_backtest()
            if backtest_results:
                perf_summary = self.company.backtest_engineer.get_performance_summary()
                if perf_summary:
                    self.company.quant_researcher.update_performance(perf_summary)

            # 步驟 5：各部門生成報告
            developer_report = self.company.strategy_developer.run()
            backtest_report = self.company.backtest_engineer.run()
            researcher_report = self.company.quant_researcher.run()
            signal_report = self.company.signal_engineer.run()

            research_summary = (
                "📋 每日策略研究簡報\n"
                f"{'=' * 35}\n"
                f"{developer_report}\n\n"
                f"{backtest_report}\n\n"
                f"{researcher_report}\n\n"
                f"{signal_report}"
            )
            self.company._send_long_message(research_summary)

            # 步驟 6：若發現高分策略，主管向老闆發警報
            best = self.company.strategy_developer.get_best_strategies(1)
            if best:
                top = best[0]
                score = top.get("score", {})
                if score.get("composite_score", 0) > 0.65:
                    alert = (
                        f"🔔 策略研究重要發現！\n"
                        f"高分策略：{top['id']}\n"
                        f"類型：{top['type']} | 複合評分：{score['composite_score']:.3f}\n"
                        f"勝率：{score['win_rate']:.1f}% | PF：{score['profit_factor']:.2f}\n"
                        f"夏普：{score['sharpe']:.2f} | 索提諾：{score['sortino']:.2f}\n"
                        f"主管建議：達到採用門檻，請老闆確認是否切換實盤策略"
                    )
                    self.company._send_long_message(alert)

            logger.info("每日策略研究完成")
        except Exception as e:
            logger.error(f"每日策略研究失敗: {e}")

    # ──────────────────────────────────────────────
    # 排程器設置
    # ──────────────────────────────────────────────

    def start_scheduler(self):
        """啟動排程器（4 個任務）"""
        scheduler = BackgroundScheduler()

        # 任務 1：每天 19:00 每日報告
        scheduler.add_job(
            self.generate_daily_report,
            "cron",
            hour=self.report_hour,
            minute=self.report_minute,
            id="daily_report",
            name="Daily Integrated Report",
            replace_existing=True,
        )

        # 任務 2：每週三 20:00 老闆週報
        scheduler.add_job(
            self.generate_weekly_report,
            "cron",
            day_of_week="wed",
            hour=20,
            minute=0,
            id="weekly_report",
            name="Weekly Boss Report (Wednesday)",
            replace_existing=True,
        )

        # 任務 3：每天 00:00 重置情報員
        scheduler.add_job(
            self.reset_daily_intelligence,
            "cron",
            hour=0,
            minute=0,
            id="daily_reset",
            name="Daily Intelligence Reset",
            replace_existing=True,
        )

        # 任務 4：每天 09:00 每日策略研究（量化研究員 + 回測工程師 + 信號工程師）
        scheduler.add_job(
            self.run_daily_research,
            "cron",
            hour=9,
            minute=0,
            id="daily_research",
            name="Daily Strategy Research",
            replace_existing=True,
        )

        scheduler.start()
        logger.info(f"✅ 排程器已啟動（4 個任務）")
        logger.info(f"   每天 09:00 → 每日策略研究（回測工程師自動回測 + 量化研究員 + 信號）")
        logger.info(f"   每天 {self.report_hour:02d}:{self.report_minute:02d} → 每日整合報告（8 部門）")
        logger.info(f"   每週三 20:00 → 老闆週報（KPI 進度）")
        logger.info(f"   每天 00:00 → 情報員警報重置")

        return scheduler

    # ──────────────────────────────────────────────
    # 主入口
    # ──────────────────────────────────────────────

    def run(self):
        """運行機器人和排程器"""
        self.setup_logging()

        logger.info("=" * 60)
        logger.info("Crypto Trading Bot with Scheduler v3.0")
        logger.info(f"🏢 {TradingCompany.COMPANY_NAME} | 8 個部門已就位")
        logger.info(f"🎯 月度目標：{TradingCompany.MONTHLY_TARGET} USDT 利潤")
        logger.info("=" * 60)

        # 啟動排程器
        scheduler = self.start_scheduler()

        # 發送啟動通知
        try:
            logger.info("發送啟動通知...")
            self.notifier.notify_bot_start(
                ["BTC/USDT:USDT", "ETH/USDT:USDT"],
                "動態選幣 + 趨勢跟踪 | TradingCompany v3.0"
            )
        except Exception as e:
            logger.warning(f"發送啟動通知失敗: {e}")

        # 運行交易機器人（主線程），共享同一個 TradingCompany 實例
        try:
            logger.info("啟動交易機器人...")
            run_trading_bot(self.company)
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
