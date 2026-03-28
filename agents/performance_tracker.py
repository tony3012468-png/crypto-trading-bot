"""
績效追蹤員 (Performance Tracker)

職責：
- 追蹤公司每週 KPI（距離月目標的進度）
- 每週日向老闆發送週報
- 計算月目標達成率
- 記錄每週的盈虧曲線

公司月目標：200 USDT 利潤
所需啟動資金建議：3,000 USDT（量化研究員評估）
"""

from datetime import datetime, timedelta
from agents.base_agent import BaseAgent


# 公司月度目標
MONTHLY_TARGET_USDT = 200.0


class PerformanceTracker(BaseAgent):
    """績效追蹤員 - 每週向老闆匯報公司 KPI 進度"""

    name = "績效追蹤員"
    role = "KPI 追蹤、週報生成、月目標進度監控"
    emoji = "📅"

    def __init__(self, config: dict, exchange=None, notifier=None):
        super().__init__(config, exchange, notifier)
        self.monthly_target = MONTHLY_TARGET_USDT
        self._weekly_records: list[dict] = []
        self._current_week_start = self._get_week_start()
        self._month_start_balance = config.get("account", {}).get("total_capital", 25.0)

    @staticmethod
    def _get_week_start() -> datetime:
        """取得本週一的日期"""
        today = datetime.now()
        return today - timedelta(days=today.weekday())

    def record_weekly_snapshot(self, balance: float, weekly_pnl: float,
                                trade_count: int, win_rate: float):
        """
        記錄本週快照（每週日由排程器調用）。

        Args:
            balance: 當前帳戶餘額
            weekly_pnl: 本週損益
            trade_count: 本週交易次數
            win_rate: 本週勝率
        """
        week_num = len(self._weekly_records) + 1
        self._weekly_records.append({
            "week": week_num,
            "week_start": self._current_week_start.strftime("%Y-%m-%d"),
            "balance": balance,
            "weekly_pnl": weekly_pnl,
            "trade_count": trade_count,
            "win_rate": win_rate,
            "timestamp": self._now_str(),
        })
        self._current_week_start = self._get_week_start()

    def analyze(self) -> dict:
        """分析當前 KPI 進度"""
        # 計算本月累計損益（從所有週記錄合計）
        month_pnl = sum(w.get("weekly_pnl", 0) for w in self._weekly_records)
        month_progress_pct = (month_pnl / self.monthly_target * 100) if self.monthly_target > 0 else 0

        # 週均損益
        avg_weekly_pnl = month_pnl / len(self._weekly_records) if self._weekly_records else 0

        # 預測月底損益（基於週均）
        weeks_elapsed = len(self._weekly_records)
        remaining_weeks = max(0, 4 - weeks_elapsed)
        projected_month_pnl = month_pnl + avg_weekly_pnl * remaining_weeks

        # 判斷是否在軌
        if weeks_elapsed == 0:
            on_track = "尚無數據"
            track_emoji = "⏳"
        elif projected_month_pnl >= self.monthly_target:
            on_track = "達標預期 ✅"
            track_emoji = "🟢"
        elif projected_month_pnl >= self.monthly_target * 0.7:
            on_track = "接近目標 🟡"
            track_emoji = "🟡"
        else:
            on_track = "落後目標 ⚠️"
            track_emoji = "🔴"

        # 最近一週數據
        latest_week = self._weekly_records[-1] if self._weekly_records else {}

        return {
            "monthly_target": self.monthly_target,
            "month_pnl": month_pnl,
            "month_progress_pct": month_progress_pct,
            "avg_weekly_pnl": avg_weekly_pnl,
            "projected_month_pnl": projected_month_pnl,
            "weeks_elapsed": weeks_elapsed,
            "on_track": on_track,
            "track_emoji": track_emoji,
            "latest_week": latest_week,
            "all_weeks": self._weekly_records,
        }

    def generate_report(self) -> str:
        """生成老闆週報"""
        data = self._last_analysis

        # 本週數據
        latest = data.get("latest_week", {})
        week_num = data.get("weeks_elapsed", 0)

        lines = [
            f"{self.emoji} 老闆週報 | 第 {week_num} 週",
            f"{'═' * 35}",
            f"🎯 月度目標：{self.monthly_target:.0f} USDT 利潤",
            f"",
            f"📊 本月累計：",
            f"  已獲利：{data.get('month_pnl', 0):+.2f} USDT",
            f"  進度：{data.get('month_progress_pct', 0):.1f}%",
            f"  預測月底：{data.get('projected_month_pnl', 0):+.2f} USDT",
            f"  達標狀況：{data.get('track_emoji', '')} {data.get('on_track', '未知')}",
        ]

        if latest:
            lines += [
                "",
                f"📋 本週績效（第 {latest.get('week', '-')} 週）：",
                f"  週損益：{latest.get('weekly_pnl', 0):+.2f} USDT",
                f"  帳戶餘額：{latest.get('balance', 0):.2f} USDT",
                f"  交易筆數：{latest.get('trade_count', 0)} 筆",
                f"  勝率：{latest.get('win_rate', 0):.1f}%",
            ]

        # 歷週趨勢
        all_weeks = data.get("all_weeks", [])
        if len(all_weeks) >= 2:
            lines.append("")
            lines.append("📈 歷週損益趨勢：")
            for w in all_weeks:
                bar = "▓" * max(0, int(w["weekly_pnl"] / 5)) if w["weekly_pnl"] > 0 else "░" * max(0, int(abs(w["weekly_pnl"]) / 5))
                lines.append(f"  第{w['week']}週 {w['weekly_pnl']:+6.1f} USDT {bar}")

        lines += [
            "",
            f"💡 主管建議：",
            self._generate_ceo_advice(data),
        ]

        return "\n".join(lines)

    def _generate_ceo_advice(self, data: dict) -> str:
        """主管給老闆的本週策略建議"""
        on_track = data.get("on_track", "")
        month_pnl = data.get("month_pnl", 0)

        if "達標預期" in on_track:
            return "本月進度良好，維持現有策略，不需要調整"
        if "接近目標" in on_track:
            return "略低於目標，建議量化研究員本週評估是否可微調信號條件"
        if "落後目標" in on_track and month_pnl < 0:
            return "本月目前虧損，已指派風控官進行全面風控複查，量化研究員檢視策略參數"
        if "尚無數據" in on_track:
            return "策略剛啟動，本週重點是驗證信號品質，蒐集基礎績效數據"
        return "持續監控各部門指標，下週再評估"

    def send_weekly_report(self) -> bool:
        """發送週報給老闆（由排程器調用）"""
        self._last_analysis = self.analyze()
        report = self.generate_report()
        return self.send_report(report)
