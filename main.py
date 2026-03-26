"""
Crypto Trading Bot v2.0
多策略自動交易機器人 - 趨勢跟踪 + 動態選幣 + 自動策略切換

主程式入口
"""

import sys
import time
import logging
import yaml
from datetime import datetime, date, timedelta
from pathlib import Path

# 設定專案根目錄
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from core.exchange import BinanceExchange
from core.risk_manager import RiskManager
from core.order_manager import OrderManager
from core.pair_selector import PairSelector
from strategies.grid_strategy import GridStrategy
from strategies.trend_strategy import TrendStrategy
from strategies.strategy_selector import StrategySelector
from notifications.telegram_bot import TelegramNotifier
from dashboard.monitor import Dashboard


def setup_logging(config: dict):
    """設定日誌"""
    log_file = config.get("system", {}).get("log_file", "trading.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def load_config() -> dict:
    """載入設定檔"""
    config_path = PROJECT_DIR / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"找不到設定檔: {config_path}")

    with open(config_path, "r", encoding="utf-8-sig") as f:
        return yaml.safe_load(f)


def main():
    # 載入設定
    config = load_config()
    setup_logging(config)
    logger = logging.getLogger(__name__)

    # 初始化元件
    dashboard = Dashboard(config)
    dashboard.print_startup_banner(config)

    logger.info("=" * 60)
    logger.info("Crypto Trading Bot v2.0 啟動")
    logger.info("=" * 60)

    # 建立交易目錄和數據目錄
    trade_dir = config.get("system", {}).get("trade_log_dir", "trades")
    data_dir = config.get("system", {}).get("data_dir", "data")
    Path(trade_dir).mkdir(exist_ok=True)
    Path(data_dir).mkdir(exist_ok=True)

    # 初始化交易所連線
    try:
        exchange = BinanceExchange(config)
        logger.info("交易所連線成功")
    except Exception as e:
        logger.error(f"交易所連線失敗: {e}")
        sys.exit(1)

    # 初始化元件
    risk_manager = RiskManager(config)
    order_manager = OrderManager(exchange, risk_manager)
    notifier = TelegramNotifier(config)

    # 初始化策略
    grid_enabled = config.get("grid", {}).get("enabled", False)
    grid_strategy = GridStrategy(config) if grid_enabled else None
    trend_strategy = TrendStrategy(config)
    selector = StrategySelector(
        grid_strategy, trend_strategy, config
    ) if grid_enabled else None

    # ========== 動態選幣 ==========
    symbols_mode = config.get("symbols_mode", "fixed")
    pair_selector = PairSelector(exchange, config) if symbols_mode == "dynamic" else None

    if symbols_mode == "dynamic":
        logger.info("啟用動態選幣模式 - 自動選擇成交量前 N 名幣種")
        symbols = pair_selector.get_top_volume_pairs()
    else:
        symbols = config.get("symbols", ["BTC/USDT:USDT", "ETH/USDT:USDT"])
        logger.info(f"使用固定交易對: {symbols}")

    loop_interval = config.get("system", {}).get("loop_interval", 30)
    leverage = config.get("account", {}).get("leverage", 3)
    total_capital = config.get("account", {}).get("total_capital", 25)

    # 設定槓桿和保證金模式
    margin_type = config.get("account", {}).get("margin_type", "isolated")
    for symbol in symbols:
        try:
            exchange.set_margin_and_leverage(symbol, margin_type, leverage)
        except Exception as e:
            logger.warning(f"{symbol} 設定槓桿失敗（可能不支援）: {e}")

    # 取得初始餘額
    balance = exchange.get_balance()
    risk_manager.current_balance = balance
    risk_manager.peak_balance = max(risk_manager.peak_balance, balance)
    logger.info(f"帳戶餘額: {balance:.2f} USDT")
    logger.info(f"測試資金: {total_capital} USDT（風險控制以此為基準）")

    # 通知啟動
    strategy_name = "趨勢跟踪" if not grid_enabled else "網格 + 趨勢自動切換"
    notifier.notify_bot_start(symbols[:5], f"{strategy_name} | 動態選幣" if pair_selector else strategy_name)

    # 追蹤最近信號
    recent_signals = []
    last_daily_reset = date.today()
    last_pair_refresh = datetime.now()
    refresh_hours = config.get("pair_selector", {}).get("refresh_hours", 24)

    logger.info(f"開始交易循環 | 掃描間隔: {loop_interval}秒 | 交易對數: {len(symbols)}")
    logger.info("=" * 60)

    while True:
        try:
            # ========== 每日動作 ==========
            if date.today() != last_daily_reset:
                # 發送每日摘要
                risk_status = risk_manager.get_status()
                notifier.notify_daily_summary(
                    balance, risk_status.get("daily_pnl", 0),
                    risk_status.get("trade_count", 0),
                    risk_status.get("win_rate", 0),
                    risk_status.get("drawdown_pct", 0),
                )
                risk_manager.reset_daily()
                last_daily_reset = date.today()
                logger.info("每日重置完成")

            # ========== 動態選幣刷新 ==========
            if pair_selector:
                hours_since_refresh = (datetime.now() - last_pair_refresh).total_seconds() / 3600
                if hours_since_refresh >= refresh_hours:
                    logger.info("重新選擇交易對...")
                    new_symbols = pair_selector.get_top_volume_pairs()
                    # 設定新幣種的槓桿
                    for sym in new_symbols:
                        if sym not in symbols:
                            try:
                                exchange.set_margin_and_leverage(sym, margin_type, leverage)
                            except Exception:
                                pass
                    symbols = new_symbols
                    last_pair_refresh = datetime.now()
                    logger.info(f"交易對已更新: {len(symbols)} 個")

            # 更新餘額
            balance = exchange.get_balance()
            risk_manager.current_balance = balance

            # 檢查已有持倉的狀態
            positions = exchange.get_positions()
            position_count = len(positions)

            # 取得風控狀態
            risk_status = risk_manager.get_status()

            # 市場狀態分析
            market_states = {}

            for symbol in symbols:
                try:
                    # 拉取主時間框架數據
                    df = exchange.fetch_ohlcv(symbol, "15m", 200)
                    if df is None or len(df) < 50:
                        continue

                    # 取得市場狀態並選擇策略
                    if selector:
                        market_state = selector.get_market_state(df)
                        strategy = selector.select_strategy(df)
                    else:
                        market_state = "trend_only"
                        strategy = trend_strategy
                    market_states[symbol] = market_state

                    # 計算指標
                    df = strategy.calculate_indicators(df)

                    # 如果是趨勢策略，提供高時間框架數據
                    if hasattr(strategy, 'set_htf_data'):
                        df_htf = exchange.fetch_ohlcv(
                            symbol,
                            config.get("trend", {}).get("confirm_timeframe", "1h"),
                            100
                        )
                        if df_htf is not None:
                            strategy.set_htf_data(df_htf)

                    # 取得信號
                    signal = strategy.get_signal(df)

                    if signal:
                        # 記錄信號
                        signal_record = {
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "symbol": symbol,
                            "side": signal["side"],
                            "price": signal["entry"],
                            "reason": signal.get("reason", ""),
                        }
                        recent_signals.append(signal_record)
                        if len(recent_signals) > 20:
                            recent_signals = recent_signals[-20:]

                        logger.info(
                            f"信號: {signal['side']} {symbol} | "
                            f"策略: {strategy.get_strategy_name()} | "
                            f"原因: {signal.get('reason', '')}"
                        )

                        # 檢查是否可以開倉
                        if risk_manager.can_open_trade(
                            position_count, risk_status.get("daily_pnl", 0)
                        ):
                            if not exchange.has_position(symbol):
                                # 用測試資金計算倉位（不是全部餘額）
                                capital_for_risk = min(total_capital, balance)
                                risk_pct = risk_manager.get_current_risk_pct()
                                sl_distance = abs(signal["entry"] - signal["stop_loss"])

                                if sl_distance > 0:
                                    risk_amount = capital_for_risk * risk_pct
                                    amount = risk_amount / sl_distance

                                    # 精度處理
                                    try:
                                        amount = float(exchange.exchange.amount_to_precision(symbol, amount))
                                    except Exception:
                                        pass

                                    # 檢查最小名義價值（Binance 最低 5 USDT）
                                    notional = amount * signal["entry"]
                                    if notional < 5.5:
                                        logger.info(f"{symbol} 名義價值 {notional:.2f} < 5.5 USDT，跳過")
                                        continue

                                    order_side = "buy" if signal["side"] == "LONG" else "sell"

                                    # 停損停利價格精度
                                    try:
                                        sl_price = float(exchange.exchange.price_to_precision(symbol, signal["stop_loss"]))
                                        tp_price = float(exchange.exchange.price_to_precision(symbol, signal["take_profit"]))
                                    except Exception:
                                        sl_price = signal["stop_loss"]
                                        tp_price = signal["take_profit"]

                                    trade_result = order_manager.open_position(
                                        symbol=symbol,
                                        side=order_side,
                                        entry_price=signal["entry"],
                                        stop_loss=sl_price,
                                        take_profit=tp_price,
                                        amount=amount,
                                    )

                                    if trade_result and trade_result.get("status") == "open":
                                        position_count += 1
                                        notifier.notify_trade_open(
                                            symbol, signal["side"],
                                            signal["entry"], amount,
                                            sl_price, tp_price,
                                            strategy.get_strategy_name(),
                                        )

                except Exception as e:
                    logger.error(f"{symbol} 處理失敗: {e}")

            # ========== 檢查已關閉的持倉 ==========
            exchange_positions = exchange.get_positions()
            exchange_symbols = {p["symbol"] for p in exchange_positions}
            closed_symbols = [
                sym for sym in list(order_manager.active_trades.keys())
                if sym not in exchange_symbols
            ]
            for sym in closed_symbols:
                trade = order_manager.active_trades.pop(sym, None)
                if trade:
                    try:
                        ticker = exchange.get_ticker(sym)
                        exit_price = ticker.get("last", trade["entry_price"])
                    except Exception:
                        exit_price = trade["entry_price"]

                    if trade["side"] == "buy":
                        pnl = (exit_price - trade["entry_price"]) * trade["amount"]
                        pnl_pct = ((exit_price - trade["entry_price"]) / trade["entry_price"]) * 100
                    else:
                        pnl = (trade["entry_price"] - exit_price) * trade["amount"]
                        pnl_pct = ((trade["entry_price"] - exit_price) / trade["entry_price"]) * 100

                    risk_manager.update_trade_result(pnl)
                    side_label = "LONG" if trade["side"] == "buy" else "SHORT"
                    notifier.notify_trade_close(sym, side_label, pnl, pnl_pct, "停損/停利觸發")
                    logger.info(f"倉位已關閉: {sym} | {side_label} | 盈虧: {pnl:+.2f} USDT")

            # 更新儀表板
            dashboard.display_status(
                balance=balance,
                positions=positions,
                risk_status=risk_status,
                market_states=market_states,
                recent_signals=recent_signals,
            )

            # 等待下一輪
            time.sleep(loop_interval)

        except KeyboardInterrupt:
            logger.info("使用者中斷，機器人停止")
            notifier.notify_bot_stop("手動停止")
            risk_status = risk_manager.get_status()
            logger.info(f"最終餘額: {balance:.2f} USDT")
            logger.info(f"累計盈虧: {risk_status.get('total_pnl', 0):+.2f} USDT")
            break

        except Exception as e:
            logger.error(f"主迴圈錯誤: {e}")
            notifier.notify_error(str(e))
            logger.info("30 秒後重試...")
            time.sleep(30)


if __name__ == "__main__":
    main()
