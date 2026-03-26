"""
Daily Trading Report Generator
每日交易報告生成器 - 包含圖表和統計分析
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import defaultdict
import re

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import rcParams

# 設定專案根目錄
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from core.risk_manager import RiskManager
import yaml


# 設置中文字體支援
rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
rcParams['axes.unicode_minus'] = False

logger = logging.getLogger(__name__)


class DailyReportGenerator:
    """每日報告生成器"""

    def __init__(self, config: dict):
        self.config = config
        self.trade_log_dir = Path(config.get("system", {}).get("trade_log_dir", "trades"))
        self.log_file = config.get("system", {}).get("log_file", "trading.log")
        self.today = date.today()

    def parse_trading_log(self) -> dict:
        """解析交易日誌，提取今日交易數據"""
        trades = []

        if not Path(self.log_file).exists():
            return {"trades": [], "signals": []}

        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                # 提取今日交易（包含信號和交易關閉）
                if self.today.isoformat() in line:
                    # 信號
                    if "信號:" in line:
                        match = re.search(r"信號: (\w+) (\S+) \| .*價格: ([\d.]+)", line)
                        if match:
                            trades.append({
                                "type": "signal",
                                "side": match.group(1),
                                "symbol": match.group(2),
                                "price": float(match.group(3)),
                                "timestamp": self._extract_time(line),
                            })

                    # 交易關閉
                    if "倉位已關閉:" in line or "盈虧:" in line:
                        match = re.search(r"盈虧: ([+-]?\d+\.?\d*)", line)
                        if match:
                            pnl = float(match.group(1))
                            trades.append({
                                "type": "close",
                                "pnl": pnl,
                                "timestamp": self._extract_time(line),
                            })

        return {"trades": trades}

    def _extract_time(self, log_line: str) -> str:
        """從日誌行提取時間戳"""
        match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", log_line)
        if match:
            return match.group(1)
        return ""

    def parse_trade_files(self) -> list:
        """解析交易文件夾中的交易記錄"""
        all_trades = []

        if not self.trade_log_dir.exists():
            return []

        for file in self.trade_log_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    trade = json.load(f)
                    # 檢查是否是今日交易
                    if "close_time" in trade:
                        close_date = datetime.fromisoformat(trade["close_time"]).date()
                        if close_date == self.today:
                            all_trades.append(trade)
            except Exception as e:
                logger.warning(f"無法解析交易文件 {file}: {e}")

        return all_trades

    def calculate_statistics(self, trades: list) -> dict:
        """計算交易統計"""
        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "best_trade": 0,
                "worst_trade": 0,
                "profit_factor": 0,
            }

        pnls = [t.get("pnl", 0) for t in trades if "pnl" in t]

        if not pnls:
            pnls = [0]

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        return {
            "total_trades": len(pnls),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": (len(wins) / len(pnls) * 100) if pnls else 0,
            "total_pnl": sum(pnls),
            "avg_win": (sum(wins) / len(wins)) if wins else 0,
            "avg_loss": (sum(losses) / len(losses)) if losses else 0,
            "best_trade": max(pnls) if pnls else 0,
            "worst_trade": min(pnls) if pnls else 0,
            "profit_factor": (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else 0,
        }

    def generate_charts(self, trades: list, stats: dict) -> str:
        """生成報告圖表"""
        chart_path = PROJECT_DIR / f"report_{self.today}.png"

        # 建立圖表網格
        fig = plt.figure(figsize=(16, 12), dpi=100)

        # 1. 盈虧曲線
        ax1 = plt.subplot(2, 3, 1)
        pnls = [t.get("pnl", 0) for t in trades if "pnl" in t]
        if pnls:
            cumulative_pnl = np.cumsum(pnls)
            ax1.plot(range(len(cumulative_pnl)), cumulative_pnl, 'b-', linewidth=2, marker='o')
            ax1.fill_between(range(len(cumulative_pnl)), cumulative_pnl, alpha=0.3)
            ax1.axhline(y=0, color='r', linestyle='--', alpha=0.5)
            ax1.set_title("盈虧曲線", fontsize=12, fontweight='bold')
            ax1.set_xlabel("交易序號")
            ax1.set_ylabel("累計盈虧 (USDT)")
            ax1.grid(True, alpha=0.3)

        # 2. 交易勝負分佈
        ax2 = plt.subplot(2, 3, 2)
        sizes = [stats["winning_trades"], stats["losing_trades"]]
        colors = ['#2ecc71', '#e74c3c']
        labels = [f'獲利 ({stats["winning_trades"]})', f'虧損 ({stats["losing_trades"]})']
        if sum(sizes) > 0:
            ax2.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
            ax2.set_title("交易勝負比例", fontsize=12, fontweight='bold')

        # 3. 單筆交易 P&L 分佈
        ax3 = plt.subplot(2, 3, 3)
        if pnls:
            ax3.bar(range(len(pnls)), pnls, color=['#2ecc71' if p > 0 else '#e74c3c' for p in pnls])
            ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
            ax3.set_title("單筆交易盈虧", fontsize=12, fontweight='bold')
            ax3.set_xlabel("交易序號")
            ax3.set_ylabel("盈虧 (USDT)")
            ax3.grid(True, alpha=0.3, axis='y')

        # 4. 統計信息表
        ax4 = plt.subplot(2, 3, 4)
        ax4.axis('off')
        stats_text = f"""
交易統計
━━━━━━━━━━━━━━━━━━
總交易數: {stats['total_trades']}
獲利交易: {stats['winning_trades']}
虧損交易: {stats['losing_trades']}
勝率: {stats['win_rate']:.1f}%

