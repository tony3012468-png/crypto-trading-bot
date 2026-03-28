"""
TradingCompany - 交易公司總部協調器

部門架構（9 個部門）：
  🧪 策略開發員   (StrategyDeveloper)   - 每日生成策略組合、管理策略庫、淘汰機制
  🔬 量化研究員   (QuantResearcher)     - 策略研究、Alpha 因子
  📈 回測工程師   (BacktestEngineer)    - 歷史回測、多策略競賽、複合評分排名
  🛡️ 風控官      (RiskOfficer)        - 風險評估、預警
  📡 信號工程師   (SignalEngineer)      - 技術指標、信號品質
  ⚙️ 執行工程師   (ExecutionEngineer)  - API 執行、訂單管理
  📊 市場分析師   (MarketAnalyst)       - 即時行情、選幣建議
  🕵️ 情報員      (IntelligenceAgent)   - 市場事件、異常波動
  📅 績效追蹤員   (PerformanceTracker)  - KPI 週報、月目標追蹤

公司月度目標：200 USDT 利潤
建議啟動資金：3,000 USDT（量化研究員評估）
"""

import logging
from agents.strategy_developer import StrategyDeveloper
from agents.quant_researcher import QuantResearcher
from agents.backtester import BacktestEngineer
from agents.risk_officer import RiskOfficer
from agents.signal_engineer import SignalEngineer
from agents.execution_engineer import ExecutionEngineer
from agents.market_analyst import MarketAnalyst
from agents.intelligence_agent import IntelligenceAgent
from agents.performance_tracker import PerformanceTracker

logger = logging.getLogger(__name__)


