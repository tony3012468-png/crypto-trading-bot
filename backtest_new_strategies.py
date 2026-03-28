"""
新策略競賽回測
測試 Bollinger + EMA Cross 多種參數組合
目標：找到 PF > 1.5、勝率 > 55%、回撤 < 35% 的策略
（低風險設定：1% 單筆風險、最多 1 倉）
"""
import sys
import logging
import yaml
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

logging.basicConfig(level=logging.WARNING)

from backtest.backtester import Backtester
from notifications.telegram_bot import TelegramNotifier

# ── 候選策略定義 ─────────────────────────────────────────
CANDIDATES = []

# === Bollinger 策略組合 ===
for bb_std in [2.0, 2.5]:
    for rsi_os, rsi_ob in [(30, 70), (35, 65)]:
        for sl, tp in [(1.5, 2.5), (2.0, 3.0), (1.5, 3.0)]:
            sid = f"bb_std{bb_std}_rsi{rsi_ob}_{rsi_os}_sl{sl}_tp{tp}"
            CANDIDATES.append({
                "type": "bollinger",
                "id": sid,
                "params": {
                    "bb_period": 20,
                    "bb_std": bb_std,
                    "rsi_oversold": rsi_os,
                    "rsi_overbought": rsi_ob,
                    "atr_sl_multiplier": sl,
                    "atr_tp_multiplier": tp,
                    "volume_filter": True,
                },
            })

# === EMA Cross 策略組合 ===
for mid, lng in [(21, 55), (26, 100)]:
    for sl, tp in [(1.5, 2.5), (2.0, 3.0)]:
        sid = f"emacross_9_{mid}_{lng}_sl{sl}_tp{tp}"
        CANDIDATES.append({
            "type": "ema_cross",
            "id": sid,
            "params": {
                "ema_short": 9,
                "ema_mid": mid,
                "ema_long": lng,
                "rsi_min": 45,
                "rsi_max": 55,
                "atr_sl_multiplier": sl,
                "atr_tp_multiplier": tp,
                "volume_filter": True,
            },
        })

# === 對照組：冠軍 Trend 策略（低風險版） ===
CANDIDATES.append({
    "type": "trend",
    "id": "trend_champion_f10_s30_sl2.0_tp3.0（對照）",
    "params": {
        "fast_ema": 10, "slow_ema": 30, "signal_ema": 9,
        "rsi_overbought": 60, "rsi_oversold": 40,
        "atr_sl_multiplier": 2.0, "atr_tp_multiplier": 3.0,
    },
})

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
CANDLE_LIMIT_15M = 5760   # 60 days
CANDLE_LIMIT_1H  = 1440


def build_strategy(stype, params, config):
    from strategies.trend_strategy import TrendStrategy
    from strategies.bollinger_strategy import BollingerStrategy
    from strategies.ema_cross_strategy import EMACrossStrategy
    if stype == "trend":
        merged = dict(config)
        merged["trend"] = params
        return TrendStrategy(merged)
    elif stype == "bollinger":
        return BollingerStrategy(config, params)
    elif stype == "ema_cross":
        return EMACrossStrategy(config, params)
    return None


def get_public_exchange():
    """建立不需要 API key 的公開 ccxt 連線（僅用於抓歷史 K 線）"""
    import ccxt
    return ccxt.binanceusdm({
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
    })


def fetch_ohlcv_long(exchange, symbol, timeframe, total_limit):
    """分批拉取超過 1000 根的 K 線"""
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
            import pandas as pd
            df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            all_dfs.insert(0, df)
            end_time = raw[0][0] - 1
            remaining -= len(raw)
            if len(raw) < batch:
                break
            _time.sleep(0.2)
        except Exception as e:
            print(f"    批次拉取失敗: {e}")
            break
    if not all_dfs:
        return None
    import pandas as pd
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
    research_config["risk"]["risk_per_trade"] = 0.01   # 1% 單筆風險
    research_config["risk"]["max_open_positions"] = 1  # 最多 1 倉
    backtester = Backtester(research_config)

    print(f"共 {len(CANDIDATES)} 個候選策略")
    print("分批抓取 60 天 K 線數據...")
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

    results = {}

    for candidate in CANDIDATES:
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
                print(f"  {symbol}: {trades}筆 | 勝率{wr:.0f}% | PF{pf:.2f} | 回撤{dd:.0f}%")
            except Exception as e:
                print(f"  {symbol} 回測失敗: {e}")

    # 彙整
    summary = []
    for candidate in CANDIDATES:
        sid = candidate["id"]
        if sid not in results or not results[sid]:
            continue
        pair_results = list(results[sid].values())
        if not pair_results:
            continue
        avg_wr  = sum(getattr(r, "win_rate", 0) for r in pair_results) / len(pair_results)
        avg_pf  = sum(getattr(r, "profit_factor", 0) for r in pair_results) / len(pair_results)
        avg_dd  = sum(getattr(r, "max_drawdown_pct", 0) for r in pair_results) / len(pair_results)
        total_trades = sum(len(getattr(r, "trades", [])) for r in pair_results)
        summary.append({
            "type": candidate["type"],
            "id": sid,
            "avg_wr": avg_wr,
            "avg_pf": avg_pf,
            "avg_dd": avg_dd,
            "total_trades": total_trades,
        })

    # 依目標排序：PF*勝率為主，回撤為次
    summary.sort(key=lambda x: (-(x["avg_pf"] * x["avg_wr"] / 100), x["avg_dd"]))

    # 組報告
    lines = [
        "🔬 新策略競賽回測（低風險版：1%/筆、最多1倉）",
        "=" * 40,
        f"候選策略: {len(CANDIDATES)} 個 | 交易對: {len(SYMBOLS)} 個",
        "",
    ]

    # 達標策略（PF>1.5 & WR>55% & DD<35%）
    qualified = [s for s in summary if s["avg_pf"] > 1.5 and s["avg_wr"] > 55 and s["avg_dd"] < 35]
    lines.append(f"✅ 達標策略（PF>1.5 & 勝率>55% & 回撤<35%）：{len(qualified)} 個")
    lines.append("")

    for i, s in enumerate(summary[:15], 1):  # 只顯示前 15
        if s["avg_pf"] > 1.5 and s["avg_wr"] > 55 and s["avg_dd"] < 35:
            marker = "✅"
        elif s["avg_pf"] > 1.2 and s["avg_dd"] < 40:
            marker = "⚠️"
        else:
            marker = "❌"
        lines.append(
            f"{marker} #{i} [{s['type']}]\n"
            f"   {s['id']}\n"
            f"   交易:{s['total_trades']}筆 | 勝率:{s['avg_wr']:.1f}% | PF:{s['avg_pf']:.2f} | 回撤:{s['avg_dd']:.1f}%"
        )

    lines.append("")
    if qualified:
        best = qualified[0]
        lines.append(f"🏆 最佳新策略：{best['id']}")
        lines.append(f"   PF:{best['avg_pf']:.2f} | 勝率:{best['avg_wr']:.1f}% | 回撤:{best['avg_dd']:.1f}%")
    else:
        lines.append("⚠️ 暫無策略達到三項指標全部達標，建議繼續優化參數")

    msg = "\n".join(lines)
    print("\n" + msg)

    try:
        notifier.send_message(msg)
        print("\n[Telegram] 已發送")
    except Exception as e:
        print(f"\n[Telegram] 發送失敗: {e}")


if __name__ == "__main__":
    main()
