"""
Top 10 策略 × 30天有效回測
抓 60 天原始數據，確保指標暖身後仍有 30 天有效交易期
"""
import sys
import logging
import yaml
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

logging.basicConfig(level=logging.WARNING)  # 只顯示警告，避免 log 太多

from backtest.backtester import Backtester
from notifications.telegram_bot import TelegramNotifier

# ── Top 10 策略定義 ───────────────────────────────────────────
TOP10 = [
    {"rank": 1,  "type": "trend", "id": "trend_f10_s30_rsi60_40_sl2.0_tp3.0",
     "params": {"fast_ema":10,"slow_ema":30,"signal_ema":9,"rsi_overbought":60,"rsi_oversold":40,"atr_sl_multiplier":2.0,"atr_tp_multiplier":3.0}},
    {"rank": 2,  "type": "trend", "id": "trend_f10_s30_rsi60_40_sl1.5_tp2.5",
     "params": {"fast_ema":10,"slow_ema":30,"signal_ema":9,"rsi_overbought":60,"rsi_oversold":40,"atr_sl_multiplier":1.5,"atr_tp_multiplier":2.5}},
    {"rank": 3,  "type": "trend", "id": "trend_f10_s30_rsi60_40_sl1.8_tp2.5",
     "params": {"fast_ema":10,"slow_ema":30,"signal_ema":9,"rsi_overbought":60,"rsi_oversold":40,"atr_sl_multiplier":1.8,"atr_tp_multiplier":2.5}},
    {"rank": 4,  "type": "trend", "id": "trend_f8_s21_rsi60_40_sl1.8_tp2.5",
     "params": {"fast_ema":8,"slow_ema":21,"signal_ema":9,"rsi_overbought":60,"rsi_oversold":40,"atr_sl_multiplier":1.8,"atr_tp_multiplier":2.5}},
    {"rank": 5,  "type": "trend", "id": "trend_f8_s21_rsi60_40_sl2.0_tp3.0",
     "params": {"fast_ema":8,"slow_ema":21,"signal_ema":9,"rsi_overbought":60,"rsi_oversold":40,"atr_sl_multiplier":2.0,"atr_tp_multiplier":3.0}},
    {"rank": 6,  "type": "trend", "id": "trend_f8_s21_rsi60_40_sl1.5_tp2.5",
     "params": {"fast_ema":8,"slow_ema":21,"signal_ema":9,"rsi_overbought":60,"rsi_oversold":40,"atr_sl_multiplier":1.5,"atr_tp_multiplier":2.5}},
    {"rank": 7,  "type": "trend", "id": "trend_f12_s26_rsi60_40_sl2.0_tp3.0",
     "params": {"fast_ema":12,"slow_ema":26,"signal_ema":9,"rsi_overbought":60,"rsi_oversold":40,"atr_sl_multiplier":2.0,"atr_tp_multiplier":3.0}},
    {"rank": 8,  "type": "trend", "id": "trend_f12_s26_rsi60_40_sl1.5_tp2.5",
     "params": {"fast_ema":12,"slow_ema":26,"signal_ema":9,"rsi_overbought":60,"rsi_oversold":40,"atr_sl_multiplier":1.5,"atr_tp_multiplier":2.5}},
    {"rank": 9,  "type": "trend", "id": "trend_f12_s26_rsi60_40_sl1.8_tp2.5",
     "params": {"fast_ema":12,"slow_ema":26,"signal_ema":9,"rsi_overbought":60,"rsi_oversold":40,"atr_sl_multiplier":1.8,"atr_tp_multiplier":2.5}},
    {"rank": 10, "type": "smc",   "id": "smc_sw8_ob7_tp2.5",
     "params": {"swing_period":8,"ob_lookback":7,"atr_tp_multiplier":2.5}},
    # 對照組：現行實盤策略
    {"rank": 0,  "type": "trend", "id": "trend_f12_s26_rsi70_30_sl1.8_tp2.5 (現行實盤)",
     "params": {"fast_ema":12,"slow_ema":26,"signal_ema":9,"rsi_overbought":70,"rsi_oversold":30,"atr_sl_multiplier":1.8,"atr_tp_multiplier":2.5}},
]

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
# 抓 60 天 K 線確保 30 天有效回測（指標暖身消耗約一半）
CANDLE_LIMIT_15M = 5760   # 60 days × 24h × 4 = 5760
CANDLE_LIMIT_1H  = 1440   # 60 days × 24h

def build_strategy(stype, params, config):
    from strategies.trend_strategy import TrendStrategy
    from strategies.smc_strategy import SMCStrategy
    if stype == "trend":
        merged = dict(config)
        merged["trend"] = params
        return TrendStrategy(merged)
    elif stype == "smc":
        return SMCStrategy(config, params)
    return None

def get_public_exchange():
    """建立不需要 API key 的公開 ccxt 連線（僅用於抓歷史 K 線）"""
    import ccxt
    return ccxt.binanceusdm({
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
    })


def fetch_ohlcv_long(exchange, symbol, timeframe, total_limit):
    """分批拉取超過 1000 根的 K 線（幣安每次最多 1000）"""
    import time as _time
    import pandas as pd
    all_dfs = []
    remaining = total_limit
    end_time = None
    while remaining > 0:
        batch = min(remaining, 1000)
        try:
            ex = exchange
            kwargs = {"symbol": symbol, "timeframe": timeframe, "limit": batch}
            if end_time:
                kwargs["params"] = {"endTime": end_time}
            raw = ex.fetch_ohlcv(**kwargs)
            if not raw:
                break
            df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            all_dfs.insert(0, df)
            end_time = raw[0][0] - 1  # 往前繼續抓
            remaining -= len(raw)
            if len(raw) < batch:
                break
            _time.sleep(0.2)
        except Exception as e:
            print(f"    批次拉取失敗: {e}")
            break
    if not all_dfs:
        return None
    result = pd.concat(all_dfs).drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    return result

