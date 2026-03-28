"""
市場分析師 (Market Analyst)

職責：
- 分析當前市場整體趨勢（牛市 / 熊市 / 震盪）
- 評估各交易對的市場狀態
- 提供選幣建議（哪些幣種適合現在的策略）
- 檢測異常波動或特殊市場行情
"""

import pandas as pd
import ta
from agents.base_agent import BaseAgent


class MarketAnalyst(BaseAgent):
    """市場分析師 - 負責即時行情與市場狀態分析"""

    name = "市場分析師"
    role = "即時行情、市場狀態判斷、選幣建議"
    emoji = "📊"

    def __init__(self, config: dict, exchange=None, notifier=None):
        super().__init__(config, exchange, notifier)
        self._market_states: dict[str, str] = {}
        self._pair_scores: dict[str, float] = {}

    def update_market_states(self, market_states: dict[str, str]):
        """由主程式更新當前市場狀態"""
        self._market_states = market_states

    def analyze(self) -> dict:
        """分析市場整體狀況"""
        if not self._market_states:
            return {"error": "尚無市場狀態資料，請先更新 market_states"}

        total = len(self._market_states)
        trending = sum(1 for s in self._market_states.values() if "trend" in s)
        ranging = total - trending
        trend_ratio = trending / total if total > 0 else 0

        # 判斷整體市場環境
        if trend_ratio >= 0.7:
            market_env = "趨勢市場"
            env_desc = "大多數幣種呈現趨勢行情，趨勢策略效果佳"
        elif trend_ratio <= 0.3:
            market_env = "震盪市場"
            env_desc = "大多數幣種橫盤震盪，注意假突破風險"
        else:
            market_env = "混合市場"
            env_desc = "市場分歧，謹慎選擇交易對，優先選趨勢明確的幣種"

        # 分析各幣種的適合度
        pair_analysis = self._analyze_pairs()

        return {
            "total_pairs": total,
            "trending_count": trending,
            "ranging_count": ranging,
            "trend_ratio": trend_ratio,
            "market_environment": market_env,
            "env_description": env_desc,
            "pair_analysis": pair_analysis,
            "market_states": self._market_states,
        }

    def _analyze_pairs(self) -> list[dict]:
        """分析各交易對的當前適合度"""
        results = []
        for symbol, state in self._market_states.items():
            short_name = symbol.split("/")[0] if "/" in symbol else symbol
            if "trend" in state:
                suitability = "✅ 適合交易"
                priority = 1
            else:
                suitability = "⚠️ 謹慎"
                priority = 2

            results.append({
                "symbol": short_name,
                "state": state,
                "suitability": suitability,
                "priority": priority,
            })

        results.sort(key=lambda x: x["priority"])
        return results

    def generate_report(self) -> str:
        """生成市場分析報告"""
        data = self._last_analysis
        if "error" in data:
            return f"{self.emoji} 市場分析師報告\n❌ {data['error']}"

        lines = [
            f"{self.emoji} 市場分析師報告 | {self._now_str()}",
            -" * 35,
            f"監控交易對：{data['total_pairs']} 個",
            f"趨勢行情：{data['trending_count']} 個 ({data['trend_ratio']*100:.0f}%)",
            f"震盪行情：{data['ranging_count']} 個",
            f"",
            f"📈 市場環境：{data['market_environment']}",
            f"說明：{data['env_description']}",
            f"",
            "📋 交易對狀態：",
        ]

        for pair in data.get("pair_analysis", []):
            lines.append(f"  {pair['symbol']:<10} {pair['suitability']}")

        return "\n".join(lines)

    def get_recommended_pairs(self) -> list[str]:
        """
        返回當前最建議交易的幣種列表。

        Returns:
            適合交易的交易對列表（完整格式）
        """
        result = self._last_analysis
        if not result or "pair_analysis" not in result:
            result = self.analyze()

        recommended = []
        for item in result.get("pair_analysis", []):
            if item["priority"] == 1:
                # 找回完整的 symbol
                for full_sym, state in self._market_states.items():
                    if full_sym.startswith(item["symbol"] + "/"):
                        recommended.append(full_sym)
                        break
        return recommended