class TradingCompany:
    """
    交易公司總部 - 統一協調 8 個部門

    主程式只需建立此實例，其餘由各部門各司其職。
    """

    COMPANY_NAME = "Crypto Trading Co."
    MONTHLY_TARGET = 200.0  # USDT

    def __init__(self, config: dict, exchange=None, notifier=None, risk_manager=None):
        self.config = config
        self.exchange = exchange
        self.notifier = notifier

        # -- 建立 9 個部門 --
        self.strategy_developer  = StrategyDeveloper(config, exchange, notifier)
        self.quant_researcher    = QuantResearcher(config, exchange, notifier)
        self.backtest_engineer   = BacktestEngineer(config, exchange, notifier)
        self.risk_officer        = RiskOfficer(config, risk_manager, exchange, notifier)
        self.signal_engineer     = SignalEngineer(config, exchange, notifier)
        self.execution_engineer  = ExecutionEngineer(config, exchange, notifier)
        self.market_analyst      = MarketAnalyst(config, exchange, notifier)
        self.intelligence_agent  = IntelligenceAgent(config, exchange, notifier)
        self.performance_tracker = PerformanceTracker(config, exchange, notifier)

        # 報告用部門列表（每日報告包含這些）
        self._report_departments = [
            self.risk_officer,
            self.market_analyst,
            self.signal_engineer,
            self.execution_engineer,
            self.intelligence_agent,
            self.quant_researcher,
        ]

        logger.info(f"[{self.COMPANY_NAME}] 公司初始化完成，9 個部門已就位")
        logger.info(f"[{self.COMPANY_NAME}] 月度目標：{self.MONTHLY_TARGET} USDT 利潤")

    # ----------------------------------------------
    # 報告接口
    # ----------------------------------------------

    def generate_daily_report(self) -> str:
        """生成每日整合報告（整合所有部門的分析）"""
        logger.info(f"[{self.COMPANY_NAME}] 開始生成每日整合報告...")
        sections = [
            f"🏢 {self.COMPANY_NAME} 每日報告",
            f"{'═' * 40}",
        ]

        for dept in self._report_departments:
            try:
                report = dept.run()
                sections.append(report)
                sections.append("")
            except Exception as e:
                sections.append(f"{dept.emoji} [{dept.name}] 報告生成失敗: {e}")

        sections += [f"{'═' * 40}", "每日報告結束 ✅"]
        return "\n".join(sections)

    def send_daily_report(self):
        """生成並分段發送每日報告至 Telegram"""
        report = self.generate_daily_report()
        if self.notifier:
            self._send_long_message(report)
        else:
            logger.warning("未配置通知器，無法發送每日報告")

    def send_weekly_report(self, risk_status: dict = None):
        """
        生成並發送每週老闆週報（由排程器在每週日調用）。

        Args:
            risk_status: 來自 RiskManager.get_status() 的狀態字典
        """
        if risk_status:
            self.performance_tracker.record_weekly_snapshot(
                balance=risk_status.get("current_balance", 0),
                weekly_pnl=risk_status.get("weekly_pnl", risk_status.get("daily_pnl", 0)),
                trade_count=risk_status.get("trade_count", 0),
                win_rate=risk_status.get("win_rate", 0),
            )

        self.performance_tracker._last_analysis = self.performance_tracker.analyze()
        report = self.performance_tracker.generate_report()

        if self.notifier:
            self._send_long_message(report)
            logger.info(f"[{self.COMPANY_NAME}] 週報已發送")
        else:
            logger.warning("未配置通知器，無法發送週報")

    def get_department_report(self, dept_name: str) -> str:
        """取得特定部門的即時報告"""
        all_depts = self._report_departments + [
            self.backtest_engineer,
            self.performance_tracker,
        ]
        for dept in all_depts:
            if dept.name == dept_name:
                return dept.run()
        return f"找不到部門：{dept_name}"

    # ----------------------------------------------
    # 數據更新接口（由主程式每次掃描後調用）
    # ----------------------------------------------

    def update_market_states(self, market_states: dict):
        """更新市場分析師的市場狀態"""
        self.market_analyst.update_market_states(market_states)

    def update_tickers(self, tickers: dict):
        """
        更新情報員的市場快照並掃描異常波動。
        若發現極端異動，自動發送 Telegram 預警。
        """
        self.intelligence_agent.update_snapshot(tickers)
        alerts = self.intelligence_agent.scan_volatility(tickers)
        extreme = [a for a in alerts if a["level"] == "extreme"]
        if extreme:
            self.intelligence_agent.send_extreme_alert(extreme)

    def record_signal(self, symbol: str, signal: dict):
        """記錄新交易信號"""
        self.signal_engineer.record_signal(symbol, signal)

    def record_trade_result(self, symbol: str, entry_price: float,
                             actual_price: float, side: str,
                             pnl: float, result: str):
        """記錄交易結果，同步更新相關部門"""
        self.signal_engineer.update_signal_result(symbol, entry_price, result)
        self.execution_engineer.record_execution(
            symbol, entry_price, actual_price, side, success=True
        )

    def check_risk_alerts(self) -> bool:
        """快速風險檢查（每次掃描後調用）"""
        return self.risk_officer.check_and_alert()

    def sync_performance_to_researcher(self):
        """將風控官的績效數據同步給量化研究員"""
        if self.risk_officer.risk_manager:
            status = self.risk_officer.risk_manager.get_status()
            self.quant_researcher.update_performance({
                "win_rate": status.get("win_rate", 0),
                "profit_factor": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "total_trades": status.get("trade_count", 0),
                "total_pnl": status.get("total_pnl", 0),
                "max_drawdown": status.get("drawdown_pct", 0),
            })

    def reset_daily(self):
        """每日重置（重置情報員警報等）"""
        self.intelligence_agent.clear_daily_alerts()

    # ----------------------------------------------
    # 私有工具
    # ----------------------------------------------

    def _send_long_message(self, text: str, max_length: int = 4000):
        """Telegram 4096 字元限制，超過時分段發送"""
        if len(text) <= max_length:
            try:
                self.notifier.send_message(text)
            except Exception as e:
                logger.error(f"發送報告失敗: {e}")
            return

        paragraphs = text.split("\n\n")
        chunk = ""
        for para in paragraphs:
            if len(chunk) + len(para) + 2 > max_length:
                if chunk:
                    try:
                        self.notifier.send_message(chunk.strip())
                    except Exception as e:
                        logger.error(f"發送分段失敗: {e}")
                chunk = para + "\n\n"
            else:
                chunk += para + "\n\n"
        if chunk.strip():
            try:
                self.notifier.send_message(chunk.strip())
            except Exception as e:
                logger.error(f"發送分段失敗: {e}")

    def __repr__(self) -> str:
        return f"<TradingCompany 8 departments | target={self.MONTHLY_TARGET} USDT/month>"


__all__ = [
    "TradingCompany",
    "QuantResearcher",
    "BacktestEngineer",
    "RiskOfficer",
    "SignalEngineer",
    "ExecutionEngineer",
    "MarketAnalyst",
    "IntelligenceAgent",
    "PerformanceTracker",
]