def main():
    config = yaml.safe_load(open(PROJECT_DIR / "config.yaml", encoding="utf-8"))
    exchange = get_public_exchange()   # 不需要 API key，僅用於抓公開 K 線
    notifier = TelegramNotifier(config)

    research_config = dict(config)
    research_config["account"] = dict(config.get("account", {}))
    research_config["account"]["total_capital"] = 500.0
    research_config["risk"] = dict(config.get("risk", {}))
    research_config["risk"]["risk_per_trade"] = 0.01   # 降低單筆風險：2% → 1%
    research_config["risk"]["max_open_positions"] = 1  # 降低同時持倉：2 → 1
    backtester = Backtester(research_config)

    print("分批抓取 60 天 K 線數據（確保 30 天有效回測）...")
    ohlcv_cache = {}
    for symbol in SYMBOLS:
        try:
            df = fetch_ohlcv_long(exchange, symbol, "15m", CANDLE_LIMIT_15M)
            df_htf = fetch_ohlcv_long(exchange, symbol, "1h", CANDLE_LIMIT_1H)
            if df is not None and len(df) >= 200:
                ohlcv_cache[symbol] = (df, df_htf)
                print(f"  {symbol}: {len(df)} 根 15m K 線")
        except Exception as e:
            print(f"  {symbol} 失敗: {e}")

    results = {}  # {strategy_id: {symbol: result}}

    for candidate in TOP10:
        sid = candidate["id"]
        print(f"\n回測 {sid}...")
        strategy = build_strategy(candidate["type"], candidate["params"], config)
        if strategy is None:
            continue
        results[sid] = {}
        for symbol in SYMBOLS:
            if symbol not in ohlcv_cache:
                continue
            df, df_htf = ohlcv_cache[symbol]
            try:
                result = backtester.run(strategy, df, symbol, "15m", df_htf=df_htf)
                results[sid][symbol] = result
                trades = len(result.trades) if hasattr(result, "trades") else 0
                wr = result.win_rate if hasattr(result, "win_rate") else 0
                pf = result.profit_factor if hasattr(result, "profit_factor") else 0
                dd = result.max_drawdown_pct if hasattr(result, "max_drawdown_pct") else 0
                days = result.period_days if hasattr(result, "period_days") else "?"
                print(f"  {symbol}: {days}天 | {trades}筆 | 勝率{wr:.0f}% | PF{pf:.2f} | 回撤{dd:.0f}%")
            except Exception as e:
                print(f"  {symbol} 回測失敗: {e}")

    # 彙整報告
    summary = []
    for candidate in TOP10:
        sid = candidate["id"]
        if sid not in results or not results[sid]:
            continue
        pair_results = list(results[sid].values())
        avg_wr  = sum(getattr(r, "win_rate", 0) for r in pair_results) / len(pair_results)
        avg_pf  = sum(getattr(r, "profit_factor", 0) for r in pair_results) / len(pair_results)
        avg_dd  = sum(getattr(r, "max_drawdown_pct", 0) for r in pair_results) / len(pair_results)
        avg_days = sum(getattr(r, "period_days", 0) for r in pair_results) / len(pair_results)
        total_trades = sum(len(getattr(r, "trades", [])) for r in pair_results)
        summary.append({
            "rank": candidate["rank"],
            "id": sid,
            "avg_wr": avg_wr,
            "avg_pf": avg_pf,
            "avg_dd": avg_dd,
            "avg_days": avg_days,
            "total_trades": total_trades,
        })

    summary.sort(key=lambda x: (-(x["avg_pf"] * x["avg_wr"] / 100), x["avg_dd"]))

    # 組 Telegram 訊息
    lines = ["📊 Top 10 策略 × 30天 回測報告（低風險版：1%/筆、最多1倉）", "=" * 35, ""]
    for i, s in enumerate(summary, 1):
        rank_tag = f"[原#{s['rank']}]" if s["rank"] > 0 else "[現行實盤]"
        marker = "✅" if s["avg_pf"] > 1.5 and s["avg_wr"] > 55 and s["avg_dd"] < 35 else "⚠️" if s["avg_pf"] > 1.2 else "❌"
        lines.append(
            f"{marker} #{i} {rank_tag}\n"
            f"   {s['id']}\n"
            f"   有效天數:{s['avg_days']:.0f}天 | 交易:{s['total_trades']}筆\n"
            f"   勝率:{s['avg_wr']:.1f}% | PF:{s['avg_pf']:.2f} | 回撤:{s['avg_dd']:.1f}%"
        )

    # 與 10 天結果比較
    lines += ["", "📌 結論："]
    top = summary[0]
    if top["avg_pf"] > 1.5 and top["avg_wr"] > 55:
        lines.append(f"✅ 30天數據確認 {top['id']} 穩定，建議切換")
    elif top["avg_pf"] > 1.2:
        lines.append(f"⚠️ 30天表現下滑，10天結果可能有過擬合，建議繼續觀察")
    else:
        lines.append(f"❌ 30天數據顯示策略不穩定，維持現行策略")

    msg = "\n".join(lines)
    print("\n" + msg)

    try:
        notifier.send_message(msg)
        print("\n[Telegram] 已發送")
    except Exception as e:
        print(f"\n[Telegram] 發送失敗: {e}")

if __name__ == "__main__":
    main()
