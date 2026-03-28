"""
執行工程師 (Execution Engineer)

職責：
- 監控 API 訂單執行品質（滑點、填成速度）
- 追蹤每筆訂單的實際 vs. 預期入場價
- 統計訂單失敗率與錯誤類型
- 確保合約設置正確（槓桿、保證金模式）
"""

from agents.base_agent import BaseAgent


class ExecutionEngineer(BaseAgent):
    """執行工程師 - 負責 API 執行品質與訂單管理監控"""

    name = "執行工程師"
    role = "API 執行監控、滑點分析、訂單品質追蹤"
    emoji = "⚙️"

    def __init__(self, config: dict, exchange=None, notifier=None):
        super().__init__(config, exchange, notifier)
        self._execution_records: list[dict] = []
        self._api_errors: list[dict] = []
        self._leverage_verified: dict[str, bool] = {}

    def record_execution(self, symbol: str, expected_price: float,
                          actual_price: float, side: str, success: bool = True):
        """
        記錄一筆訂單執行結果（由主程式的下單後調用）。

        Args:
            symbol: 交易對
            expected_price: 信號觸發時的預期入場價
            actual_price: 實際成交價格
            side: "LONG" / "SHORT"
            success: 是否成功成交
        """
        slippage = actual_price - expected_price
        slippage_pct = abs(slippage / expected_price * 100) if expected_price > 0 else 0

        self._execution_records.append({
            "symbol": symbol,
            "time": self._now_str(),
            "side": side,
            "expected": expected_price,
            "actual": actual_price,
            "slippage": slippage,
            "slippage_pct": slippage_pct,
            "success": success,
        })

    def record_api_error(self, symbol: str, error_type: str, message: str):
        """記錄 API 錯誤（由主程式 except 區塊調用）"""
        self._api_errors.append({
            "time": self._now_str(),
            "symbol": symbol,
            "error_type": error_type,
            "message": message,
        })

    def mark_leverage_verified(self, symbol: str):
        """標記某交易對的槓桿已驗證設置正確"""
        self._leverage_verified[symbol] = True

    def analyze(self) -> dict:
        """分析執行品質"""
        total_orders = len(self._execution_records)
        successful = [r for r in self._execution_records if r["success"]]
        failed = [r for r in self._execution_records if not r["success"]]

        if total_orders == 0:
            return {
                "total_orders": 0,
                "success_rate": 100.0,
                "avg_slippage_pct": 0,
                "api_errors": len(self._api_errors),
                "leverage_verified_count": len(self._leverage_verified),
                "note": "尚無執行記錄",
            }

        success_rate = len(successful) / total_orders * 100
        avg_slippage = (
            sum(r["slippage_pct"] for r in successful) / len(successful)
            if successful else 0
        )
        max_slippage = max((r["slippage_pct"] for r in successful), default=0)

        # 評估執行品質
        quality = self._evaluate_execution_quality(success_rate, avg_slippage)

        # 統計錯誤類型
        error_types = {}
        for err in self._api_errors:
            t = err.get("error_type", "未知")
            error_types[t] = error_types.get(t, 0) + 1

        return {
            "total_orders": total_orders,
            "successful_orders": len(successful),
            "failed_orders": len(failed),
            "success_rate": success_rate,
            "avg_slippage_pct": avg_slippage,
            "max_slippage_pct": max_slippage,
            "execution_quality": quality,
            "api_errors": len(self._api_errors),
            "error_types": error_types,
            "leverage_verified_count": len(self._leverage_verified),
            "config_leverage": self.config.get("account", {}).get("leverage", 3),
            "config_margin_type": self.config.get("account", {}).get("margin_type", "isolated"),
        }

    def _evaluate_execution_quality(self, success_rate: float, avg_slippage: float) -> str:
        """評估執行品質等級"""
        if success_rate >= 99 and avg_slippage < 0.05:
            return "優秀 ✅"
        if success_rate >= 95 and avg_slippage < 0.15:
            return "良好 🟡"
        if success_rate >= 90:
            return "尚可 🟠"
        return "需改善 🔴"

    def generate_report(self) -> str:
        """生成執行工程師報告"""
        data = self._last_analysis

        leverage = data.get("config_leverage", 3)
        margin_type = data.get("config_margin_type", "isolated")

        lines = [
            f"{self.emoji} 執行工程師報告 | {self._now_str()}",
            -" * 35,
            f"總訂單數：{data.get('total_orders', 0)} 筆",
            f"成功率：{data.get('success_rate', 100):.1f}%",
            f"失敗訂單：{data.get('failed_orders', 0)} 筆",
            f"",
            f"📉 滑點分析：",
            f"  平均滑點：{data.get('avg_slippage_pct', 0):.3f}%",
            f"  最大滑點：{data.get('max_slippage_pct', 0):.3f}%",
            f"  執行品質：{data.get('execution_quality', '未知')}",
            f"",
            f"⚙️ 合約設置：",
            f"  槓桿：{leverage}x | 保證金模式：{margin_type}",
            f"  已驗證交易對：{data.get('leverage_verified_count', 0)} 個",
        ]

        error_types = data.get("error_types", {})
        if error_types:
            lines.append(f"\n❌ API 錯誤統計（共 {data.get('api_errors', 0)} 次）：")
            for err_type, count in error_types.items():
                lines.append(f"  {err_type}: {count} 次")
        elif data.get("api_errors", 0) == 0:
            lines.append("\n✅ 無 API 錯誤記錄")

        if data.get("note"):
            lines.append(f"\n💡 {data['note']}")

        return "\n".join(lines)
