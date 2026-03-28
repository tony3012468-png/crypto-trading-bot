"""
回測工程師 (Backtest Engineer)

職責：
- 自動拉取歷史 K 線數據並執行回測（無需手動操作）
- 分析不同時間段的績效穩定性
- 生成完整績效報告（勝率、獲利因子、最大回撤）
- 識別策略在哪種市場條件下表現最佳/最差
- 每日自動將回測結果同步給量化研究員
"""

import logging
import pandas as pd
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class BacktestEngineer(BaseAgent):
    """回測工程師 - 自動執行歷史回測與績效分析"""

    name = "回測工程師"
    role = "歷史回測、績效分析、策略驗證、數據提供"
    emoji = "📈"

    # 每次自動回測的交易對（代表性樣本，避免 API 過載）
    DEFAULT_BACKTEST_SYMBOLS = [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "BNB/USDT:USDT",
    ]
    DEFAULT_LOOKBACK_DAYS = 30   # 回測過去 30 天
    DEFAULT_TIMEFRAME = "15m"
    RESEARCH_CAPITAL = 500.0     # 各部門研究模擬固定用 500 USDT

    def __init__(self, config: dict, exchange=None, notifier=None):
        super().__init__(config, exchange, notifier)
        self._backtest_results: dict = {}          # {symbol: BacktestResult}
        self._multi_strategy_results: list = []   # 多策略回測排名結果
        self._last_auto_run: str = ""
        self._auto_run_symbols: list = self.DEFAULT_BACKTEST_SYMBOLS

    def load_results(self, results: dict):
        """
        載入外部回測結果（由 run_backtest.py 提供）。

        Args:
            results: {symbol: BacktestResult}
        """
        self._backtest_results = results
        logger.info(f"[回測工程師] 載入 {len(results)} 個外部回測結果")

    def run_auto_backtest(self) -> dict:
        """
        自動執行回測（單策略）：拉取歷史數據 → 跑當前策略 → 回傳結果。
        Returns: {symbol: BacktestResult}
        """
        if self.exchange is None:
            logger.warning("[回測工程師] 未連接交易所，無法執行自動回測")
            return {}

        from backtest.backtester import Backtester
        from strategies.trend_strategy import TrendStrategy

        research_config = dict(self.config)
        research_config["account"] = dict(self.config.get("account", {}))
        research_config["account"]["total_capital"] = self.RESEARCH_CAPITAL
        backtester = Backtester(research_config)
        strategy = TrendStrategy(self.config)
        results = {}
        symbols = self._auto_run_symbols or self.DEFAULT_BACKTEST_SYMBOLS

        logger.info(f"[回測工程師] 開始自動回測 {len(symbols)} 個交易對...")
        ohlcv_cache = self._fetch_ohlcv_cache(symbols)

        for symbol in symbols:
            try:
                df, df_htf = ohlcv_cache.get(symbol, (None, None))
                if df is None or len(df) < 100:
                    continue
                result = backtester.run(strategy=strategy, df=df, symbol=symbol,
                                        timeframe=self.DEFAULT_TIMEFRAME, df_htf=df_htf)
                results[symbol] = result
                logger.info(f"[回測工程師] {symbol} 勝率:{result.win_rate:.1f}% PF:{result.profit_factor:.2f}")
            except Exception as e:
                logger.error(f"[回測工程師] {symbol} 回測失敗: {e}")

        self._backtest_results = results
        self._last_auto_run = self._now_str()
        return results

    def run_multi_strategy_backtest(self, strategy_candidates: list[dict]) -> dict:
        """
        多策略並行回測 - 策略開發員的核心工作。

        Args:
            strategy_candidates: 策略開發員提供的策略列表
                [{"type": "trend", "id": "...", "params": {...}}, ...]

        Returns:
            {strategy_id: composite_score_dict} 包含複合評分
        """
        if self.exchange is None:
            logger.warning("[回測工程師] 未連接交易所")
            return {}

        from backtest.backtester import Backtester
        from strategies.trend_strategy import TrendStrategy
        from strategies.bollinger_strategy import BollingerStrategy
        from strategies.ema_cross_strategy import EMACrossStrategy
        from strategies.smc_strategy import SMCStrategy

        research_config = dict(self.config)
        research_config["account"] = dict(self.config.get("account", {}))
        research_config["account"]["total_capital"] = self.RESEARCH_CAPITAL
        backtester = Backtester(research_config)
        symbols = self.DEFAULT_BACKTEST_SYMBOLS

        logger.info(f"[回測工程師] 多策略回測：{len(strategy_candidates)} 個策略 × {len(symbols)} 個交易對")

        # 預先拉取所有 K 線（避免重複 API 請求）
        ohlcv_cache = self._fetch_ohlcv_cache(symbols)
        all_scores = {}

        for candidate in strategy_candidates:
            sid = candidate["id"]
            stype = candidate["type"]
            params = candidate.get("params", {})

            try:
                # 建立策略實例
                strategy = self._build_strategy(stype, params)
                if strategy is None:
                    continue

                # 對所有交易對回測，彙整結果
                all_trades = []
                symbol_results = []

                for symbol in symbols:
                    df, df_htf = ohlcv_cache.get(symbol, (None, None))
                    if df is None or len(df) < 100:
                        continue
                    try:
                        result = backtester.run(
                            strategy=strategy, df=df, symbol=symbol,
                            timeframe=self.DEFAULT_TIMEFRAME, df_htf=df_htf
                        )
                        all_trades.extend(result.trades)
                        symbol_results.append(result)
                    except Exception as e:
                        logger.debug(f"[回測工程師] {sid} @ {symbol} 失敗: {e}")

                if len(all_trades) < 3:
                    logger.debug(f"[回測工程師] {sid} 交易筆數不足，跳過評分")
                    continue

                # 計算複合評分
                score = self._compute_composite_score(all_trades, symbol_results)
                score["strategy_id"] = sid
                score["strategy_type"] = stype
                all_scores[sid] = score

                logger.info(
                    f"[回測工程師] {sid} | 複合={score['composite_score']:.3f} | "
                    f"勝率={score['win_rate']:.1f}% | PF={score['profit_factor']:.2f} | "
                    f"夏普={score['sharpe']:.2f} | 索提諾={score['sortino']:.2f}"
                )

            except Exception as e:
                logger.error(f"[回測工程師] {sid} 回測失敗: {e}")

        # 排名
        ranked = sorted(all_scores.values(), key=lambda x: x["composite_score"], reverse=True)
        self._multi_strategy_results = ranked
        self._last_auto_run = self._now_str()

        logger.info(f"[回測工程師] 多策略回測完成，有效結果 {len(all_scores)} 個")
        return all_scores

    def _fetch_ohlcv_cache(self, symbols: list) -> dict:
        """預先拉取所有交易對的 K 線，減少 API 請求次數"""
        cache = {}
        for symbol in symbols:
            try:
                df = self.exchange.fetch_ohlcv(symbol, self.DEFAULT_TIMEFRAME, limit=2880)
                df_htf = self.exchange.fetch_ohlcv(symbol, "1h", limit=720)
                if df is not None and len(df) >= 100:
                    cache[symbol] = (df, df_htf)
            except Exception as e:
                logger.warning(f"[回測工程師] 拉取 {symbol} K 線失敗: {e}")
        return cache

    def _build_strategy(self, stype: str, params: dict):
        """根據類型和參數建立策略實例"""
        from strategies.trend_strategy import TrendStrategy
        from strategies.bollinger_strategy import BollingerStrategy
        from strategies.ema_cross_strategy import EMACrossStrategy
        from strategies.smc_strategy import SMCStrategy

        # 把 params 合併進 config 的對應區段
        merged_config = dict(self.config)
        if stype == "trend":
            merged_config["trend"] = params
            return TrendStrategy(merged_config)
        elif stype == "bollinger":
            return BollingerStrategy(merged_config, params)
        elif stype == "ema_cross":
            return EMACrossStrategy(merged_config, params)
        elif stype == "smc":
            return SMCStrategy(merged_config, params)
        else:
            logger.warning(f"[回測工程師] 未知策略類型: {stype}")
            return None

    def _compute_composite_score(self, all_trades: list, symbol_results: list) -> dict:
        """
        計算複合評分（0~1）
        權重：夏普 30% + 索提諾 25% + 獲利因子 25% + 最大回撤 20%
        """
        import math

        wins = [t for t in all_trades if getattr(t, "pnl", 0) > 0]
        losses = [t for t in all_trades if getattr(t, "pnl", 0) <= 0]
        total = len(all_trades)
        win_rate = len(wins) / total * 100 if total > 0 else 0

        total_wins = sum(getattr(t, "pnl", 0) for t in wins)
        total_losses = abs(sum(getattr(t, "pnl", 0) for t in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # 夏普比率（用每筆 pnl 序列估算）
        pnls = [getattr(t, "pnl", 0) for t in all_trades]
        avg_pnl = sum(pnls) / len(pnls) if pnls else 0
        std_pnl = (sum((x - avg_pnl) ** 2 for x in pnls) / len(pnls)) ** 0.5 if len(pnls) > 1 else 1e-10
        sharpe = avg_pnl / std_pnl if std_pnl > 0 else 0

        # 索提諾比率（只懲罰下行波動）
        downside = [min(x - 0, 0) for x in pnls]
        downside_std = (sum(x ** 2 for x in downside) / len(downside)) ** 0.5 if downside else 1e-10
        sortino = avg_pnl / downside_std if downside_std > 0 else 0

        # 最大回撤（取各 symbol 結果的最大值）
        max_dd = max((getattr(r, "max_drawdown_pct", 0) for r in symbol_results), default=0)

        # 正規化各指標到 0~1，然後加權
        def normalize(val, min_val, max_val):
            if max_val == min_val:
                return 0.5
            return max(0.0, min(1.0, (val - min_val) / (max_val - min_val)))

        sharpe_n = normalize(sharpe, -2, 4)
        sortino_n = normalize(sortino, -2, 6)
        pf_n = normalize(profit_factor, 0, 3)
        dd_n = normalize(100 - max_dd, 0, 100)  # 回撤越小越好

        composite = (
            sharpe_n * 0.30 +
            sortino_n * 0.25 +
            pf_n * 0.25 +
            dd_n * 0.20
        )

        return {
            "composite_score": round(composite, 4),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 3),
            "sharpe": round(sharpe, 3),
            "sortino": round(sortino, 3),
            "max_drawdown": round(max_dd, 2),
            "total_trades": total,
            "total_pnl": round(sum(pnls), 2),
        }

    def get_performance_summary(self) -> dict:
        """
        提取績效摘要，供量化研究員和績效追蹤員使用。

        Returns:
            整體績效摘要字典
        """
        if not self._backtest_results:
            return {}

        all_trades = []
        for result in self._backtest_results.values():
            all_trades.extend(getattr(result, "trades", []))

        if not all_trades:
            return {}

        wins = [t for t in all_trades if getattr(t, "pnl", 0) > 0]
        losses = [t for t in all_trades if getattr(t, "pnl", 0) <= 0]
        total = len(all_trades)
        total_wins_val = sum(getattr(t, "pnl", 0) for t in wins)
        total_losses_val = abs(sum(getattr(t, "pnl", 0) for t in losses))

        return {
            "win_rate": len(wins) / total * 100 if total > 0 else 0,
            "profit_factor": total_wins_val / total_losses_val if total_losses_val > 0 else 0,
            "avg_win": total_wins_val / len(wins) if wins else 0,
            "avg_loss": -total_losses_val / len(losses) if losses else 0,
            "total_trades": total,
            "total_pnl": sum(getattr(t, "pnl", 0) for t in all_trades),
            "max_drawdown": max(
                (getattr(r, "max_drawdown_pct", 0) for r in self._backtest_results.values()),
                default=0
            ),
        }

    def analyze(self) -> dict:
        """分析回測結果，生成統計摘要"""
        if not self._backtest_results:
            return {
                "status": "尚無回測結果",
                "note": "等待自動回測執行（每天 09:00）或手動執行 python run_backtest.py",
                "last_auto_run": self._last_auto_run or "從未執行",
            }

        all_trades = []
        symbol_summaries = []

        for symbol, result in self._backtest_results.items():
            trades = getattr(result, "trades", [])
            all_trades.extend(trades)

            wins = [t for t in trades if getattr(t, "pnl", 0) > 0]
            losses = [t for t in trades if getattr(t, "pnl", 0) <= 0]
            total = len(trades)
            win_rate = len(wins) / total * 100 if total > 0 else 0
            total_pnl = sum(getattr(t, "pnl", 0) for t in trades)
            wins_val = sum(getattr(t, "pnl", 0) for t in wins)
            losses_val = abs(sum(getattr(t, "pnl", 0) for t in losses))
            pf = wins_val / losses_val if losses_val > 0 else 0

            symbol_summaries.append({
                "symbol": symbol.split("/")[0] if "/" in symbol else symbol,
                "total_trades": total,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "max_drawdown": getattr(result, "max_drawdown_pct", 0),
                "profit_factor": pf,
                "period_days": getattr(result, "period_days", self.DEFAULT_LOOKBACK_DAYS),
            })

        total_all = len(all_trades)
        wins_all = [t for t in all_trades if getattr(t, "pnl", 0) > 0]
        losses_all = [t for t in all_trades if getattr(t, "pnl", 0) <= 0]
        overall_win_rate = len(wins_all) / total_all * 100 if total_all > 0 else 0
        total_pnl_all = sum(getattr(t, "pnl", 0) for t in all_trades)
        wins_val_all = sum(getattr(t, "pnl", 0) for t in wins_all)
        losses_val_all = abs(sum(getattr(t, "pnl", 0) for t in losses_all))
        profit_factor = wins_val_all / losses_val_all if losses_val_all > 0 else float("inf")
        avg_win = wins_val_all / len(wins_all) if wins_all else 0
        avg_loss = losses_val_all / len(losses_all) if losses_all else 0

        symbol_summaries.sort(key=lambda x: x["win_rate"], reverse=True)
        grade = self._grade_performance(overall_win_rate, profit_factor)

        return {
            "status": "完成",
            "last_auto_run": self._last_auto_run or "手動載入",
            "total_symbols": len(self._backtest_results),
            "total_trades": total_all,
            "win_count": len(wins_all),
            "loss_count": len(losses_all),
            "overall_win_rate": overall_win_rate,
            "total_pnl": total_pnl_all,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "grade": grade,
            "by_symbol": symbol_summaries,
            "best_symbol": symbol_summaries[0] if symbol_summaries else None,
            "worst_symbol": symbol_summaries[-1] if symbol_summaries else None,
        }

    def _grade_performance(self, win_rate: float, profit_factor: float) -> str:
        if profit_factor >= 1.8 and win_rate >= 55:
            return "頂級 ⭐⭐⭐"
        if profit_factor >= 1.4 and win_rate >= 45:
            return "良好 ⭐⭐"
        if profit_factor >= 1.1:
            return "尚可 ⭐"
        if profit_factor >= 1.0:
            return "持平 ⚠️"
        return "虧損 ❌"

    def generate_report(self) -> str:
        data = self._last_analysis
        if data.get("status") != "完成":
            return (
                f"{self.emoji} 回測工程師報告 | {self._now_str()}\n"
                "-" * 35 + "\n"
                f"狀態：{data.get('status', '未知')}\n"
                f"說明：{data.get('note', '')}\n"
                f"上次執行：{data.get('last_auto_run', '從未')}"
            )

        best = data.get("best_symbol")
        worst = data.get("worst_symbol")

        lines = [
            f"{self.emoji} 回測工程師報告 | {self._now_str()}",
            f"上次回測：{data.get('last_auto_run', '未知')}",
            "-" * 35,
            f"回測幣種：{data.get('total_symbols', 0)} 個（過去 {self.DEFAULT_LOOKBACK_DAYS} 天）",
            f"總交易數：{data.get('total_trades', 0)} 筆",
            f"整體勝率：{data.get('overall_win_rate', 0):.1f}%",
            f"獲利因子：{data.get('profit_factor', 0):.2f}",
            f"模擬損益：{data.get('total_pnl', 0):+.2f} USDT",
            f"平均獲利：{data.get('avg_win', 0):+.2f} USDT",
            f"平均虧損：{data.get('avg_loss', 0):+.2f} USDT",
            f"績效等級：{data.get('grade', '未知')}",
        ]

        if best:
            lines.append(f"\n🏆 最佳：{best['symbol']} 勝率{best['win_rate']:.0f}% | 損益{best['total_pnl']:+.2f}")
        if worst and worst != best:
            lines.append(f"⚠️ 最差：{worst['symbol']} 勝率{worst['win_rate']:.0f}% | 損益{worst['total_pnl']:+.2f}")

        by_symbol = data.get("by_symbol", [])
        if by_symbol:
            lines.append("\n📋 各幣種回測：")
            for item in by_symbol[:6]:
                lines.append(
                    f"  {item['symbol']:<8} 勝率:{item['win_rate']:.0f}% | "
                    f"PF:{item['profit_factor']:.2f} | {item['total_pnl']:+.2f} USDT"
                )

        # 多策略排名（若有）
        if self._multi_strategy_results:
            lines.append("\n🏆 策略競賽排名 Top 5：")
            for i, s in enumerate(self._multi_strategy_results[:5], 1):
                lines.append(
                    f"  #{i} [{s['strategy_type']}] {s['strategy_id']}\n"
                    f"      複合={s['composite_score']:.3f} | 勝率={s['win_rate']:.1f}% | "
                    f"PF={s['profit_factor']:.2f} | 夏普={s['sharpe']:.2f} | 索提諾={s['sortino']:.2f}"
                )

        return "\n".join(lines)
