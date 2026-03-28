"""
策略開發員 (Strategy Developer)

職責：
- 每天自動生成 N 種策略組合（指標參數矩陣 + 不同策略類型）
- 管理策略候選庫，記錄每個策略的歷史績效
- 根據市場條件推薦當日最值得回測的策略
- 淘汰長期表現差的策略，持續引入新組合
"""

import json
import logging
import itertools
from datetime import datetime
from pathlib import Path
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

SCORES_FILE = Path(__file__).parent.parent / "data" / "strategy_scores.json"


class StrategyDeveloper(BaseAgent):
    """策略開發員 - 自動生成與管理策略組合"""

    name = "策略開發員"
    role = "策略研發、參數矩陣生成、候選策略管理、績效追蹤與淘汰"
    emoji = "🧪"

    # 每日回測的策略數量上限
    DAILY_STRATEGY_LIMIT = 20   # 每次選 20 個跑回測（避免 API 過載）
    MAX_LIBRARY_SIZE = 200       # 策略庫最大容量

    def __init__(self, config: dict, exchange=None, notifier=None):
        super().__init__(config, exchange, notifier)
        self._strategy_library: list[dict] = []   # 所有候選策略
        self._strategy_scores: dict[str, dict] = {}  # {strategy_id: {score, win_rate, ...}}
        self._generation: int = 0   # 第幾次生成

        # 初始化策略庫
        self._build_strategy_library()

        # 從磁碟載入歷史競賽分數（跨進程、跨重啟保留）
        self._load_scores()

    # ──────────────────────────────────────────────
    # 策略庫建立
    # ──────────────────────────────────────────────

    def _build_strategy_library(self):
        """建立初始策略庫（三種策略 × 參數矩陣）"""
        self._strategy_library = []

        # 1. TrendStrategy 參數矩陣
        self._strategy_library += self._gen_trend_variants()

        # 2. BollingerStrategy 參數矩陣
        self._strategy_library += self._gen_bollinger_variants()

        # 3. EMACrossStrategy 參數矩陣
        self._strategy_library += self._gen_ema_cross_variants()

        # 4. SMCStrategy 參數矩陣
        self._strategy_library += self._gen_smc_variants()

        logger.info(f"[策略開發員] 策略庫初始化完成，共 {len(self._strategy_library)} 個候選策略")

    def _gen_trend_variants(self) -> list[dict]:
        """TrendStrategy 參數組合"""
        variants = []
        for fast, slow, signal in [(8, 21, 9), (12, 26, 9), (10, 30, 9), (5, 13, 5)]:
            for rsi_ob, rsi_os in [(65, 35), (70, 30), (60, 40)]:
                for atr_sl, atr_tp in [(1.5, 2.5), (1.8, 2.5), (2.0, 3.0)]:
                    variants.append({
                        "type": "trend",
                        "id": f"trend_f{fast}_s{slow}_rsi{rsi_ob}_{rsi_os}_sl{atr_sl}_tp{atr_tp}",
                        "params": {
                            "fast_ema": fast, "slow_ema": slow, "signal_ema": signal,
                            "rsi_overbought": rsi_ob, "rsi_oversold": rsi_os,
                            "atr_sl_multiplier": atr_sl, "atr_tp_multiplier": atr_tp,
                        }
                    })
        return variants

    def _gen_bollinger_variants(self) -> list[dict]:
        """BollingerStrategy 參數組合"""
        variants = []
        for period in [15, 20, 25]:
            for std in [1.8, 2.0, 2.5]:
                for rsi_ob, rsi_os in [(65, 35), (70, 30)]:
                    for atr_sl, atr_tp in [(1.2, 2.0), (1.5, 2.5)]:
                        variants.append({
                            "type": "bollinger",
                            "id": f"bb_p{period}_std{std}_rsi{rsi_ob}_{rsi_os}_sl{atr_sl}_tp{atr_tp}",
                            "params": {
                                "bb_period": period, "bb_std": std,
                                "rsi_overbought": rsi_ob, "rsi_oversold": rsi_os,
                                "atr_sl_multiplier": atr_sl, "atr_tp_multiplier": atr_tp,
                            }
                        })
        return variants

    def _gen_ema_cross_variants(self) -> list[dict]:
        """EMACrossStrategy 參數組合"""
        variants = []
        ema_combos = [(5, 13, 34), (8, 21, 55), (9, 21, 50), (10, 30, 60)]
        for s, m, l in ema_combos:
            for atr_sl, atr_tp in [(1.3, 2.0), (1.5, 2.5), (2.0, 3.0)]:
                variants.append({
                    "type": "ema_cross",
                    "id": f"ema_{s}_{m}_{l}_sl{atr_sl}_tp{atr_tp}",
                    "params": {
                        "ema_short": s, "ema_mid": m, "ema_long": l,
                        "atr_sl_multiplier": atr_sl, "atr_tp_multiplier": atr_tp,
                    }
                })
        return variants

    def _gen_smc_variants(self) -> list[dict]:
        """SMCStrategy 參數組合"""
        variants = []
        for swing in [8, 10, 15]:
            for ob in [3, 5, 7]:
                for atr_tp in [2.5, 3.0, 4.0]:
                    variants.append({
                        "type": "smc",
                        "id": f"smc_sw{swing}_ob{ob}_tp{atr_tp}",
                        "params": {
                            "swing_lookback": swing,
                            "ob_lookback": ob,
                            "atr_tp_multiplier": atr_tp,
                        }
                    })
        return variants

    # ──────────────────────────────────────────────
    # 每日選策略
    # ──────────────────────────────────────────────

    def get_today_strategies(self) -> list[dict]:
        """
        選出今日要回測的策略清單。
        邏輯：
        1. 未測試過的策略優先（探索）
        2. 有成績但近期未複測的策略（驗證）
        3. 隨機抽樣確保覆蓋多樣性
        """
        import random

        untested = [s for s in self._strategy_library if s["id"] not in self._strategy_scores]
        tested = [s for s in self._strategy_library if s["id"] in self._strategy_scores]

        selected = []

        # 70% 選未測試的（探索）
        explore_n = int(self.DAILY_STRATEGY_LIMIT * 0.7)
        if untested:
            selected += random.sample(untested, min(explore_n, len(untested)))

        # 30% 選已測試中評分較高的（驗證/複測）
        exploit_n = self.DAILY_STRATEGY_LIMIT - len(selected)
        if tested and exploit_n > 0:
            tested_sorted = sorted(
                tested,
                key=lambda s: self._strategy_scores.get(s["id"], {}).get("composite_score", 0),
                reverse=True
            )
            selected += tested_sorted[:exploit_n]

        self._generation += 1
        logger.info(f"[策略開發員] 第 {self._generation} 輪：選出 {len(selected)} 個策略待回測")
        return selected[:self.DAILY_STRATEGY_LIMIT]

    def update_scores(self, results: dict):
        """
        接收回測結果，更新策略評分。

        Args:
            results: {strategy_id: {"win_rate", "profit_factor", "sharpe",
                                    "sortino", "max_drawdown", "composite_score"}}
        """
        self._strategy_scores.update(results)

        # 淘汰長期墊底的策略（複合評分 < 0.3 且已有足夠樣本）
        to_remove = []
        for sid, score in self._strategy_scores.items():
            if score.get("composite_score", 1.0) < 0.2 and score.get("total_trades", 0) >= 5:
                to_remove.append(sid)

        for sid in to_remove:
            self._strategy_library = [s for s in self._strategy_library if s["id"] != sid]
            del self._strategy_scores[sid]

        if to_remove:
            logger.info(f"[策略開發員] 淘汰 {len(to_remove)} 個低分策略")

        # 每次更新後立即存檔，確保崩潰或重啟不遺失結果
        self._save_scores()

    def _save_scores(self):
        """將競賽分數存入磁碟"""
        try:
            SCORES_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "saved_at": datetime.now().isoformat(),
                "total_tested": len(self._strategy_scores),
                "scores": self._strategy_scores,
            }
            SCORES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.debug(f"[策略開發員] 已存檔 {len(self._strategy_scores)} 個策略分數")
        except Exception as e:
            logger.warning(f"[策略開發員] 存檔失敗: {e}")

    def _load_scores(self):
        """從磁碟載入歷史競賽分數"""
        try:
            if SCORES_FILE.exists():
                data = json.loads(SCORES_FILE.read_text(encoding="utf-8"))
                self._strategy_scores = data.get("scores", {})
                saved_at = data.get("saved_at", "unknown")
                logger.info(f"[策略開發員] 載入歷史分數：{len(self._strategy_scores)} 個策略，存檔於 {saved_at}")
        except Exception as e:
            logger.warning(f"[策略開發員] 載入歷史分數失敗: {e}")

    def get_best_strategies(self, top_n: int = 5) -> list[dict]:
        """取得目前評分最高的前 N 個策略"""
        scored = [
            (sid, data) for sid, data in self._strategy_scores.items()
            if data.get("total_trades", 0) >= 3
        ]
        scored.sort(key=lambda x: x[1].get("composite_score", 0), reverse=True)

        best = []
        for sid, score_data in scored[:top_n]:
            strategy = next((s for s in self._strategy_library if s["id"] == sid), None)
            if strategy:
                best.append({**strategy, "score": score_data})
        return best

    # ──────────────────────────────────────────────
    # BaseAgent 必要方法
    # ──────────────────────────────────────────────

    def analyze(self) -> dict:
        tested_count = len(self._strategy_scores)
        untested_count = len(self._strategy_library) - tested_count
        best = self.get_best_strategies(3)

        type_dist = {}
        for s in self._strategy_library:
            type_dist[s["type"]] = type_dist.get(s["type"], 0) + 1

        return {
            "generation": self._generation,
            "library_size": len(self._strategy_library),
            "tested": tested_count,
            "untested": untested_count,
            "type_distribution": type_dist,
            "best_strategies": best,
        }

    def generate_report(self) -> str:
        data = self._last_analysis
        lines = [
            f"{self.emoji} 策略開發員報告 | {self._now_str()}",
            "-" * 35,
            f"策略庫總量：{data['library_size']} 個",
            f"已回測：{data['tested']} 個 | 待回測：{data['untested']} 個",
            f"第 {data['generation']} 輪研究",
            "",
            "策略類型分布：",
        ]
        for t, n in data.get("type_distribution", {}).items():
            lines.append(f"  {t}: {n} 個")

        best = data.get("best_strategies", [])
        if best:
            lines.append("\n目前評分最佳策略 Top 3：")
            for i, s in enumerate(best, 1):
                score = s.get("score", {})
                lines.append(
                    f"  #{i} {s['id']}\n"
                    f"      複合分={score.get('composite_score', 0):.3f} | "
                    f"勝率={score.get('win_rate', 0):.1f}% | "
                    f"PF={score.get('profit_factor', 0):.2f} | "
                    f"夏普={score.get('sharpe', 0):.2f}"
                )
        else:
            lines.append("\n尚無完整評分策略，持續回測中...")

        return "\n".join(lines)
