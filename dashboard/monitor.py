"""
即時監控儀表板 - 在終端機顯示交易狀態
使用 rich 庫實現美觀的終端介面
"""

import logging
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.live import Live
import time
import sys
import io

logger = logging.getLogger(__name__)
# 設定 UTF-8 編碼以支持繁體中文
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
console = Console(force_terminal=True, width=120, legacy_windows=False)


class Dashboard:
    """即時監控儀表板"""

    def __init__(self, config: dict):
        self.config = config
        self.symbols = config.get("symbols", [])
        self.start_time = datetime.now()

    def display_status(
        self,
        balance: float,
        positions: list[dict],
        risk_status: dict,
        market_states: dict[str, str],
        recent_signals: list[dict] = None,
    ):
        """
        顯示即時狀態

        Args:
            balance: 當前餘額
            positions: 持倉列表
            risk_status: 風險管理狀態
            market_states: {symbol: "trending"/"ranging"} 市場狀態
            recent_signals: 最近的交易信號
        """
        console.clear()

        # 標題
        uptime = datetime.now() - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        title = Text()
        title.append("Crypto Trading Bot", style="bold cyan")
        title.append(f"  |  運行時間: {hours:02d}:{minutes:02d}:{seconds:02d}", style="dim")
        title.append(f"  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
        console.print(Panel(title, border_style="cyan"))

        # 帳戶狀態
        self._display_account(balance, risk_status)

        # 持倉狀態
        self._display_positions(positions)

        # 市場狀態
        self._display_market_states(market_states)

        # 最近信號
        if recent_signals:
            self._display_signals(recent_signals)

        # 風控狀態
        self._display_risk_status(risk_status)

    def _display_account(self, balance: float, risk_status: dict):
        """顯示帳戶資訊"""
        table = Table(title="帳戶狀態", border_style="green", title_style="bold green")
        table.add_column("項目", style="white")
        table.add_column("數值", style="cyan", justify="right")

        initial = self.config.get("account", {}).get("total_capital", 125)
        pnl = balance - initial
        pnl_pct = (pnl / initial) * 100 if initial > 0 else 0
        pnl_style = "green" if pnl >= 0 else "red"

        table.add_row("餘額", f"{balance:.2f} USDT")
        table.add_row("累計盈虧", Text(f"{pnl:+.2f} USDT ({pnl_pct:+.1f}%)", style=pnl_style))
        table.add_row("今日盈虧", Text(f"{risk_status.get('daily_pnl', 0):+.2f} USDT",
                       style="green" if risk_status.get("daily_pnl", 0) >= 0 else "red"))
        table.add_row("交易次數", str(risk_status.get("trade_count", 0)))
        table.add_row("勝率", f"{risk_status.get('win_rate', 0):.1f}%")

        console.print(table)

    def _display_positions(self, positions: list[dict]):
        """顯示持倉"""
        table = Table(title="當前持倉", border_style="yellow", title_style="bold yellow")
        table.add_column("交易對", style="white")
        table.add_column("方向", style="white")
        table.add_column("進場價", style="cyan", justify="right")
        table.add_column("當前價", style="cyan", justify="right")
        table.add_column("未實現盈虧", justify="right")
        table.add_column("策略", style="dim")

        if not positions:
            table.add_row("(無持倉)", "-", "-", "-", "-", "-")
        else:
            for pos in positions:
                pnl = pos.get("unrealizedPnl", 0)
                pnl_style = "green" if pnl >= 0 else "red"
                side_style = "green" if pos.get("side") == "long" else "red"

                table.add_row(
                    pos.get("symbol", ""),
                    Text(pos.get("side", "").upper(), style=side_style),
                    f"{pos.get('entryPrice', 0):.6f}",
                    f"{pos.get('markPrice', 0):.6f}",
                    Text(f"{pnl:+.2f} USDT", style=pnl_style),
                    pos.get("strategy", ""),
                )

        console.print(table)

    def _display_market_states(self, market_states: dict[str, str]):
        """顯示市場狀態"""
        table = Table(title="市場分析", border_style="blue", title_style="bold blue")
        table.add_column("交易對", style="white")
        table.add_column("市場狀態", style="white")
        table.add_column("選用策略", style="cyan")

        for symbol, state in market_states.items():
            if state == "trending":
                state_text = Text("趨勢", style="bold green")
                strategy = "趨勢跟踪"
            elif state == "ranging":
                state_text = Text("震盪", style="bold yellow")
                strategy = "網格交易"
            elif state == "trend_only":
                state_text = Text("趨勢", style="bold green")
                strategy = "趨勢跟踪"
            else:
                state_text = Text("混合", style="bold white")
                strategy = "趨勢跟踪"  # 預設改為趨勢跟踪

            short_symbol = symbol.split("/")[0] if "/" in symbol else symbol
            table.add_row(short_symbol, state_text, strategy)

        console.print(table)

    def _display_signals(self, signals: list[dict]):
        """顯示最近交易信號"""
        table = Table(title="最近信號 (最新 5 筆)", border_style="magenta", title_style="bold magenta")
        table.add_column("時間", style="dim")
        table.add_column("交易對", style="white")
        table.add_column("方向", style="white")
        table.add_column("價格", style="cyan", justify="right")
        table.add_column("原因", style="dim")

        for sig in signals[-5:]:
            side_style = "green" if sig.get("side") == "LONG" else "red"
            table.add_row(
                sig.get("time", ""),
                sig.get("symbol", ""),
                Text(sig.get("side", ""), style=side_style),
                f"{sig.get('price', 0):.6f}",
                sig.get("reason", ""),
            )

        console.print(table)

    def _display_risk_status(self, risk_status: dict):
        """顯示風控狀態"""
        dd = risk_status.get("drawdown_pct", 0)
        max_dd = self.config.get("risk", {}).get("max_drawdown_pct", 12)
        streak = risk_status.get("consecutive_losses", 0)
        limit = self.config.get("risk", {}).get("loss_streak_limit", 4)

        dd_color = "green" if dd < max_dd * 0.5 else ("yellow" if dd < max_dd * 0.8 else "red")
        streak_color = "green" if streak < limit * 0.5 else ("yellow" if streak < limit else "red")

        risk_text = Text()
        risk_text.append(f"回撤: ", style="white")
        risk_text.append(f"{dd:.1f}%/{max_dd}%", style=dd_color)
        risk_text.append(f"  |  連虧: ", style="white")
        risk_text.append(f"{streak}/{limit}", style=streak_color)
        risk_text.append(f"  |  風險/筆: ", style="white")
        risk_text.append(f"{risk_status.get('current_risk_pct', 0.02) * 100:.1f}%", style="cyan")

        can_trade = risk_status.get("can_trade", True)
        if can_trade:
            risk_text.append(f"  |  狀態: ", style="white")
            risk_text.append("正常交易中", style="bold green")
        else:
            risk_text.append(f"  |  狀態: ", style="white")
            risk_text.append("已暫停交易", style="bold red")

        console.print(Panel(risk_text, title="風控狀態", border_style="red" if not can_trade else "green"))

    def print_startup_banner(self, config: dict):
        """顯示啟動畫面"""
        banner = """
   ____                  _          ____        _
  / ___|_ __ _   _ _ __ | |_ ___   | __ )  ___ | |_
 | |   | '__| | | | '_ \\| __/ _ \\  |  _ \\ / _ \\| __|
 | |___| |  | |_| | |_) | || (_) | | |_) | (_) | |_
  \\____|_|   \\__, | .__/ \\__\\___/  |____/ \\___/ \\__|
             |___/|_|
        """
        console.print(Text(banner, style="bold cyan"))
        console.print(f"  版本: 2.0.0 | 策略: 網格 + 趨勢自動切換", style="dim")
        console.print(f"  交易對: {', '.join(config.get('symbols', []))}", style="dim")
        console.print(f"  槓桿: {config.get('account', {}).get('leverage', 3)}x", style="dim")
        console.print()
