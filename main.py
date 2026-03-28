"""
Crypto Trading Bot v3.0
多策略自動交易機器人 - 趨勢跟踪 + 動態選幣 + TradingCompany 整合

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
from agents import TradingCompany


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


def _run_research(company):
    """背景執行策略研究（供觸發檔案使用）"""
    logger = logging.getLogger(__name__)
    try:
        today_strategies = company.strategy_developer.get_today_strategies()
        multi_results = company.backtest_engineer.run_multi_strategy_backtest(today_strategies)
        if multi_results:
            company.strategy_developer.update_scores(multi_results)
        backtest_results = company.backtest_engineer.run_auto_backtest()
        if backtest_results:
            perf = company.backtest_engineer.get_performance_summary()
            if perf:
                company.quant_researcher.update_performance(perf)
        developer_report = company.strategy_developer.run()
        backtest_report = company.backtest_engineer.run()
        researcher_report = company.quant_researcher.run()
        summary = "=== 策略競賽結果 ===\n" + developer_report + "\n\n" + backtest_report + "\n\n" + researcher_report
        company._send_long_message(summary)
        best = company.strategy_developer.get_best_strategies(1)
        if best:
            top = best[0]
            score = top.get("score", {})
            if score.get("composite_score", 0) > 0.65:
                alert = (
                    "🔔 高分策略發現！\n"
                    f"策略：{top['id']}\n"
                    f"複合評分：{score['composite_score']:.3f}\n"
                    f"勝率：{score['win_rate']:.1f}% | PF：{score['profit_factor']:.2f}"
                )
                company._send_long_message(alert)
        logger.info("策略研究完成")
    except Exception as e:
        logger.error(f"策略研究失敗: {e}")


def main(shared_company=None):
    # 載入設定
    config = load_config()
    setup_logging(config)
    logger = logging.getLogger(__name__)

    # 初始化元件
    dashboard = Dashboard(config)
    dashboard.print_startup_banner(config)

    logger.info("=" * 60)
    logger.info("Crypto Trading Bot v3.0 啟動")
    logger.info("=" * 60)

    # 建立目錄
    Path(config.get("system", {}).get("trade_log_dir", "trades")).mkdir(exist_ok=True)
    Path(config.get("system", {}).get("data_dir", "data")).mkdir(exist_ok=True)

    # 初始化交易所連線
    try:
        exchange = BinanceExchange(config)
        logger.info("交易所連線成功")
    except Exception as e:
        logger.error(f"交易所連線失敗: {e}")
        sys.exit(1)

    # 初始化核心元件
    risk_manager = RiskManager(config)
    order_manager = OrderManager(exchange, risk_manager)
    notifier = TelegramNotifier(config)

    # 使用外部傳入的 company（與排程器共享），或建立新的
    if shared_company is not None:
        company = shared_company
        # 注入真實的 risk_manager 和 exchange（排程器建立時可能為 None）
        company.risk_officer.risk_manager = risk_manager
        company.exchange = exchange
        company.backtest_engineer.exchange = exchange
        logger.info(f"[TradingCompany] 使用共享實例，風控官已連接 RiskManager")
    else:
        company = TradingCompany(
            config=config,
            exchange=exchange,
            notifier=notifier,
            risk_manager=risk_manager,
        )
    logger.info(f"[TradingCompany] 9 個部門已就位，月度目標：{TradingCompany.MONTHLY_TARGET} USDT")

    # 初始化策略
    grid_enabled = config.get("grid", {}).get("enabled", False)
    grid_strategy = GridStrategy(config) if grid_enabled else None
    trend_strategy = TrendStrategy(config)
    selector = StrategySelector(grid_strategy, trend_strategy, config) if grid_enabled else None

    # 動態選幣
    symbols_mode = config.get("symbols_mode", "fixed")
    pair_selector = PairSelector(exchange, config) if symbols_mode == "dynamic" else None

    if symbols_mode == "dynamic":
        logger.info("啟用動態選幣模式")
        symbols = pair_selector.get_top_volume_pairs()
    else:
        symbols = config.get("symbols", ["BTC/USDT:USDT", "ETH/USDT:USDT"])
        logger.info(f"使用固定交易對: {symbols}")

    loop_interval = config.get("system", {}).get("loop_interval", 30)
    leverage = config.get("account", {}).get("leverage", 3)
    margin_type = config.get("account", {}).get("margin_type", "isolated")
    # total_capital 不再限制實盤倉位，改用實際帳戶餘額
    # 僅保留供 risk_manager 初始化盈虧計算用
    total_capital = config.get("account", {}).get("total_capital", 500)

    # 設定槓桿和保證金模式
    for symbol in symbols:
        try:
            exchange.set_margin_and_leverage(symbol, margin_type, leverage)
            company.execution_engineer.mark_leverage_verified(symbol)
        except Exception as e:
            logger.warning(f"{symbol} 設定槓桿失敗: {e}")

    # 取得初始餘額（實盤使用實際帳戶餘額，無 25 USDT 限制）
    balance = exchange.get_balance()
    risk_manager.current_balance = balance
    risk_manager.peak_balance = max(risk_manager.peak_balance, balance)
    logger.info(f"帳戶餘額: {balance:.2f} USDT（實盤使用實際餘額）")

    # 從幣安同步真實交易歷史（確保重啟後紀錄不消失）
    logger.info("從幣安同步歷史交易紀錄...")
    risk_manager.sync_from_exchange(exchange)

    strategy_name = "趨勢跟踪" if not grid_enabled else "網格 + 趨勢自動切換"
    notifier.notify_bot_start(
        symbols[:5],
        f"{strategy_name} | 動態選幣 | TradingCompany v3.0" if pair_selector else strategy_name
    )

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
                risk_status = risk_manager.get_status()
                notifier.notify_daily_summary(
                    balance, risk_status.get("daily_pnl", 0),
                    risk_status.get("trade_count", 0),
                    risk_status.get("win_rate", 0),
                    risk_status.get("drawdown_pct", 0),
                )
                risk_manager.reset_daily()
                company.reset_daily()          # 情報員每日重置
                last_daily_reset = date.today()
                logger.info("每日重置完成")

            # ========== 動態選幣刷新 ==========
            if pair_selector:
                hours_since_refresh = (datetime.now() - last_pair_refresh).total_seconds() / 3600
                if hours_since_refresh >= refresh_hours:
                    logger.info("重新選擇交易對...")
                    new_symbols = pair_selector.get_top_volume_pairs()
                    for sym in new_symbols:
                        if sym not in symbols:
                            try:
                                exchange.set_margin_and_leverage(sym, margin_type, leverage)
                                company.execution_engineer.mark_leverage_verified(sym)
                            except Exception:
                                pass
                    symbols = new_symbols
                    last_pair_refresh = datetime.now()
                    logger.info(f"交易對已更新: {len(symbols)} 個")

            # 更新餘額
            balance = exchange.get_balance()
            risk_manager.current_balance = balance

            # 取得持倉
            positions = exchange.get_positions()
            position_count = len(positions)

            # 取得風控狀態並更新風控官
            risk_status = risk_manager.get_status()

            # 情報員：掃描整體市場行情（每隔數次掃描更新一次，避免過多 API 請求）
            market_states = {}

            for symbol in symbols:
                try:
                    # 拉取 K 線
                    df = exchange.fetch_ohlcv(symbol, "15m", 200)
                    if df is None or len(df) < 50:
                        continue

                    # 策略選擇
                    if selector:
                        market_state = selector.get_market_state(df)
                        strategy = selector.select_strategy(df)
                    else:
                        market_state = "trend_only"
                        strategy = trend_strategy
                    market_states[symbol] = market_state

                    # 計算指標
                    df = strategy.calculate_indicators(df)

                    # 高時間框架確認
                    if hasattr(strategy, "set_htf_data"):
                        df_htf = exchange.fetch_ohlcv(
                            symbol,
                            config.get("trend", {}).get("confirm_timeframe", "1h"),
                            100
                        )
                        if df_htf is not None:
                            strategy.set_htf_data(df_htf)

                    # 信號工程師：更新技術指標快照
                    try:
                        latest = df.iloc[-2]
                        company.signal_engineer.update_indicator_snapshot(symbol, {
                            "rsi": float(latest.get("rsi", 0) or 0),
                            "macd": float(latest.get("macd", 0) or 0),
                            "macd_signal": float(latest.get("macd_signal", 0) or 0),
                            "atr": float(latest.get("atr", 0) or 0),
                        })
                    except Exception:
                        pass

                    # 取得信號
                    signal = strategy.get_signal(df)

                    if signal:
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

                        # 信號工程師：記錄信號
                        company.record_signal(symbol, signal)

                        logger.info(
                            f"信號: {signal['side']} {symbol} | "
                            f"策略: {strategy.get_strategy_name()} | "
                            f"原因: {signal.get('reason', '')}"
                        )

                        # 風控檢查
                        if risk_manager.can_open_trade(
                            position_count, risk_status.get("daily_pnl", 0)
                        ):
                            if not exchange.has_position(symbol):
                                risk_pct = risk_manager.get_current_risk_pct()
                                sl_distance = abs(signal["entry"] - signal["stop_loss"])

                                if sl_distance > 0:
                                    # 實盤直接用當前帳戶餘額計算風險金額
                                    risk_amount = balance * risk_pct
                                    amount = risk_amount / sl_distance

                                    try:
                                        amount = float(exchange.exchange.amount_to_precision(symbol, amount))
                                    except Exception:
                                        pass

                                    notional = amount * signal["entry"]
                                    if notional < 5.5:
                                        logger.info(f"{symbol} 名義價值 {notional:.2f} < 5.5 USDT，跳過")
                                        continue

                                    order_side = "buy" if signal["side"] == "LONG" else "sell"

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
                                        actual_price = trade_result.get("price", signal["entry"])

                                        # 執行工程師：記錄執行品質
                                        company.execution_engineer.record_execution(
                                            symbol, signal["entry"], actual_price,
                                            signal["side"], success=True
                                        )

                                        notifier.notify_trade_open(
                                            symbol, signal["side"],
                                            signal["entry"], amount,
                                            sl_price, tp_price,
                                            strategy.get_strategy_name(),
                                        )

                except Exception as e:
                    logger.error(f"{symbol} 處理失敗: {e}")
                    # 執行工程師：記錄 API 錯誤
                    company.execution_engineer.record_api_error(symbol, type(e).__name__, str(e))

            # ========== 更新各部門狀態 ==========
            # 市場分析師：更新市場狀態
            company.update_market_states(market_states)

            # 風控官：快速預警檢查
            company.check_risk_alerts()

            # 量化研究員：同步最新績效
            company.sync_performance_to_researcher()

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
                    risk_manager._save_state()
                    side_label = "LONG" if trade["side"] == "buy" else "SHORT"
                    result_label = "win" if pnl > 0 else "loss"
                    actual_exit = exit_price

                    # 各部門更新交易結果
                    company.record_trade_result(
                        sym, trade["entry_price"], actual_exit,
                        side_label, pnl, result_label
                    )

                    notifier.notify_trade_close(sym, side_label, pnl, pnl_pct, "停損/停利觸發")
                    logger.info(f"倉位已關閉: {sym} | {side_label} | 盈虧: {pnl:+.2f} USDT")

            # ========== 觸發檔案檢查（手動測試用）==========
            trigger_report = Path("/tmp/trigger_report")
            trigger_research = Path("/tmp/trigger_research")
            if trigger_report.exists():
                try:
                    trigger_report.unlink()
                    logger.info("收到觸發信號，生成每日報告...")
                    company.send_daily_report()
                except Exception as e:
                    logger.error(f"觸發報告失敗: {e}")
            if trigger_research.exists():
                try:
                    trigger_research.unlink()
                    logger.info("收到觸發信號，啟動策略研究...")
                    import threading
                    threading.Thread(target=_run_research, args=(company,), daemon=True).start()
                except Exception as e:
                    logger.error(f"觸發策略研究失敗: {e}")

            # 更新儀表板
            dashboard.display_status(
                balance=balance,
                positions=positions,
                risk_status=risk_status,
                market_states=market_states,
                recent_signals=recent_signals,
            )

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
