"""
訂單管理模組

負責交易的完整生命週期管理，包括開倉、平倉、
止損/止盈設定、移動止損更新等功能。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OrderManager:
    """訂單管理器 - 管理交易生命週期"""

    def __init__(self, exchange: Any, risk_manager: Any) -> None:
        """
        初始化訂單管理器

        Args:
            exchange: BinanceExchange 交易所實例（提供下單 API）
            risk_manager: RiskManager 風險管理器實例
        """
        self.exchange = exchange
        self.risk_manager = risk_manager
        # 追蹤活躍倉位：symbol -> 交易資訊字典
        self.active_trades: Dict[str, Dict[str, Any]] = {}

        logger.info("訂單管理器已初始化")

    def open_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        amount: float,
    ) -> Dict[str, Any]:
        """
        開倉：執行市價單並設定止損/止盈

        Args:
            symbol: 交易對（例如 "DOGE/USDT:USDT"）
            side: 方向（"buy" 做多 / "sell" 做空）
            entry_price: 預計入場價格（用於記錄，實際以市價成交）
            stop_loss: 止損價格
            take_profit: 止盈價格
            amount: 合約數量

        Returns:
            交易資訊字典，包含訂單 ID 與狀態
        """
        trade_info: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "amount": amount,
            "status": "pending",
            "order_id": None,
            "sl_order_id": None,
            "tp_order_id": None,
        }

        try:
            # 執行市價開倉單
            logger.info(
                "開倉 %s %s | 數量: %.6f | 預計入場: %.8f | 止損: %.8f | 止盈: %.8f",
                side.upper(),
                symbol,
                amount,
                entry_price,
                stop_loss,
                take_profit,
            )

            order = self.exchange.create_market_order(symbol, side, amount)
            trade_info["order_id"] = order.get("id")
            trade_info["entry_price"] = order.get("average", entry_price)
            trade_info["status"] = "open"

            logger.info(
                "市價單成交 | 訂單 ID: %s | 成交價: %.8f",
                trade_info["order_id"],
                trade_info["entry_price"],
            )

            # 設定止損單
            sl_side = "sell" if side == "buy" else "buy"
            sl_order = self.exchange.create_order(
                symbol=symbol,
                type="stop_market",
                side=sl_side,
                amount=amount,
                params={"stopPrice": stop_loss, "closePosition": True},
            )
            trade_info["sl_order_id"] = sl_order.get("id")
            logger.info("止損單已設定 | 訂單 ID: %s | 價格: %.8f", trade_info["sl_order_id"], stop_loss)

            # 設定止盈單
            tp_order = self.exchange.create_order(
                symbol=symbol,
                type="take_profit_market",
                side=sl_side,
                amount=amount,
                params={"stopPrice": take_profit, "closePosition": True},
            )
            trade_info["tp_order_id"] = tp_order.get("id")
            logger.info("止盈單已設定 | 訂單 ID: %s | 價格: %.8f", trade_info["tp_order_id"], take_profit)

            # 記錄活躍倉位
            self.active_trades[symbol] = trade_info
            logger.info("倉位已開啟並記錄 | %s %s", side.upper(), symbol)

        except Exception as e:
            trade_info["status"] = "error"
            trade_info["error"] = str(e)
            logger.error("開倉失敗 %s: %s", symbol, e)
            # 開倉失敗時嘗試取消已設定的掛單
            self._cleanup_failed_orders(trade_info)

        return trade_info

    def close_position(self, symbol: str) -> Dict[str, Any]:
        """
        平倉：市價平倉並取消所有相關掛單

        Args:
            symbol: 交易對

        Returns:
            平倉結果字典
        """
        result: Dict[str, Any] = {
            "symbol": symbol,
            "status": "pending",
            "pnl": 0.0,
        }

        try:
            # 先取消該交易對的所有掛單
            self.cancel_symbol_orders(symbol)

            trade = self.active_trades.get(symbol)
            if not trade:
                logger.warning("找不到 %s 的活躍倉位", symbol)
                result["status"] = "no_position"
                return result

            # 執行市價平倉
            close_side = "sell" if trade["side"] == "buy" else "buy"
            logger.info(
                "平倉 %s | 方向: %s | 數量: %.6f",
                symbol,
                close_side.upper(),
                trade["amount"],
            )

            order = self.exchange.create_market_order(
                symbol, close_side, trade["amount"], params={"reduceOnly": True}
            )

            close_price = order.get("average", 0.0)

            # 計算損益
            if trade["side"] == "buy":
                pnl = (close_price - trade["entry_price"]) * trade["amount"]
            else:
                pnl = (trade["entry_price"] - close_price) * trade["amount"]

            result["close_price"] = close_price
            result["entry_price"] = trade["entry_price"]
            result["pnl"] = pnl
            result["status"] = "closed"

            # 更新風險管理器
            self.risk_manager.update_trade_result(pnl)

            # 從活躍倉位中移除
            del self.active_trades[symbol]

            logger.info(
                "平倉完成 %s | 入場: %.8f | 平倉: %.8f | 損益: %.2f USDT",
                symbol,
                trade["entry_price"],
                close_price,
                pnl,
            )

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            logger.error("平倉失敗 %s: %s", symbol, e)

        return result

    def check_positions(self) -> List[Dict[str, Any]]:
        """
        檢查所有活躍倉位的狀態與未實現損益

        Returns:
            倉位資訊列表，每個元素包含 symbol、side、entry_price、
            current_price、unrealized_pnl、pnl_pct 等欄位
        """
        positions: List[Dict[str, Any]] = []

        for symbol, trade in self.active_trades.items():
            try:
                # 從交易所取得目前價格
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = ticker.get("last", 0.0)

                # 計算未實現損益
                if trade["side"] == "buy":
                    unrealized_pnl = (current_price - trade["entry_price"]) * trade["amount"]
                else:
                    unrealized_pnl = (trade["entry_price"] - current_price) * trade["amount"]

                # 計算損益百分比
                position_value = trade["entry_price"] * trade["amount"]
                pnl_pct = (unrealized_pnl / position_value * 100) if position_value > 0 else 0.0

                position_info = {
                    "symbol": symbol,
                    "side": trade["side"],
                    "amount": trade["amount"],
                    "entry_price": trade["entry_price"],
                    "current_price": current_price,
                    "stop_loss": trade["stop_loss"],
                    "take_profit": trade["take_profit"],
                    "unrealized_pnl": unrealized_pnl,
                    "pnl_pct": pnl_pct,
                }
                positions.append(position_info)

                logger.debug(
                    "%s %s | 入場: %.8f | 現價: %.8f | 未實現損益: %.2f USDT (%.2f%%)",
                    trade["side"].upper(),
                    symbol,
                    trade["entry_price"],
                    current_price,
                    unrealized_pnl,
                    pnl_pct,
                )

            except Exception as e:
                logger.error("檢查倉位失敗 %s: %s", symbol, e)
                positions.append({
                    "symbol": symbol,
                    "side": trade["side"],
                    "error": str(e),
                })

        logger.info("倉位檢查完成 | 活躍倉位數: %d", len(positions))
        return positions

    def update_trailing_stop(
        self, symbol: str, current_price: float, atr_value: float
    ) -> None:
        """
        更新移動止損（追蹤止損）

        根據當前價格與 ATR 值調整止損位，只往有利方向移動。

        Args:
            symbol: 交易對
            current_price: 目前市場價格
            atr_value: 當前 ATR 值（用於計算止損距離）
        """
        trade = self.active_trades.get(symbol)
        if not trade:
            logger.warning("更新移動止損失敗：找不到 %s 的活躍倉位", symbol)
            return

        old_sl = trade["stop_loss"]

        if trade["side"] == "buy":
            # 做多：止損只能往上移動
            new_sl = current_price - (atr_value * 1.5)
            if new_sl <= old_sl:
                logger.debug(
                    "%s 移動止損無需更新（新 %.8f <= 舊 %.8f）",
                    symbol,
                    new_sl,
                    old_sl,
                )
                return
        else:
            # 做空：止損只能往下移動
            new_sl = current_price + (atr_value * 1.5)
            if new_sl >= old_sl:
                logger.debug(
                    "%s 移動止損無需更新（新 %.8f >= 舊 %.8f）",
                    symbol,
                    new_sl,
                    old_sl,
                )
                return

        try:
            # 取消舊的止損單
            if trade.get("sl_order_id"):
                self.exchange.cancel_order(trade["sl_order_id"], symbol)
                logger.debug("已取消舊止損單: %s", trade["sl_order_id"])

            # 設定新的止損單
            sl_side = "sell" if trade["side"] == "buy" else "buy"
            sl_order = self.exchange.create_order(
                symbol=symbol,
                type="stop_market",
                side=sl_side,
                amount=trade["amount"],
                params={"stopPrice": new_sl, "closePosition": True},
            )

            # 更新交易記錄
            trade["stop_loss"] = new_sl
            trade["sl_order_id"] = sl_order.get("id")

            logger.info(
                "移動止損已更新 %s | 舊止損: %.8f -> 新止損: %.8f | ATR: %.8f",
                symbol,
                old_sl,
                new_sl,
                atr_value,
            )

        except Exception as e:
            logger.error("更新移動止損失敗 %s: %s", symbol, e)

    def cancel_symbol_orders(self, symbol: str) -> None:
        """
        取消指定交易對的所有掛單

        Args:
            symbol: 交易對
        """
        try:
            open_orders = self.exchange.fetch_open_orders(symbol)
            if not open_orders:
                logger.debug("%s 無掛單需要取消", symbol)
                return

            cancelled_count = 0
            for order in open_orders:
                try:
                    self.exchange.cancel_order(order["id"], symbol)
                    cancelled_count += 1
                    logger.debug("已取消訂單 %s (%s)", order["id"], order.get("type", "unknown"))
                except Exception as e:
                    logger.error("取消訂單 %s 失敗: %s", order["id"], e)

            logger.info("%s 已取消 %d 筆掛單", symbol, cancelled_count)

        except Exception as e:
            logger.error("取得 %s 掛單列表失敗: %s", symbol, e)

    def _cleanup_failed_orders(self, trade_info: Dict[str, Any]) -> None:
        """
        開倉失敗時清理已設定的掛單（內部方法）

        Args:
            trade_info: 交易資訊字典
        """
        symbol = trade_info["symbol"]

        for order_key in ("sl_order_id", "tp_order_id"):
            order_id = trade_info.get(order_key)
            if order_id:
                try:
                    self.exchange.cancel_order(order_id, symbol)
                    logger.info("已清理失敗交易的掛單: %s", order_id)
                except Exception as e:
                    logger.error("清理掛單 %s 失敗: %s", order_id, e)
