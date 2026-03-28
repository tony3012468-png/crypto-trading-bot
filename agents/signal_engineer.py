"""
信號工程師 (Signal Engineer)

職責：
- 追蹤和分析交易信號的品質與頻率
- 統計各類信號（MACD 金叉/死叉、RSI 過界等）的成功率
- 識別信號失效的市場條件
- 優化信號過濾條件
"""

from collections import defaultdict
from agents.base_agent import BaseAgent


class SignalEngineer(BaseAgent):
    """信號工程師 - 負責技術指標監控與信號品質分析"""

    name = "信號工程師"
    role = "技術指標分析、信號品質評估、信號統計"
    emoji = "📡"

    def __init__(self, config: dict, exchange=None, notifier=None):
        super().__init__(config, exchange, notifier)
        # 信號歷史記錄
        self._signal_history: list[dict] = []
        # 各交易對的最新指標快照
        self._indicator_snapshots: dict[str, dict] = {}

    def record_signal(self, symbol: str, signal: dict, result: str = "pending"):
        """
        記錄一筆信號（由主程式調用）。

        Args:
            symbol: 交易對
            signal: 信號字典 {"side", "entry", "stop_loss", "take_profit", "reason"}
            result: "win" / "loss" / "pending"
        """
        self._signal_history.append({
            "symbol": symbol,
            "time": self._now_str(),
            "side": signal.get("side"),
            "entry": signal.get("entry"),
            "stop_loss": signal.get("stop_loss"),
            "take_profit": signal.get("take_profit"),
            "reason": signal.get("reason", ""),
            "result": result,
        })

    def update_signal_result(self, symbol: str, entry_price: float, result: str):
        """
        更新信號結果（停損/停利後調用）。

        Args:
            symbol: 交易對
            entry_price: 入場價（用於匹配信號）
            result: "win" 或 "loss"
        """
        for sig in reversed(self._signal_history):
            if sig["symbol"] == symbol and sig["entry"] == entry_price and sig["result"] == "pending":
                sig["result"] = result
                break

    def update_indicator_snapshot(self, symbol: str, indicators: dict):
        """
        更新交易對的最新指標快照（由主程式在每次掃描後調用）。

        Args:
            symbol: 交易對
            indicators: {"rsi", "macd", "macd_signal", "atr", "volume_ratio"}
        """
        self._indicator_snapshots[symbol] = indicators

    def analyze(self) -> dict:
        """分析信號統計與當前指標狀態"""
        total = len(self._signal_history)
        if total == 0:
            return {
                "total_signals": 0,
                "win_rate": 0,
                "long_count": 0,
                "short_count": 0,
                "by_symbol": {},
                "indicator_snapshots": self._indicator_snapshots,
                "note": "尚無信號記錄"
            }

        wins = sum(1 for s in self._signal_history if s["result"] == "win")
        losses = sum(1 for s in self._signal_history if s["result"] == "loss")
        pending = sum(1 for s in self._signal_history if s["result"] == "pending")
        resolved = wins + losses

        win_rate = (wins / resolved * 100) if resolved > 0 else 0

        long_signals = [s for s in self._signal_history if s.get("side") == "LONG"]
        short_signals = [s for s in self._signal_history if s.get("side") == "SHORT"]

        # 按交易對統計
        by_symbol = defaultdict(lambda: {"count": 0, "wins": 0, "losses": 0})
        for sig in self._signal_history:
            sym = sig["symbol"].split("/")[0] if "/" in sig["symbol"] else sig["symbol"]
            by_symbol[sym]["count"] += 1
            if sig["result"] == "win":
                by_symbol[sym]["wins"] += 1
            elif sig["result"] == "loss":
                by_symbol[sym]["losses"] += 1

        # 評估信號品質
        quality = self._evaluate_signal_quality(win_rate, total, resolved)

        return {
            "total_signals": total,
            "resolved_signals": resolved,
            "pending_signals": pending,
            "win_count": wins,
            "loss_count": losses,
            "win_rate": win_rate,
            "long_count": len(long_signals),
            "short_count": len(short_signals),
            "by_symbol": dict(by_symbol),
            "signal_quality": quality,
            "indicator_snapshots": self._indicator_snapshots,
        }

    def _evaluate_signal_quality(self, win_rate: float, total: int, resolved: int) -> str:
        """評估信號品質等級"""
        if resolved < 5:
            return "樣本不足（需至少 5 筆已完成交易）"
        if win_rate >= 60:
            return "優秀 ✅"
        if win_rate >= 45:
            return "良好 🟡"
        if win_rate >= 35:
            return "偏弱 🟠"
        return "不佳，建議檢查策略參數 🔴"

    def generate_report(self) -> str:
        """生成信號工程師報告"""
        data = self._last_analysis

        lines = [
            f"{self.emoji} 信號工程師報告 | {self._now_str()}",
            -" * 35,
            f"總信號數：{data.get('total_signals', 0)} 筆",
            f"已完成：{data.get('resolved_signals', 0)} 筆 | 持倉中：{data.get('pending_signals', 0)} 筆",
            f"多單信號：{data.get('long_count', 0)} 筆 | 空單信號：{data.get('short_count', 0)} 筆",
            f"勝率：{data.get('win_rate', 0):.1f}%",
            f"信號品質：{data.get('signal_quality', '未知')}",
        ]

        by_symbol = data.get("by_symbol", {})
        if by_symbol:
            lines.append("")
            lines.append("📋 各幣種信號統計：")
            for sym, stats in sorted(by_symbol.items(),
                                     key=lambda x: x[1]["count"], reverse=True)[:8]:
                resolved = stats["wins"] + stats["losses"]
                wr = f"{stats['wins']/resolved*100:.0f}%" if resolved > 0 else "N/A"
                lines.append(f"  {sym:<10} 共{stats['count']}筆 | 勝率:{wr}")

        snapshots = data.get("indicator_snapshots", {})
        if snapshots:
            lines.append("")
            lines.append("📈 最新技術指標快照：")
            for sym, ind in list(snapshots.items())[:5]:
                short = sym.split("/")[0] if "/" in sym else sym
                rsi = ind.get("rsi", 0)
                rsi_label = "超買" if rsi > 70 else ("超賣" if rsi < 30 else "正常")
                lines.append(f"  {short:<10} RSI:{rsi:.1f}({rsi_label})")

        return "\n".join(lines)
