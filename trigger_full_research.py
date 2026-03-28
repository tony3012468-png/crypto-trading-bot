"""
全量策略競賽 - 運行所有未測試策略
"""
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

# 通知開始
company._send_long_message(
    "🏁 全量策略競賽開始\n"
    f"策略庫：{len(company.strategy_developer._strategy_library)} 個候選策略\n"
    "預計耗時：40-60 分鐘\n"
    "涵蓋：Trend / Bollinger / EMA Cross / SMC 全系列"
)

# 分批跑完所有未測試策略（每批20個）
all_strategies = company.strategy_developer._strategy_library.copy()
total = len(all_strategies)
batch_size = 20
all_results = {}

logger.info(f'全量策略競賽：共 {total} 個策略，每批 {batch_size} 個')

for batch_num, i in enumerate(range(0, total, batch_size), 1):
    batch = all_strategies[i:i+batch_size]
    logger.info(f'--- 第 {batch_num} 批：{len(batch)} 個策略 ---')

    batch_results = company.backtest_engineer.run_multi_strategy_backtest(batch)
    if batch_results:
        all_results.update(batch_results)
        company.strategy_developer.update_scores(batch_results)

    # 每批結束後發一個進度通知
    completed = min(i + batch_size, total)
    progress_msg = (
        f"📊 競賽進度：{completed}/{total}\n"
        f"本批完成：{len(batch_results) if batch_results else 0} 個\n"
    )
    if batch_results:
        # 本批最高分
        best_in_batch = max(batch_results.items(), key=lambda x: x[1].get('composite_score', 0))
        progress_msg += f"本批最高：{best_in_batch[0]}\n評分：{best_in_batch[1]['composite_score']:.3f} | 勝率：{best_in_batch[1]['win_rate']:.1f}% | PF：{best_in_batch[1]['profit_factor']:.2f}"
    company._send_long_message(progress_msg)

logger.info(f'全量回測完成，共 {len(all_results)} 個策略有結果')

# 生成最終排行榜
if all_results:
    ranked = sorted(all_results.items(), key=lambda x: x[1].get('composite_score', 0), reverse=True)

    # Top 10 排行榜
    top10_lines = ["🏆 全量策略競賽最終排行榜 Top 10\n" + "=" * 35]
    for rank, (sid, score) in enumerate(ranked[:10], 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
        line = (
            f"{medal} {sid}\n"
            f"   複合評分：{score['composite_score']:.3f} | 勝率：{score['win_rate']:.1f}%\n"
            f"   PF：{score['profit_factor']:.2f} | 夏普：{score['sharpe']:.2f} | 索提諾：{score['sortino']:.2f}\n"
            f"   最大回撤：{score['max_drawdown']:.1f}%"
        )
        top10_lines.append(line)

    company._send_long_message("\n\n".join(top10_lines))

    # 各策略類型勝者
    by_type = {}
    for sid, score in ranked:
        stype = sid.split('_')[0]
        if stype == 'bb':
            stype = 'bollinger'
        elif stype == 'ema':
            stype = 'ema_cross'
        elif stype == 'smc':
            stype = 'smc'
        else:
            stype = 'trend'
        if stype not in by_type:
            by_type[stype] = (sid, score)

    type_summary = ["📋 各策略類型最優代表：\n"]
    type_names = {'trend': '趨勢策略', 'bollinger': '布林通道', 'ema_cross': 'EMA 三線', 'smc': 'SMC 智慧資金'}
    for stype, (sid, score) in by_type.items():
        name = type_names.get(stype, stype)
        type_summary.append(
            f"【{name}】\n"
            f"  {sid}\n"
            f"  評分：{score['composite_score']:.3f} | 勝率：{score['win_rate']:.1f}% | PF：{score['profit_factor']:.2f}"
        )
    company._send_long_message("\n".join(type_summary))

    # 冠軍策略詳細分析
    champ_id, champ_score = ranked[0]
    champ_type = 'SMC' if champ_id.startswith('smc') else \
                 'EMA Cross' if champ_id.startswith('ema') else \
                 'Bollinger' if champ_id.startswith('bb') else 'Trend'

    champion_msg = (
        f"👑 冠軍策略完整分析\n"
        f"{'=' * 35}\n"
        f"策略：{champ_id}\n"
        f"類型：{champ_type}\n\n"
        f"📊 績效指標：\n"
        f"  複合評分：{champ_score['composite_score']:.3f}\n"
        f"  勝率：{champ_score['win_rate']:.1f}%\n"
        f"  獲利因子：{champ_score['profit_factor']:.2f}\n"
        f"  夏普比率：{champ_score['sharpe']:.2f}\n"
        f"  索提諾比率：{champ_score['sortino']:.2f}\n"
        f"  最大回撤：{champ_score['max_drawdown']:.1f}%\n\n"
        f"📈 評估：\n"
    )

    cs = champ_score['composite_score']
    wr = champ_score['win_rate']
    pf = champ_score['profit_factor']
    dd = champ_score['max_drawdown']

    if cs >= 0.65:
        champion_msg += "  🔥 達到採用門檻（0.65+），強烈建議切換實盤！\n"
    elif cs >= 0.5:
        champion_msg += "  ✅ 表現良好，建議繼續觀察 2-3 天確認穩定性後再切換\n"
    else:
        champion_msg += "  ⚠️ 尚未達到切換門檻，繼續累積測試數據\n"

    if dd > 30:
        champion_msg += f"  ⚠️ 回撤 {dd:.1f}% 偏高，實盤需注意風控\n"
    if wr >= 55 and pf >= 1.5:
        champion_msg += "  💪 高勝率 + 高 PF，策略品質優秀\n"

    company._send_long_message(champion_msg)

    # 淘汰統計
    eliminated = [sid for sid, score in all_results.items() if score.get('composite_score', 1) < 0.2]
    logger.info(f'本次競賽淘汰 {len(eliminated)} 個低分策略')

logger.info('=== 全量策略競賽完成 ===')
