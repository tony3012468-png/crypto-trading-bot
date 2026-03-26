"""
動態交易對選擇器 - 每日自動篩選前 N 名成交量的幣種
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 排除的幣種（穩定幣、特殊代幣等不適合交易的）
EXCLUDED_SYMBOLS = {
    # 穩定幣
    "USDC/USDT:USDT",
    "BUSD/USDT:USDT",
    "TUSD/USDT:USDT",
    "FDUSD/USDT:USDT",
    "DAI/USDT:USDT",
    "USDP/USDT:USDT",
    # 貴金屬（走勢與加密貨幣不同，策略不適用）
    "XAU/USDT:USDT",
    "XAG/USDT:USDT",
    "PAXG/USDT:USDT",
}

# 最低 24h 成交量門檻（USDT）
MIN_VOLUME_USDT = 50_000_000  # 5000 萬 USDT

# 最大 24h 漲跌幅（超過此值的幣種視為異常波動，排除）
MAX_CHANGE_PCT = 50.0


class PairSelector:
    """動態交易對選擇器"""

    def __init__(self, exchange, config: dict):
        """
        初始化

        Args:
            exchange: BinanceExchange 實例
            config: 設定檔字典
        """
        self.exchange = exchange
        self.top_n = config.get("pair_selector", {}).get("top_n", 20)
        self.min_volume = config.get("pair_selector", {}).get("min_volume_usdt", MIN_VOLUME_USDT)
        self.max_change = config.get("pair_selector", {}).get("max_change_pct", MAX_CHANGE_PCT)
        self.exclude = EXCLUDED_SYMBOLS
        # 可以在 config 中指定必須包含的幣種
        self.always_include = set(config.get("pair_selector", {}).get("always_include", []))
        self._cached_pairs: list[str] = []

    def get_top_volume_pairs(self, top_n: Optional[int] = None) -> list[str]:
        """
        取得前 N 名 24h 成交量的 USDT 永續合約交易對

        Args:
            top_n: 取前幾名（預設用 config 設定）

        Returns:
            交易對列表，如 ["BTC/USDT:USDT", "ETH/USDT:USDT", ...]
        """
        if top_n is None:
            top_n = self.top_n

        try:
            # 取得所有交易對的 24h 行情
            tickers = self.exchange.exchange.fetch_tickers()

            # 篩選 USDT 永續合約
            usdt_futures = []
            for symbol, ticker in tickers.items():
                # 只要 USDT 永續合約
                if not symbol.endswith(":USDT"):
                    continue
                # 排除穩定幣等
                if symbol in self.exclude:
                    continue
                # 取得 24h 成交量（以 USDT 計）
                quote_volume = ticker.get("quoteVolume", 0) or 0
                if quote_volume < self.min_volume:
                    continue
                # 排除異常波動的幣種（24h 漲跌幅超過門檻）
                change_pct = abs(ticker.get("percentage", 0) or 0)
                if change_pct > self.max_change:
                    logger.info(f"  排除 {symbol}（24h 漲跌 {change_pct:.1f}% 超過 {self.max_change}%）")
                    continue

                usdt_futures.append({
                    "symbol": symbol,
                    "volume": quote_volume,
                    "last": ticker.get("last", 0),
                    "change": ticker.get("percentage", 0),
                })

            # 按成交量排序
            usdt_futures.sort(key=lambda x: x["volume"], reverse=True)

            # 取前 N 名
            top_pairs = [item["symbol"] for item in usdt_futures[:top_n]]

            # 加入必須包含的幣種
            for pair in self.always_include:
                if pair not in top_pairs:
                    top_pairs.append(pair)

            # 記錄結果
            logger.info(f"動態選幣完成 | 前 {top_n} 名成交量幣種：")
            for i, item in enumerate(usdt_futures[:top_n]):
                vol_m = item["volume"] / 1_000_000
                change = item.get("change", 0) or 0
                logger.info(
                    f"  #{i+1:2d} {item['symbol']:<25s} | "
                    f"24h量: {vol_m:>10.1f}M USDT | "
                    f"漲跌: {change:+.1f}%"
                )

            self._cached_pairs = top_pairs
            return top_pairs

        except Exception as e:
            logger.error(f"取得成交量排名失敗: {e}")
            # 失敗時使用快取或預設幣種
            if self._cached_pairs:
                logger.info("使用快取的交易對列表")
                return self._cached_pairs
            return ["BTC/USDT:USDT", "ETH/USDT:USDT"]

    def get_cached_pairs(self) -> list[str]:
        """取得快取的交易對列表"""
        return self._cached_pairs if self._cached_pairs else self.get_top_volume_pairs()
