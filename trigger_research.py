import sys
sys.path.insert(0, '/opt/trading-bot')
import yaml, logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

with open('/opt/trading-bot/config.yaml', 'r', encoding='utf-8-sig') as f:
    config = yaml.safe_load(f)

from notifications.telegram_bot import TelegramNotifier
from core.exchange import BinanceExchange
from core.risk_manager import RiskManager
from agents import TradingCompany

notifier = TelegramNotifier(config)
exchange = BinanceExchange(config)
risk_manager = RiskManager(config)

balance = exchange.get_balance()
risk_manager.current_balance = balance
risk_manager.peak_balance = balance

company = TradingCompany(config=config, exchange=exchange, notifier=notifier, risk_manager=risk_manager)

logger.info('=== 開始每日策略研究（多策略競賽）===')

# 步驟 1: 策略開發員選策略
today_strategies = company.strategy_developer.get_today_strategies()
logger.info(f'[策略開發員] 共 {len(today_strategies)} 個策略待競賽')

# 步驟 2: 回測工程師執行多策略競賽
multi_results = company.backtest_engineer.run_multi_strategy_backtest(today_strategies)

# 步驟 3: 更新評分
if multi_results:
    company.strategy_developer.update_scores(multi_results)

# 步驟 4: 基準回測
backtest_results = company.backtest_engineer.run_auto_backtest()
if backtest_results:
    perf = company.backtest_engineer.get_performance_summary()
    if perf:
        company.quant_researcher.update_performance(perf)

# 步驟 5: 生成報告
developer_report = company.strategy_developer.run()
backtest_report = company.backtest_engineer.run()
researcher_report = company.quant_researcher.run()

summary = (
    "=== 策略競賽結果 ===\n"
    + developer_report + "\n\n"
    + backtest_report + "\n\n"
    + researcher_report
)
company._send_long_message(summary)

# 步驟 6: 高分策略警報
best = company.strategy_developer.get_best_strategies(1)
if best:
    top = best[0]
    score = top.get('score', {})
    if score.get('composite_score', 0) > 0.65:
        alert = (
            "🔔 高分策略發現！\n"
            f"策略：{top['id']}\n"
            f"複合評分：{score['composite_score']:.3f}\n"
            f"勝率：{score['win_rate']:.1f}% | PF：{score['profit_factor']:.2f}"
        )
        company._send_long_message(alert)

logger.info('=== 策略競賽完成 ===')
