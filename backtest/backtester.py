"""
回測引擎 - 用歷史數據驗證策略表現
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """回測交易記錄"""
    trade_id: int
    symbol: str
    side: str               # LONG / SHORT
    entry_price: float
    entry_time: pd.Timestamp
    stop_loss: float
    take_profit: float
    amount: float
    exit_price: Optional[float] = None
    exit_time: Optional[pd.Timestamp] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    reason: str = ""
    exit_reason: str = ""


@dataclass
class BacktestResult:
    """回測結果摘要"""
    strategy_name: str
    symbol: str
    timeframe: str
    period_days: int
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    trades: list = field(default_factory=list)

    def summary(self) -> str:
        """輸出結果摘要"""
        return (
            f"\n{'='*60}\n"
            f"回測結果: {self.strategy_name} | {self.symbol} | {self.timeframe}\n"
            f"{'='*60}\n"
            f"測試期間:     {self.period_days} 天\n"
            f"總交易數:     {self.total_trades}\n"
            f"勝率:         {self.win_rate:.1f}%\n"
            f"獲利交易:     {self.winning_trades}\n"
            f"虧損交易:     {self.losing_trades}\n"
            f"總盈虧:       {self.total_pnl:+.2f} USDT\n"
            f"最大回撤:     {self.max_drawdown_pct:.1f}%\n"
            f"平均獲利:     {self.avg_win:+.2f} USDT\n"
            f"平均虧損:     {self.avg_loss:+.2f} USDT\n"
            f"獲利因子:     {self.profit_factor:.2f}\n"
            f"{'='*60}"
        )


class Backtester:
    """回測引擎"""

    def __init__(self, config: dict):
        self.config = config
        self.initial_capital = config.get("account", {}).get("total_capital", 125)
        self.leverage = config.get("account", {}).get("leverage", 3)
        self.risk_per_trade = config.get("risk", {}).get("risk_per_trade", 0.02)

    def run(
        self,
        strategy,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        df_htf: Optional[pd.DataFrame] = None,
    ) -> BacktestResult:
        """
        執行回測

        Args:
            strategy: 策略實例 (BaseStrategy)
            df: 歷史數據 DataFrame
            symbol: 交易對
            timeframe: K 線週期
            df_htf: 高時間框架確認數據（可選）

        Returns:
            BacktestResult
        """
        logger.info(f"開始回測: {strategy.get_strategy_name()} | {symbol} | {timeframe}")

        # 計算指標
        df = strategy.calculate_indicators(df.copy())
        if df_htf is not None and hasattr(strategy, "set_htf_data"):
            strategy.set_htf_data(df_htf)

        # 初始化狀態
        balance = self.initial_capital
        peak_balance = balance
        max_drawdown = 0.0
        trades: list[BacktestTrade] = []
        open_trade: Optional[BacktestTrade] = None
        trade_count = 0

        # 逐根 K 線模擬
        for i in range(50, len(df)):  # 跳過前 50 根用於指標預熱
            row = df.iloc[i]
            current_price = row["close"]
            current_time = row["timestamp"]

            # 檢查是否有持倉需要結算
            if open_trade is not None:
                hit_sl = False
                hit_tp = False

                if open_trade.side == "LONG":
                    hit_sl = row["low"] <= open_trade.stop_loss
                    hit_tp = row["high"] >= open_trade.take_profit
                else:
                    hit_sl = row["high"] >= open_trade.stop_loss
                    hit_tp = row["low"] <= open_trade.take_profit

                if hit_sl or hit_tp:
                    if hit_sl:
                        exit_price = open_trade.stop_loss
                        exit_reason = "停損"
                    else:
                        exit_price = open_trade.take_profit
                        exit_reason = "停利"

                    # 計算盈虧
                    if open_trade.side == "LONG":
                        pnl_pct = ((exit_price - open_trade.entry_price) / open_trade.entry_price) * 100
                    else:
                        pnl_pct = ((open_trade.entry_price - exit_price) / open_trade.entry_price) * 100

                    pnl = (pnl_pct / 100) * open_trade.amount * open_trade.entry_price

                    open_trade.exit_price = exit_price
                    open_trade.exit_time = current_time
                    open_trade.pnl = pnl
                    open_trade.pnl_pct = pnl_pct
                    open_trade.exit_reason = exit_reason
                    trades.append(open_trade)

                    balance += pnl
                    if balance > peak_balance:
                        peak_balance = balance
                    dd = ((peak_balance - balance) / peak_balance) * 100 if peak_balance > 0 else 0
                    if dd > max_drawdown:
                        max_drawdown = dd

                    open_trade = None
                    continue

            # 沒有持倉時，檢查新信號
            if open_trade is None:
                # 為策略提供截止到當前的數據
                signal = strategy.get_signal(df.iloc[: i + 1])

                if signal is not None:
                    trade_count += 1

                    # 計算倉位大小
                    risk_amount = balance * self.risk_per_trade
                    sl_distance = abs(signal["entry"] - signal["stop_loss"])
                    if sl_distance == 0:
                        continue
                    amount = (risk_amount / sl_distance) * self.leverage

                    open_trade = BacktestTrade(
                        trade_id=trade_count,
                        symbol=symbol,
                        side=signal["side"],
                        entry_price=signal["entry"],
                        entry_time=current_time,
                        stop_loss=signal["stop_loss"],
                        take_profit=signal["take_profit"],
                        amount=amount,
                        reason=signal.get("reason", ""),
                    )

        # 結算仍在持倉的交易
        if open_trade is not None:
            last_price = df.iloc[-1]["close"]
            if open_trade.side == "LONG":
                pnl_pct = ((last_price - open_trade.entry_price) / open_trade.entry_price) * 100
            else:
                pnl_pct = ((open_trade.entry_price - last_price) / open_trade.entry_price) * 100

            pnl = (pnl_pct / 100) * open_trade.amount * open_trade.entry_price
            open_trade.exit_price = last_price
            open_trade.exit_time = df.iloc[-1]["timestamp"]
            open_trade.pnl = pnl
            open_trade.pnl_pct = pnl_pct
            open_trade.exit_reason = "回測結束"
            trades.append(open_trade)
            balance += pnl

        # 計算結果
        result = self._calculate_result(
            strategy.get_strategy_name(), symbol, timeframe,
            len(df) // (96 if timeframe == "15m" else 288),  # 粗略天數
            trades, max_drawdown
        )

        logger.info(result.summary())
        return result

    def _calculate_result(
        self, strategy_name: str, symbol: str, timeframe: str,
        period_days: int, trades: list[BacktestTrade], max_drawdown: float
    ) -> BacktestResult:
        """計算回測統計數據"""
        result = BacktestResult(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            period_days=max(period_days, 1),
            trades=trades,
            max_drawdown_pct=max_drawdown,
        )

        if not trades:
            return result

        result.total_trades = len(trades)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]

        result.winning_trades = len(wins)
        result.losing_trades = len(losses)
        result.win_rate = (len(wins) / len(trades)) * 100 if trades else 0
        result.total_pnl = sum(t.pnl for t in trades)

        if wins:
            result.avg_win = sum(t.pnl for t in wins) / len(wins)
        if losses:
            result.avg_loss = sum(t.pnl for t in losses) / len(losses)

        total_wins = sum(t.pnl for t in wins) if wins else 0
        total_losses = abs(sum(t.pnl for t in losses)) if losses else 0
        result.profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

        return result

    def run_multi_symbol(
        self, strategy, data_dict: dict[str, pd.DataFrame], timeframe: str
    ) -> dict[str, BacktestResult]:
        """
        對多個交易對執行回測

        Args:
            strategy: 策略實例
            data_dict: {symbol: DataFrame} 字典
            timeframe: K 線週期

        Returns:
            {symbol: BacktestResult} 字典
        """
        results = {}
        for symbol, df in data_dict.items():
            try:
                results[symbol] = self.run(strategy, df, symbol, timeframe)
            except Exception as e:
                logger.error(f"{symbol} 回測失敗: {e}")
        return results
