"""
歷史數據載入模組 - 從 Binance 下載並快取歷史 K 線數據
"""

import os
import logging
import time
import pandas as pd
import ccxt
from datetime import datetime, timedelta
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class DataLoader:
    """歷史數據載入器"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        load_dotenv()

        # 初始化交易所（只讀，不需要 API 金鑰）
        self.exchange = ccxt.binanceusdm({"enableRateLimit": True})
        self.exchange.load_markets()

    def fetch_historical(
        self,
        symbol: str,
        timeframe: str = "15m",
        days: int = 30,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        下載歷史 K 線數據

        Args:
            symbol: 交易對，如 "DOGE/USDT:USDT"
            timeframe: K 線週期
            days: 回溯天數
            use_cache: 是否使用快取

        Returns:
            包含 OHLCV 數據的 DataFrame
        """
        cache_file = self._get_cache_path(symbol, timeframe, days)

        # 檢查快取
        if use_cache and os.path.exists(cache_file):
            cache_age = time.time() - os.path.getmtime(cache_file)
            if cache_age < 3600:  # 快取有效期 1 小時
                logger.info(f"使用快取數據: {cache_file}")
                df = pd.read_csv(cache_file, parse_dates=["timestamp"])
                return df

        logger.info(f"下載 {symbol} {timeframe} 歷史數據 ({days} 天)...")

        # 計算起始時間
        since = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
        all_ohlcv = []

        while True:
            try:
                ohlcv = self.exchange.fetch_ohlcv(
                    symbol, timeframe=timeframe, since=since, limit=1000
                )
                if not ohlcv:
                    break

                all_ohlcv.extend(ohlcv)
                since = ohlcv[-1][0] + 1  # 下一批從最後一根 K 線之後開始

                # 如果返回的數據少於 1000 根，代表已到最新
                if len(ohlcv) < 1000:
                    break

                time.sleep(0.5)  # 避免速率限制

            except Exception as e:
                logger.error(f"下載數據失敗: {e}")
                time.sleep(2)
                continue

        if not all_ohlcv:
            raise ValueError(f"無法下載 {symbol} 的歷史數據")

        # 轉換為 DataFrame
        df = pd.DataFrame(
            all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.drop_duplicates(subset=["timestamp"], inplace=True)
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)

        # 儲存快取
        df.to_csv(cache_file, index=False)
        logger.info(f"下載完成: {len(df)} 根 K 線，已快取至 {cache_file}")

        return df

    def fetch_multi_timeframe(
        self, symbol: str, timeframes: list[str], days: int = 30
    ) -> dict[str, pd.DataFrame]:
        """
        下載多個時間框架的數據

        Args:
            symbol: 交易對
            timeframes: 時間框架列表，如 ["5m", "15m", "1h"]
            days: 回溯天數

        Returns:
            {timeframe: DataFrame} 字典
        """
        result = {}
        for tf in timeframes:
            result[tf] = self.fetch_historical(symbol, tf, days)
        return result

    def _get_cache_path(self, symbol: str, timeframe: str, days: int) -> str:
        """生成快取文件路徑"""
        safe_symbol = symbol.replace("/", "_").replace(":", "_")
        filename = f"{safe_symbol}_{timeframe}_{days}d.csv"
        return os.path.join(self.data_dir, filename)
