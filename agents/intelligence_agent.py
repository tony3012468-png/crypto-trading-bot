"""
情報員 (Intelligence Agent)

職責：
- 監控市場重大事件（FED 利率決議、重大清算、BTC 巨鯨動向）
- 偵測異常波動（短時間大幅漲跌）
- 在高風險事件前主動預警
- 提供每日市場簡報

注意：目前使用 Binance 公開 API 數據，不依賴付費新聞 API。
未來可擴充接入 CoinGecko、Glassnode 等數據源。
"""

import time
import logging
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# 高風險波動門檻（1 小時內漲跌超過此值）
HIGH_VOLATILITY_THRESHOLD_PCT = 5.0
# 極端波動（立即預警）
EXTREME_VOLATILITY_PCT = 10.0


class IntelligenceAgent(BaseAgent):
    """情報員 - 負責市場異常偵測與事件預警"""

    name = "情報員"
    role = "市場事件監控、異常波動預警、每日市場簡報"
    emoji = "🕵️"

    def __init__(self, config: dict, exchange=None, notifier=None):
        super().__init__(config, exchange, notifier)
        self._alert_history: list[dict] = []
        self._market_snapshot: dict = {}
        self._last_prices: dict[str, float] = {}
        self._fear_greed: str = "未知"  # 未來可接入 Fear & Greed API

    def scan_volatility(self, tickers: dict) -> list[dict]:
        """
        掃描所有交易對，找出異常波動。

        Args:
            tickers: ccxt fetch_tickers() 返回的結果

        Returns:
            異常警報列表
        """
        alerts = []
        for symbol, ticker in tickers.items():
            if not symbol.endswith(":USDT"):
                continue

            change_pct = abs(ticker.get("percentage", 0) or 0)
            price = ticker.get("last", 0) or 0

            if change_pct >= EXTREME_VOLATILITY_PCT:
                direction = "🚀 急漲" if (ticker.get("percentage", 0) or 0) > 0 else "💥 急跌"
                alerts.append({
                    "level": "extreme",
                    "symbol": symbol,
                    "change_pct": change_pct,
                    "direction": direction,
                    "price": price,
                    "message": f"{direction} {symbol.split('/')[0]} 24h漲跌 {ticker.get('percentage',0):+.1f}%",
                })
            elif change_pct >= HIGH_VOLATILITY_THRESHOLD_PCT:
                direction = "📈 上漲" if (ticker.get("percentage", 0) or 0) > 0 else "📉 下跌"
                alerts.append({
                    "level": "high",
                    "symbol": symbol,
                    "change_pct": change_pct,
                    "direction": direction,
                    "price": price,
                    "message": f"{direction} {symbol.split('/')[0]} 24h漲跌 {ticker.get('percentage',0):+.1f}%",
                })

        # 按漲跌幅排序（最大的在前）
        alerts.sort(key=lambda x: x["change_pct"], reverse=True)
        self._alert_history.extend(alerts[:5])  # 只保留最顯著的
        return alerts

    def update_snapshot(self, tickers: dict):
        """更新市場快照（每次掃描後調用）"""
        btc = tickers.get("BTC/USDT:USDT", {})
        eth = tickers.get("ETH/USDT:USDT", {})

        self._market_snapshot = {
            "btc_price": btc.get("last", 0),
            "btc_change": btc.get("percentage", 0),
            "eth_price": eth.get("last", 0),
            "eth_change": eth.get("percentage", 0),
            "timestamp": self._now_str(),
        }

    def analyze(self) -> dict:
        """分析當前情報狀況"""
        extreme_alerts = [a for a in self._alert_history if a["level"] == "extreme"]
        high_alerts = [a for a in self._alert_history if a["level"] == "high"]

        # 市場整體情緒評估（基於 BTC 走勢）
        btc_change = self._market_snapshot.get("btc_change", 0) or 0
        if btc_change > 3:
            market_mood = "🟢 看漲"
        elif btc_change < -3:
            market_mood = "🔴 看跌"
        else:
            market_mood = "🟡 中性"

        # 建議的交易警戒等級
        if extreme_alerts:
            alert_level = "極高 ⛔"
            trading_advice = "市場出現極端波動，建議暫停新開單，等待市場穩定"
        elif len(high_alerts) >= 3:
            alert_level = "高 🔴"
            trading_advice = "多個幣種出現高波動，降低倉位並嚴格遵守止損"
        else:
            alert_level = "正常 🟢"
            trading_advice = "市場情緒正常，按策略正常執行"

        return {
            "market_snapshot": self._market_snapshot,
            "market_mood": market_mood,
            "alert_level": alert_level,
            "trading_advice": trading_advice,
            "recent_extreme_alerts": extreme_alerts[:3],
            "recent_high_alerts": high_alerts[:3],
            "total_alerts_today": len(self._alert_history),
        }

    def generate_report(self) -> str:
        """生成情報員每日簡報"""
        data = self._last_analysis
        snapshot = data.get("market_snapshot", {})

        lines = [
            f"{self.emoji} 情報員日報 | {self._now_str()}",
            -" * 35,
            f"市場情緒：{data.get('market_mood', '未知')}",
            f"警戒等級：{data.get('alert_level', '未知')}",
            "",
            "📊 市場快照：",
        ]

        if snapshot.get("btc_price"):
            lines.append(f"  BTC: ${snapshot['btc_price']:,.0f} ({snapshot['btc_change']:+.1f}%)")
        if snapshot.get("eth_price"):
            lines.append(f"  ETH: ${snapshot['eth_price']:,.0f} ({snapshot['eth_change']:+.1f}%)")

        extreme = data.get("recent_extreme_alerts", [])
        if extreme:
            lines.append("\n🚨 極端異動：")
            for a in extreme:
                lines.append(f"  {a['message']}")

        high = data.get("recent_high_alerts", [])
        if high:
            lines.append("\n⚠️ 高波動警報：")
            for a in high[:3]:
                lines.append(f"  {a['message']}")

        lines.append(f"\n💡 交易建議：{data.get('trading_advice', '')}")

        return "\n".join(lines)

    def send_extreme_alert(self, alerts: list[dict]) -> bool:
        """立即發送極端異動預警到 Telegram"""
        if not alerts or not self.notifier:
            return False

        msg_lines = [f"{self.emoji} 極端市場異動預警！", -" * 30]
        for a in alerts[:5]:
            msg_lines.append(a["message"])
        msg_lines.append("\n⚠️ 建議立即檢查持倉並考慮暫停開新單")

        try:
            self.notifier.send_message("\n".join(msg_lines))
            return True
        except Exception as e:
            logger.error(f"發送異動預警失敗: {e}")
            return False

    def clear_daily_alerts(self):
        """每日重置（由排程器調用）"""
        self._alert_history.clear()
        logger.info("[情報員] 每日警報已重置")
