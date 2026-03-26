"""
幣安 USDT-M 永續合約交易所連線模組

負責與幣安交易所的所有 API 互動，包含下單、查詢餘額、持倉等功能。
"""

import time
import logging
from typing import Optional

import ccxt
import pandas as pd
from dotenv import load_dotenv
import os

logger = logging.getLogger(__name__)


class BinanceExchange:
    """幣安 USDT-M 永續合約交易所封裝類別"""

    def __init__(self, config: dict) -> None:
        """
        初始化交易所連線

        Args:
            config: 從 config.yaml 載入的設定字典，應包含：
                - exchange.sandbox (bool): 是否使用測試網
                - trading.leverage (int): 槓桿倍數
                - trading.margin_mode (str): 保證金模式 (isolated/cross)
                - trading.symbols (list[str]): 交易對列表
        """
        # 載入 .env 檔案中的 API 金鑰
        load_dotenv()

        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")

        if not api_key or not api_secret:
            raise ValueError("請在 .env 檔案中設定 BINANCE_API_KEY 和 BINANCE_API_SECRET")

        self.config = config
        self.max_retries: int = 3
        self.retry_delay: float = 1.0  # 初始重試延遲（秒）

        # 取得交易所相關設定
        exchange_config = config.get("exchange", {})
        trading_config = config.get("trading", {})

        self.leverage: int = trading_config.get("leverage", 5)
        self.margin_mode: str = trading_config.get("margin_mode", "isolated")
        self.symbols: list[str] = trading_config.get("symbols", [])

        # 初始化 ccxt 幣安 USDT-M 永續合約連線
        self.exchange = ccxt.binanceusdm({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,  # 啟用速率限制，避免被封鎖
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,  # 自動校正時間差異
            },
        })

        # 如果設定為沙盒模式（測試網），啟用測試環境
        if exchange_config.get("sandbox", False):
            self.exchange.set_sandbox_mode(True)
            logger.info("已啟用幣安測試網模式")

        # 載入市場資訊
        try:
            self.exchange.load_markets()
            logger.info("已成功載入市場資訊")
        except Exception as e:
            logger.error(f"載入市場資訊失敗: {e}")
            raise

        # 為所有交易對設定保證金模式和槓桿倍數
        for symbol in self.symbols:
            self._set_margin_and_leverage(symbol)

        logger.info(
            f"BinanceExchange 初始化完成 | 槓桿: {self.leverage}x | "
            f"保證金模式: {self.margin_mode} | 交易對: {self.symbols}"
        )

    def _set_margin_and_leverage(self, symbol: str) -> None:
        """
        設定指定交易對的保證金模式與槓桿倍數

        Args:
            symbol: 交易對符號，例如 'BTC/USDT:USDT'
        """
        try:
            # 設定保證金模式（逐倉 isolated / 全倉 cross）
            self.exchange.set_margin_mode(self.margin_mode, symbol)
            logger.info(f"{symbol} 保證金模式已設為 {self.margin_mode}")
        except ccxt.ExchangeError as e:
            # 如果已經是該模式，幣安會回傳錯誤，可忽略
            if "No need to change margin type" in str(e):
                logger.debug(f"{symbol} 保證金模式已經是 {self.margin_mode}，無需變更")
            else:
                logger.warning(f"{symbol} 設定保證金模式失敗: {e}")

        try:
            # 設定槓桿倍數
            self.exchange.set_leverage(self.leverage, symbol)
            logger.info(f"{symbol} 槓桿倍數已設為 {self.leverage}x")
        except ccxt.ExchangeError as e:
            logger.warning(f"{symbol} 設定槓桿倍數失敗: {e}")

    def _retry_on_error(self, func, *args, **kwargs):
        """
        帶有重試邏輯的函式包裝器（針對網路錯誤，最多重試 3 次，指數退避）

        Args:
            func: 要執行的函式
            *args: 位置參數
            **kwargs: 關鍵字參數

        Returns:
            函式執行結果

        Raises:
            最後一次重試仍失敗時拋出原始例外
        """
        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except (ccxt.NetworkError, ccxt.RequestTimeout) as e:
                last_exception = e
                delay = self.retry_delay * (2 ** (attempt - 1))  # 指數退避
                logger.warning(
                    f"網路錯誤，第 {attempt}/{self.max_retries} 次重試，"
                    f"等待 {delay} 秒: {e}"
                )
                time.sleep(delay)
            except ccxt.InsufficientFunds as e:
                logger.error(f"餘額不足: {e}")
                raise
            except ccxt.RateLimitExceeded as e:
                last_exception = e
                delay = self.retry_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"超過速率限制，第 {attempt}/{self.max_retries} 次重試，"
                    f"等待 {delay} 秒: {e}"
                )
                time.sleep(delay)
            except ccxt.ExchangeError as e:
                logger.error(f"交易所錯誤: {e}")
                raise

        logger.error(f"重試 {self.max_retries} 次後仍然失敗")
        raise last_exception

    # =========================================================================
    # 市場資料查詢方法
    # =========================================================================

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> pd.DataFrame:
        """
        取得 K 線（OHLCV）資料並回傳 pandas DataFrame

        Args:
            symbol: 交易對符號，例如 'BTC/USDT:USDT'
            timeframe: K 線時間週期，例如 '1m', '5m', '1h', '4h', '1d'
            limit: 取得的 K 線數量上限

        Returns:
            包含 timestamp, open, high, low, close, volume 欄位的 DataFrame
        """
        logger.debug(f"取得 {symbol} {timeframe} K 線資料（{limit} 根）")

        raw = self._retry_on_error(
            self.exchange.fetch_ohlcv, symbol, timeframe, limit=limit
        )

        df = pd.DataFrame(
            raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        logger.debug(f"成功取得 {len(df)} 根 K 線資料")
        return df

    def get_ticker(self, symbol: str) -> dict:
        """
        取得指定交易對的最新行情（含最新價格）

        Args:
            symbol: 交易對符號

        Returns:
            行情資訊字典，包含 last（最新價格）、bid、ask 等
        """
        logger.debug(f"取得 {symbol} 最新行情")
        ticker = self._retry_on_error(self.exchange.fetch_ticker, symbol)
        logger.debug(f"{symbol} 最新價格: {ticker['last']}")
        return ticker

    # =========================================================================
    # 帳戶查詢方法
    # =========================================================================

    def fetch_balance(self) -> dict:
        """
        取得 USDT 帳戶餘額資訊

        Returns:
            包含以下欄位的字典:
                - total: USDT 總餘額
                - free: 可用餘額
                - used: 已用保證金
        """
        logger.debug("取得 USDT 帳戶餘額")
        balance = self._retry_on_error(self.exchange.fetch_balance)
        usdt = balance.get("USDT", {})

        result = {
            "total": usdt.get("total", 0),
            "free": usdt.get("free", 0),
            "used": usdt.get("used", 0),
        }
        logger.info(
            f"USDT 餘額 | 總額: {result['total']} | "
            f"可用: {result['free']} | 已用: {result['used']}"
        )
        return result

    def fetch_positions(self) -> list[dict]:
        """
        取得所有持倉中的部位

        Returns:
            持倉列表，每個元素為包含 symbol, side, contracts, notional,
            unrealizedPnl, percentage, entryPrice 等欄位的字典
        """
        logger.debug("取得所有持倉部位")
        positions = self._retry_on_error(self.exchange.fetch_positions)

        # 只回傳有實際持倉的部位（合約數量不為零）
        open_positions = [
            p for p in positions
            if p.get("contracts") and float(p["contracts"]) != 0
        ]

        logger.info(f"目前持倉數量: {len(open_positions)}")
        for pos in open_positions:
            logger.info(
                f"  {pos['symbol']} | 方向: {pos['side']} | "
                f"數量: {pos['contracts']} | 未實現盈虧: {pos.get('unrealizedPnl', 0)}"
            )

        return open_positions

    def has_position(self, symbol: str) -> bool:
        """
        檢查指定交易對是否有持倉

        Args:
            symbol: 交易對符號

        Returns:
            True 表示有持倉，False 表示無持倉
        """
        positions = self.fetch_positions()
        for pos in positions:
            if pos["symbol"] == symbol and float(pos.get("contracts", 0)) != 0:
                logger.debug(f"{symbol} 有持倉")
                return True
        logger.debug(f"{symbol} 無持倉")
        return False

    # =========================================================================
    # 下單方法
    # =========================================================================

    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
    ) -> dict:
        """
        建立市價單（開倉或平倉）

        Args:
            symbol: 交易對符號
            side: 方向，'buy'（做多）或 'sell'（做空）
            amount: 下單數量（合約張數）

        Returns:
            訂單資訊字典
        """
        logger.info(f"建立市價單 | {symbol} | {side} | 數量: {amount}")

        order = self._retry_on_error(
            self.exchange.create_order,
            symbol=symbol,
            type="market",
            side=side,
            amount=amount,
        )

        logger.info(f"市價單已成交 | 訂單 ID: {order['id']} | 均價: {order.get('average', 'N/A')}")
        return order

    def create_stop_loss_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float,
    ) -> dict:
        """
        建立停損單（STOP_MARKET 類型）

        Args:
            symbol: 交易對符號
            side: 方向，'buy'（空單停損）或 'sell'（多單停損）
            amount: 數量
            stop_price: 觸發價格

        Returns:
            訂單資訊字典
        """
        logger.info(
            f"建立停損單 | {symbol} | {side} | 數量: {amount} | 觸發價: {stop_price}"
        )

        order = self._retry_on_error(
            self.exchange.create_order,
            symbol=symbol,
            type="STOP_MARKET",
            side=side,
            amount=amount,
            price=None,
            params={"stopPrice": stop_price, "closePosition": False},
        )

        logger.info(f"停損單已建立 | 訂單 ID: {order['id']}")
        return order

    def create_take_profit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float,
    ) -> dict:
        """
        建立止盈單（TAKE_PROFIT_MARKET 類型）

        Args:
            symbol: 交易對符號
            side: 方向，'buy'（空單止盈）或 'sell'（多單止盈）
            amount: 數量
            stop_price: 觸發價格

        Returns:
            訂單資訊字典
        """
        logger.info(
            f"建立止盈單 | {symbol} | {side} | 數量: {amount} | 觸發價: {stop_price}"
        )

        order = self._retry_on_error(
            self.exchange.create_order,
            symbol=symbol,
            type="TAKE_PROFIT_MARKET",
            side=side,
            amount=amount,
            price=None,
            params={"stopPrice": stop_price, "closePosition": False},
        )

        logger.info(f"止盈單已建立 | 訂單 ID: {order['id']}")
        return order

    def cancel_all_orders(self, symbol: str) -> list[dict]:
        """
        取消指定交易對的所有掛單

        Args:
            symbol: 交易對符號

        Returns:
            已取消的訂單列表
        """
        logger.info(f"取消 {symbol} 的所有掛單")

        cancelled = self._retry_on_error(
            self.exchange.cancel_all_orders, symbol
        )

        logger.info(f"已取消 {symbol} 的 {len(cancelled)} 筆掛單")
        return cancelled

    # =========================================================================
    # 整合用便捷方法
    # =========================================================================

    def get_balance(self) -> float:
        """取得 USDT 總餘額（數值）"""
        balance_info = self.fetch_balance()
        return float(balance_info.get("total", 0))

    def get_positions(self) -> list[dict]:
        """取得所有持倉（fetch_positions 的別名）"""
        return self.fetch_positions()

    def set_margin_and_leverage(self, symbol: str, margin_type: str = "isolated", leverage: int = 3) -> None:
        """
        設定指定交易對的保證金模式與槓桿

        Args:
            symbol: 交易對符號
            margin_type: 保證金模式 (isolated/cross)
            leverage: 槓桿倍數
        """
        try:
            self.exchange.set_margin_mode(margin_type, symbol)
            logger.info(f"{symbol} 保證金模式已設為 {margin_type}")
        except ccxt.ExchangeError as e:
            if "No need to change margin type" in str(e):
                logger.debug(f"{symbol} 保證金模式已經是 {margin_type}")
            else:
                logger.warning(f"{symbol} 設定保證金模式失敗: {e}")

        try:
            self.exchange.set_leverage(leverage, symbol)
            logger.info(f"{symbol} 槓桿已設為 {leverage}x")
        except ccxt.ExchangeError as e:
            logger.warning(f"{symbol} 設定槓桿失敗: {e}")

    def get_ticker(self, symbol: str) -> dict:
        """取得最新行情（含 last 價格）"""
        return self._retry_on_error(self.exchange.fetch_ticker, symbol)

    def fetch_ticker(self, symbol: str) -> dict:
        """取得最新行情（get_ticker 的別名）"""
        return self.get_ticker(symbol)

    def create_order(self, symbol: str, type: str, side: str, amount: float, price: float = None, params: dict = None) -> dict:
        """
        通用下單方法

        Args:
            symbol: 交易對
            type: 訂單類型 (market, limit, stop_market, take_profit_market)
            side: 方向 (buy/sell)
            amount: 數量
            price: 價格（市價單可為 None）
            params: 額外參數
        """
        logger.info(f"下單 | {symbol} | {type} | {side} | 數量: {amount}")
        return self._retry_on_error(
            self.exchange.create_order,
            symbol=symbol,
            type=type,
            side=side,
            amount=amount,
            price=price,
            params=params or {},
        )

    def fetch_open_orders(self, symbol: str) -> list[dict]:
        """取得指定交易對的所有掛單"""
        return self._retry_on_error(self.exchange.fetch_open_orders, symbol)

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        """取消指定訂單"""
        logger.info(f"取消訂單 {order_id} | {symbol}")
        return self._retry_on_error(self.exchange.cancel_order, order_id, symbol)
