"""
風控官 (Risk Officer)

職責：
- 實時監控風控指標（回撤、連虧、每日損益）
- 評估當前風險等級（低 / 中 / 高 / 危險）
- 主動發出預警通知
- 提出倉位調整建議
"""

from datetime import datetime, timedelta

from agents.base_agent import BaseAgent
from core.risk_manager import RiskManager


class RiskOfficer(BaseAgent):
    """風控官 - 負責風險評估與倉位管理建議"""

    name = "風控官"
    role = "風險評估、回撤監控、預警通知"
    emoji = "🛡️"

    ALERT_COOLDOWN_HOURS = 1  # 同一種警報最少間隔 1 小時

    def __init__(self, config: dict, risk_manager: RiskManager = None,
                 exchange=None, notifier=None):
        super().__init__(config, exchange, notifier)
        self.risk_manager = risk_manager
        self._alert_thresholds = {
            "drawdown_warn": 0.6,   # 回撤達到最大限制的 60% 發出警告
            "drawdown_danger": 0.85, # 85% 發出危險警報
            "streak_warn": 0.6,      # 連虧達到限制的 60% 警告
        }
        # 記錄各種警報最後發送時間，避免重複轟炸
        self._last_alert_time: dict = {}

    def analyze(self) -> dict:
        """分析當前風控狀態"""
        if self.risk_manager is None:
            return {"error": "尚未連接風控管理器"}

        status = self.risk_manager.get_status()
        max_dd = self.config.get("risk", {}).get("max_drawdown_pct", 12)
        streak_limit = self.config.get("risk", {}).get("loss_streak_limit", 4)

        # 計算風險等級
        dd_pct = status.get("drawdown_pct", 0)
        streak = status.get("consecutive_losses", 0)
        daily_pnl = status.get("daily_pnl", 0)

        dd_ratio = dd_pct / max_dd if max_dd > 0 else 0
        streak_ratio = streak / streak_limit if streak_limit > 0 else 0

        risk_level = self._evaluate_risk_level(dd_ratio, streak_ratio, daily_pnl, status)
        alerts = self._generate_alerts(dd_ratio, streak_ratio, status)
        recommendation = self._generate_recommendation(risk_level, dd_ratio, streak_ratio)

        return {
            "status": status,
            "risk_level": risk_level,
            "dd_ratio": dd_ratio,
            "streak_ratio": streak_ratio,
            "alerts": alerts,
            "recommendation": recommendation,
            "can_trade": status.get("can_trade", True),
        }

    def _evaluate_risk_level(self, dd_ratio: float, streak_ratio: float,
                              daily_pnl: float, status: dict) -> str:
        """評估整體風險等級"""
        if not status.get("can_trade", True):
            return "危險"
        if dd_ratio >= self._alert_thresholds["drawdown_danger"]:
            return "高"
        if dd_ratio >= self._alert_thresholds["drawdown_warn"] or \
           streak_ratio >= self._alert_thresholds["streak_warn"]:
            return "中"
        if daily_pnl < 0 and abs(daily_pnl) > status.get("current_balance", 1) * 0.02:
            return "中"
        return "低"

    def _generate_alerts(self, dd_ratio: float, streak_ratio: float, status: dict) -> list:
        """生成預警訊息列表"""
        alerts = []
        if not status.get("can_trade", True):
            alerts.append("⛔ 交易已暫停！回撤或連虧超過限制")
        elif dd_ratio >= self._alert_thresholds["drawdown_danger"]:
            alerts.append(f"🔴 高危預警：回撤已達最大限制的 {dd_ratio*100:.0f}%")
        elif dd_ratio >= self._alert_thresholds["drawdown_warn"]:
            alerts.append(f"🟡 回撤警告：已達最大限制的 {dd_ratio*100:.0f}%")

        if streak_ratio >= self._alert_thresholds["streak_warn"]:
            streak = status.get("consecutive_losses", 0)
            limit = self.config.get("risk", {}).get("loss_streak_limit", 4)
            alerts.append(f"🟡 連虧警告：已連續虧損 {streak}/{limit} 次")

        return alerts

    def _generate_recommendation(self, risk_level: str, dd_ratio: float,
                                   streak_ratio: float) -> str:
        """根據風險等級生成建議"""
        if risk_level == "危險":
            return "立即停止交易，檢查策略參數，等待市場穩定後再重新評估"
        if risk_level == "高":
            return "降低倉位至正常的 50%，避免開新單，等待回撤收窄"
        if risk_level == "中":
            return "謹慎操作，每筆風險降低至 1%，避免逆勢交易"
        return "風控狀況良好，可按正常策略執行"

    def generate_report(self) -> str:
        """生成風控報告"""
        data = self._last_analysis
        if "error" in data:
            return f"{self.emoji} 風控官報告\n❌ {data['error']}"

        status = data.get("status", {})
        risk_level = data.get("risk_level", "未知")
        alerts = data.get("alerts", [])
        recommendation = data.get("recommendation", "")

        level_icon = {"低": "🟢", "中": "🟡", "高": "🔴", "危險": "⛔"}.get(risk_level, "⚪")

        lines = [
            f"{self.emoji} 風控官報告 | {self._now_str()}",
            "-" * 35,
            f"風險等級：{level_icon} {risk_level}",
            f"帳戶餘額：{status.get('current_balance', 0):.2f} USDT",
            f"當日損益：{status.get('daily_pnl', 0):+.2f} USDT",
            f"回撤狀況：{status.get('drawdown_pct', 0):.1f}% / {status.get('max_drawdown_pct', 12):.0f}%",
            f"連續虧損：{status.get('consecutive_losses', 0)} 次",
            f"總交易數：{status.get('trade_count', 0)} 筆",
            f"勝率：{status.get('win_rate', 0):.1f}%",
            f"可交易：{'✅ 是' if data.get('can_trade') else '❌ 否'}",
        ]

        if alerts:
            lines.append("\n⚠️ 預警訊息：")
            lines.extend(alerts)

        lines.append(f"\n💡 建議：{recommendation}")

        return "\n".join(lines)

    def check_and_alert(self) -> bool:
        """
        快速檢查並在必要時發出預警（可在每次掃描後調用）。
        同一種警報在冷卻時間內不重複發送。

        Returns:
            True 表示有新預警被發出
        """
        result = self.analyze()
        alerts = result.get("alerts", [])
        if not alerts or not self.notifier:
            return False

        now = datetime.now()
        cooldown = timedelta(hours=self.ALERT_COOLDOWN_HOURS)

        # 以警報內容為 key，過濾掉冷卻中的警報
        new_alerts = []
        for alert in alerts:
            last_sent = self._last_alert_time.get(alert)
            if last_sent is None or (now - last_sent) >= cooldown:
                new_alerts.append(alert)
                self._last_alert_time[alert] = now

        if new_alerts:
            alert_msg = f"{self.emoji} 風控預警\n" + "\n".join(new_alerts)
            self.send_report(alert_msg)
            return True
        return False
