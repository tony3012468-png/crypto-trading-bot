"""從幣安拉取期貨歷史（嘗試多種方式）"""
import sys
sys.path.insert(0, '/opt/trading-bot')
import yaml
from datetime import datetime, timedelta

with open('/opt/trading-bot/config.yaml', 'r', encoding='utf-8-sig') as f:
    config = yaml.safe_load(f)

from core.exchange import BinanceExchange
exchange = BinanceExchange(config)
ex = exchange.exchange

since_ms = int((datetime.now() - timedelta(days=60)).timestamp() * 1000)

# 方法 1: 期貨收益紀錄（最完整）
print('=== 方法1: fapiPrivateGetIncome (期貨收益) ===')
try:
    income = ex.fapiPrivateGetIncome({
        'incomeType': 'REALIZED_PNL',
        'limit': 200,
        'startTime': since_ms,
    })
    print(f'已實現盈虧紀錄：{len(income)} 筆')
    total = 0
    for item in income:
        dt = datetime.fromtimestamp(int(item['time'])/1000).strftime('%m/%d %H:%M')
        sym = item['symbol'].replace('USDT', '')
        val = float(item['income'])
        total += val
        print(f'  {dt} | {sym:10s} | {val:+.4f} USDT')
    print(f'合計已實現盈虧: {total:+.4f} USDT')
except Exception as e:
    print(f'Error: {e}')

# 方法 2: 手續費
print('\n=== 方法2: 手續費紀錄 ===')
try:
    fees = ex.fapiPrivateGetIncome({
        'incomeType': 'COMMISSION',
        'limit': 200,
        'startTime': since_ms,
    })
    total_fee = sum(float(f['income']) for f in fees)
    print(f'手續費筆數: {len(fees)}, 合計: {total_fee:.4f} USDT')
except Exception as e:
    print(f'Error: {e}')

# 方法 3: 帳戶資訊
print('\n=== 方法3: 帳戶資訊 ===')
try:
    account = ex.fapiPrivateGetAccount()
    print(f"總錢包餘額: {account.get('totalWalletBalance', '?')} USDT")
    print(f"總未實現盈虧: {account.get('totalUnrealizedProfit', '?')} USDT")
    print(f"總保證金餘額: {account.get('totalMarginBalance', '?')} USDT")
    print(f"總維持保證金: {account.get('totalMaintMargin', '?')} USDT")
    assets = [a for a in account.get('assets', []) if float(a.get('walletBalance', 0)) != 0]
    for a in assets:
        print(f"  {a['asset']}: 餘額={a['walletBalance']}, 未實現={a['unrealizedProfit']}")
except Exception as e:
    print(f'Error: {e}')

# 方法 4: 成交紀錄（指定交易對）
print('\n=== 方法4: 所有交易對成交紀錄 ===')
try:
    # 取得所有有過交易的交易對（從 24h 統計推斷）
    all_trades_total = 0
    # 嘗試不帶 symbol 的 userTrades
    result = ex.fapiPrivateGetUserTrades({'limit': 200, 'startTime': since_ms})
    print(f'不帶symbol的userTrades: {len(result)} 筆')
    all_trades_total += len(result)
except Exception as e:
    print(f'Error: {e}')
