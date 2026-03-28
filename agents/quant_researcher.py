"""
量化研究員 (Quant Researcher)

職責：
- 分析現有策略的 alpha 因子有效性
- 評估策略參數是否仍然有效（EMA、RSI、ATR 週期等）
- 比較不同市場條件下的策略表現
- 提出策略優化方向
"""

from agents.base_agent import BaseAgent


class QuantResearcher(BaseAgent):
    """量化研究員 - 負責策略研究與 Alpha 發現"""

    name = "量化研究員"
    role = "策略研究、Alpha 因子分析、參數優化建議"
    emoji = "🔬"

    def __init__(self, config: dict, exchange=None, notifier=None):
        super().__init__(config, exchange, notifier)
        # 從外部注入的績效數據
        self._performance_data: dict = {}
        self._backtest_results: list[dict] = []

    def update_performance(self, performance: dict):
        """
        更新策略績效數據（由主程式或回測工程師傳入）。

        Args:
            performance: {
                "win_rate": float,
                "profit_factor": float,
                "avg_win": float,
                "avg_loss": float,
                "total_trades": int,
                "total_pnl": float,
                "max_drawdown": float,
            }
        """
        self._performance_data = performance

    def add_backtest_result(self, result: dict):
        """新增一筆回測結果供分析"""
        self._backtest_results.append(result)

    def analyze(self) -> dict:
        """分析策略 Alpha 有效性與參數狀況"""
        config_analysis = self._analyze_config_params()
        performance_analysis = self._analyze_performance()
        alpha_assessment = self._assess_alpha()
        optimization_hints = self._generate_optimization_hints(
            performance_analysis, config_analysis
        )

        return {
            "config_params": config_analysis,
            "performance": performance_analysis,
            "alpha_assessment": alpha_assessment,
            "optimization_hints": optimization_hints,
        }

    def _analyze_config_params(self) -> dict:
        """分析當前策略配置參數"""
        trend_cfg = self.config.get("trend", {})
        risk_cfg = self.config.get("risk", {})
        account_cfg = self.config.get("account", {})

        return {
            "fast_ema": trend_cfg.get("fast_ema", 12),
            "slow_ema": trend_cfg.get("slow_ema", 26),
            "signal_ema": trend_cfg.get("signal_ema", 9),
            "rsi_period": trend_cfg.get("rsi_period", 14),
            "rsi_overbought": trend_cfg.get("rsi_overbought", 65),
            "rsi_oversold": trend_cfg.get("rsi_oversold", 35),
            "atr_sl_mult": trend_cfg.get("atr_sl_multiplier", 1.8),
            "atr_tp_mult": trend_cfg.get("atr_tp_multiplier", 2.5),
            "risk_per_trade": risk_cfg.get("risk_per_trade", 0.02),
            "leverage": account_cfg.get("leverage", 3),
            "rr_ratio": trend_cfg.get("atr_tp_multiplier", 2.5) / trend_cfg.get("atr_sl_multiplier", 1.8),
        }

    def _analyze_performance(self) -> dict:
        """分析傳入的績效數據"""
        if not self._performance_data:
            return {"status": "尚無績效數據"}

        perf = self._performance_data
        win_rate = perf.get("win_rate", 0)
        profit_factor = perf.get("profit_factor", 0)
        avg_win = perf.get("avg_win", 0)
        avg_loss = perf.get("avg_loss", 0)

        # 交易數不足時不評估
        total_trades = perf.get("total_trades", 0)
        if total_trades < 5:
            return {"status": f"數據不足（{total_trades} 筆），需至少 5 筆交易"}

        # 評估績效等級
        if profit_factor >= 1.5 and win_rate >= 50:
            grade = "優秀 ✅"
        elif profit_factor >= 1.2 and win_rate >= 40:
            grade = "良好 🟡"
        elif profit_factor >= 1.0:
            grade = "持平 🟠"
        else:
            grade = "虧損策略 🔴"

        return {
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "total_trades": perf.get("total_trades", 0),
            "total_pnl": perf.get("total_pnl", 0),
            "max_drawdown": perf.get("max_drawdown", 0),
            "grade": grade,
        }

    def _assess_alpha(self) -> str:
        """評估當前策略的 Alpha 來源"""
        params = self._analyze_config_params()
        rr = params.get("rr_ratio", 0)
        sources = []

        sources.append("MACD 動量（快慢線交叉識別趨勢方向）")
        sources.append("RSI 動量過濾（避免追高殺低）")
        sources.append("EMA 趨勢確認（價格在均線上方做多）")
        sources.append("ATR 動態止損（適應市場波動度）")
        sources.append("多時間框架確認（15m 信號 + 1H 趨勢）")

        if rr >= 1.5:
            sources.append(f"正向風險報酬比（{rr:.2f}x，有統計優勢）")

        return " | ".join(sources)

    def _generate_optimization_hints(self, perf: dict, params: dict) -> list[str]:
        """根據績效生成優化建議"""
        hints = []

        if "status" in perf:
            hints.append("建議累積至少 20 筆交易後再評估策略效果")
            return hints

        win_rate = perf.get("win_rate", 0)
        profit_factor = perf.get("profit_factor", 1)
        rr = params.get("rr_ratio", 1.4)

        if win_rate < 40:
            hints.append("勝率偏低：考慮加嚴入場條件（RSI 縮小至 30-60）或加入成交量確認")
        if profit_factor < 1.0:
            hints.append("獲利因子低於 1：策略目前虧損，建議暫停並回測調整參數")
        if rr < 1.5:
            hints.append(f"風險報酬比 {rr:.2f}x 偏低：建議將 ATR 停利倍數提升至 3.0")
        if win_rate >= 55 and profit_factor >= 1.5:
            hints.append("策略表現良好，可考慮適度提升每筆風險至 2.5%（謹慎評估後）")
        if not hints:
            hints.append("當前策略參數運作正常，維持現有配置")

        return hints

    def generate_report(self) -> str:
        """生成量化研究員報告"""
        data = self._last_analysis

        params = data.get("config_params", {})
        perf = data.get("performance", {})
        alpha = data.get("alpha_assessment", "")
        hints = data.get("optimization_hints", [])

        lines = [
            f"{self.emoji} 量化研究員報告 | {self._now_str()}",
            "-" * 35,
            "📐 當前策略參數：",
            f"  MACD：快線 {params.get('fast_ema',12)} / 慢線 {params.get('slow_ema',26)} / 訊號線 {params.get('signal_ema',9)}",
            f"  RSI：週期 {params.get('rsi_period',14)} | 區間 {params.get('rsi_oversold',35)}-{params.get('rsi_overbought',65)}",
            f"  ATR：止損 {params.get('atr_sl_mult',1.8)}x | 止盈 {params.get('atr_tp_mult',2.5)}x | 風報比 {params.get('rr_ratio',1.4):.2f}x",
            f"  槓桿：{params.get('leverage',3)}x | 每筆風險：{params.get('risk_per_trade',0.02)*100:.0f}%",
        ]

        if "grade" in perf:
            lines += [
                "",
                "📊 策略績效評估：",
                f"  等級：{perf.get('grade', '未知')}",
                f"  勝率：{perf.get('win_rate', 0):.1f}%",
                f"  獲利因子：{perf.get('profit_factor', 0):.2f}",
                f"  平均獲利：{perf.get('avg_win', 0):+.2f} USDT",
                f"  平均虧損：{perf.get('avg_loss', 0):+.2f} USDT",
            ]
        else:
            lines.append("\n📊 策略績效：尚無足夠數據")

        lines += [
            "",
            "🔑 Alpha 來源：",
            f"  {alpha}",
            "",
            "💡 優化建議：",
        ]
        for h in hints:
            lines.append(f"  • {h}")

        return "\n".join(lines)
