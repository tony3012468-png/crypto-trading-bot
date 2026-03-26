"""
回測執行腳本 - 下載歷史數據並驗證策略表現
"""

import sys
import yaml
import logging
from pathlib import Path

# 設定專案根目錄
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from backtest.data_loader import DataLoader
from backtest.backtester import Backtester
from strategies.grid_strategy import GridStrategy
from strategies.trend_strategy import TrendStrategy
from strategies.strategy_selector import StrategySelector

# 日誌設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """載入設定檔"""
    config_path = PROJECT_DIR / "config.yaml"
    with open(config_path, "r", encoding="utf-8-sig") as f:
        return yaml.safe_load(f)


def main():
    config = load_config()
    symbols = config.get("symbols", [])

    logger.info("=" * 60)
    logger.info("開始回測驗證")
    logger.info(f"交易對: {symbols}")
    logger.info("=" * 60)

    # 初始化元件
    data_loader = DataLoader(str(PROJECT_DIR / "data"))
    backtester = Backtester(config)
    grid_strategy = GridStrategy(config)
    trend_strategy = TrendStrategy(config)
    selector = StrategySelector(grid_strategy, trend_strategy, config)

    all_results = []

    for symbol in symbols:
        logger.info(f"\n{'='*60}")
        logger.info(f"回測交易對: {symbol}")
        logger.info(f"{'='*60}")

        try:
            # 下載歷史數據
            df_15m = data_loader.fetch_historical(symbol, "15m", days=30)
            df_1h = data_loader.fetch_historical(symbol, "1h", days=30)

            # 測試網格策略
            logger.info(f"\n--- 網格策略回測 ---")
            grid_result = backtester.run(grid_strategy, df_15m, symbol, "15m")
            all_results.append(("Grid", symbol, grid_result))

            # 測試趨勢策略
            logger.info(f"\n--- 趨勢策略回測 ---")
            trend_result = backtester.run(
                trend_strategy, df_15m, symbol, "15m", df_htf=df_1h
            )
            all_results.append(("Trend", symbol, trend_result))

        except Exception as e:
            logger.error(f"{symbol} 回測失敗: {e}")

    # 輸出總結
    logger.info("\n" + "=" * 70)
    logger.info("回測總結")
    logger.info("=" * 70)
    logger.info(f"{'策略':<15} {'交易對':<20} {'交易數':<8} {'勝率':<8} {'盈虧(USDT)':<12} {'最大回撤':<10}")
    logger.info("-" * 70)

    total_pnl = 0
    for strategy_name, symbol, result in all_results:
        short_symbol = symbol.split("/")[0] if "/" in symbol else symbol
        logger.info(
            f"{strategy_name:<15} {short_symbol:<20} {result.total_trades:<8} "
            f"{result.win_rate:<8.1f} {result.total_pnl:<12.2f} {result.max_drawdown_pct:<10.1f}"
        )
        total_pnl += result.total_pnl

    logger.info("-" * 70)
    logger.info(f"{'總計':<35} {'':8} {total_pnl:<12.2f}")
    logger.info("=" * 70)

    if total_pnl > 0:
        logger.info(f"\n回測結果為正！預估月收益: {total_pnl:.2f} USDT")
        logger.info("建議先用小資金 ($20-30) 實盤測試 24-48 小時")
    else:
        logger.info(f"\n回測結果為負 ({total_pnl:.2f} USDT)，建議調整策略參數")


if __name__ == "__main__":
    main()