累計盈虧: {stats['total_pnl']:+.2f} USDT
平均獲利: {stats['avg_win']:+.2f} USDT
平均虧損: {stats['avg_loss']:+.2f} USDT
最佳交易: {stats['best_trade']:+.2f} USDT
最差交易: {stats['worst_trade']:+.2f} USDT
利潤因子: {stats['profit_factor']:.2f}
        """
        ax4.text(0.1, 0.5, stats_text, fontsize=10, family='monospace',
                verticalalignment='center', bbox=dict(boxstyle='round',
                facecolor='wheat', alpha=0.3))

        # 5. 交易對績效
        ax5 = plt.subplot(2, 3, 5)
        symbol_pnl = defaultdict(float)
        symbol_count = defaultdict(int)
        for t in trades:
            if "symbol" in t and "pnl" in t:
                symbol_pnl[t["symbol"]] += t["pnl"]
                symbol_count[t["symbol"]] += 1

        if symbol_pnl:
            symbols = list(symbol_pnl.keys())
            pnls_by_symbol = list(symbol_pnl.values())
            colors_sym = ['#2ecc71' if p > 0 else '#e74c3c' for p in pnls_by_symbol]
            ax5.barh(symbols, pnls_by_symbol, color=colors_sym)
            ax5.set_title("交易對績效", fontsize=12, fontweight='bold')
            ax5.set_xlabel("累計盈虧 (USDT)")
            ax5.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
            ax5.grid(True, alpha=0.3, axis='x')

        # 6. 時間分佈
        ax6 = plt.subplot(2, 3, 6)
        times = [t.get("timestamp", "")[:2] for t in trades if t.get("timestamp")]
        time_counts = defaultdict(int)
        for t in times:
            if t:
                time_counts[t] += 1

        if time_counts:
            hours = sorted(time_counts.keys())
            counts = [time_counts[h] for h in hours]
            ax6.bar(hours, counts, color='#3498db')
            ax6.set_title("交易時間分佈", fontsize=12, fontweight='bold')
            ax6.set_xlabel("時間 (小時)")
            ax6.set_ylabel("交易數")
            ax6.grid(True, alpha=0.3, axis='y')

        plt.suptitle(f"每日交易報告 - {self.today.strftime('%Y-%m-%d')}",
                    fontsize=16, fontweight='bold', y=0.995)
        plt.tight_layout()

        plt.savefig(chart_path, dpi=100, bbox_inches='tight', facecolor='white')
        logger.info(f"圖表已生成: {chart_path}")
        plt.close()

        return str(chart_path)

    def generate_report(self) -> dict:
        """生成完整報告"""
        logger.info(f"開始生成 {self.today} 的交易報告")

        # 解析交易數據
        trades = self.parse_trade_files()

        # 計算統計
        stats = self.calculate_statistics(trades)

        # 生成圖表
        chart_path = None
        if trades:
            chart_path = self.generate_charts(trades, stats)

        # 生成報告文本
        report = {
            "date": self.today.isoformat(),
            "timestamp": datetime.now().isoformat(),
            "trades": trades,
            "statistics": stats,
            "chart_path": chart_path,
            "summary": self._generate_summary(stats, trades),
        }

        logger.info("報告生成完成")
        return report

    def _generate_summary(self, stats: dict, trades: list) -> str:
        """生成報告摘要"""
        summary = f"""
📊 {self.today.strftime('%Y-%m-%d')} 交易報告摘要
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 交易成績
• 總交易數: {stats['total_trades']} 筆
• 獲利交易: {stats['winning_trades']} 筆 ({stats['win_rate']:.1f}%)
• 虧損交易: {stats['losing_trades']} 筆

💰 盈虧統計
• 累計盈虧: {stats['total_pnl']:+.2f} USDT
• 平均獲利: {stats['avg_win']:+.2f} USDT/筆
• 平均虧損: {stats['avg_loss']:+.2f} USDT/筆
• 最佳交易: {stats['best_trade']:+.2f} USDT
• 最差交易: {stats['worst_trade']:+.2f} USDT
• 利潤因子: {stats['profit_factor']:.2f}

🎯 優化建議
"""

        # 根據數據提供優化建議
        suggestions = []

        if stats['total_trades'] == 0:
            suggestions.append("• 今日無交易信號")
        elif stats['win_rate'] < 40:
            suggestions.append("• 勝率較低，建議檢查進場條件")
        elif stats['win_rate'] > 70:
            suggestions.append("• 勝率很高，可考慮增加風險")

        if stats['profit_factor'] < 1:
            suggestions.append("• 利潤因子 < 1，虧損交易過多")
        elif stats['profit_factor'] > 3:
            suggestions.append("• 利潤因子很好，策略表現穩定")

        if stats['total_pnl'] > 0:
            suggestions.append(f"• 今日獲利！继续保持當前策略")
        elif stats['total_pnl'] < 0 and stats['total_trades'] > 0:
            suggestions.append(f"• 今日虧損，建議審視風險管理")

        if not suggestions:
            suggestions.append("• 數據不足，無法提供優化建議")

        summary += "\n".join(suggestions)
        summary += "\n\n✅ 報告已自動生成"

        return summary


def main():
    """主程序"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # 載入設定
    config_path = PROJECT_DIR / "config.yaml"
    with open(config_path, "r", encoding="utf-8-sig") as f:
        config = yaml.safe_load(f)

    # 生成報告
    generator = DailyReportGenerator(config)
    report = generator.generate_report()

    # 輸出報告信息
    print(report["summary"])
    if report["chart_path"]:
        print(f"圖表已保存: {report['chart_path']}")


if __name__ == "__main__":
    main()
