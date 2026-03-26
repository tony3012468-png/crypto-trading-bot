"""
風險管理模組

負責控制每筆交易的風險、倉位大小計算、
回撤監控、連續虧損追蹤等風控功能。
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class RiskManager:
    """風險管理器 - 控制交易風險與資金管理"""

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        初始化風險管理器

        Args:
            config: 完整設定檔字典（包含 risk 與 account 區段）
        """
        risk_cfg = config.get("risk", {})
        account_cfg = config.get("account", {})

        # --- 風控參數 ---
        self.risk_per_trade: float = risk_cfg.get("risk_per_trade", 0.02)
        self.max_open_positions: int = risk_cfg.get("max_open_positions", 2)
        self.max_drawdown_pct: float = risk_cfg.get("max_drawdown_pct", 12.0)
        self.loss_streak_limit: int = risk_cfg.get("loss_streak_limit", 4)
        self.risk_reduced: float = risk_cfg.get("risk_reduced", 0.01)
        self.daily_loss_limit: float = risk_cfg.get("daily_loss_limit", 0.05)

        # --- 帳戶參數 ---
        initial_capital: float = account_cfg.get("total_capital", 125.0)
        self.leverage: int = account_cfg.get("leverage", 3)

        # --- 內部追蹤狀態 ---
        self.consecutive_losses: int = 0
        self.peak_balance: float = initial_capital
        self.current_balance: float = initial_capital
        self.daily_pnl: float = 0.0
        self.total_pnl: float = 0.0
        self.trade_count: int = 0
        self.win_count: int = 0

        logger.info(
            "風險管理器已初始化 | 初始資金: %.2f USDT | 單筆風險: %.1f%% | "
            "最大持倉數: %d | 最大回撤: %.1f%%",
            initial_capital,
            self.risk_per_trade * 100,
            self.max_open_positions,
            self.max_drawdown_pct,
        )

    def can_open_trade(self, current_positions: int, daily_pnl: float) -> bool:
        """
        檢查是否允許開新倉位

        Args:
            current_positions: 當前持倉數量
            daily_pnl: 當日已實現損益（USDT）

        Returns:
            True 表示可以開倉，False 表示不允許
        """
        # 檢查最大持倉數
        if current_positions >= self.max_open_positions:
            logger.warning(
                "已達最大持倉數限制 (%d/%d)，不允許開新倉",
                current_positions,
                self.max_open_positions,
            )
            return False

        # 檢查最大回撤
        drawdown = self.get_drawdown_pct()
        if drawdown >= self.max_drawdown_pct:
            logger.warning(
                "回撤已達 %.2f%%，超過限制 %.2f%%，暫停交易",
                drawdown,
                self.max_drawdown_pct,
            )
            return False

        # 檢查每日虧損限制
        daily_loss_threshold = self.current_balance * self.daily_loss_limit
        if daily_pnl < 0 and abs(daily_pnl) >= daily_loss_threshold:
            logger.warning(
                "當日虧損 %.2f USDT，已達每日限制 (%.2f USDT)，暫停交易",
                abs(daily_pnl),
                daily_loss_threshold,
            )
            return False

        # 檢查連續虧損
        if self.consecutive_losses >= self.loss_streak_limit:
            logger.warning(
                "連續虧損 %d 次，已達限制 (%d 次)，風險已降低至 %.1f%%",
                self.consecutive_losses,
                self.loss_streak_limit,
                self.risk_reduced * 100,
            )
            # 連續虧損時不直接禁止，而是降低風險（在 get_current_risk_pct 中處理）
            # 但如果連續虧損超過限制的兩倍，則暫停交易
            if self.consecutive_losses >= self.loss_streak_limit * 2:
                logger.warning(
                    "連續虧損 %d 次，超過雙倍限制，完全暫停交易",
                    self.consecutive_losses,
                )
                return False

        logger.info(
            "風控檢查通過 | 持倉: %d/%d | 回撤: %.2f%% | 當日損益: %.2f USDT",
            current_positions,
            self.max_open_positions,
            drawdown,
            daily_pnl,
        )
        return True

    def calculate_position_size(
        self,
        balance: float,
        entry_price: float,
        stop_loss_price: float,
        leverage: int,
    ) -> float:
        """
        根據風險比例和止損距離計算倉位大小

        使用公式：倉位金額 = (資金 * 風險比例) / (止損距離百分比)
        再除以入場價格得到合約數量

        Args:
            balance: 帳戶餘額（USDT）
            entry_price: 預計入場價格
            stop_loss_price: 止損價格
            leverage: 槓桿倍數

        Returns:
            合約數量（以標的幣種計）
        """
        if entry_price <= 0 or stop_loss_price <= 0:
            logger.error("價格無效：入場價 %.8f，止損價 %.8f", entry_price, stop_loss_price)
            return 0.0

        # 計算止損距離百分比
        sl_distance_pct = abs(entry_price - stop_loss_price) / entry_price
        if sl_distance_pct == 0:
            logger.error("止損距離為零，無法計算倉位大小")
            return 0.0

        # 取得當前風險比例（可能因連續虧損而降低）
        current_risk = self.get_current_risk_pct()

        # 風險金額 = 帳戶餘額 * 風險比例
        risk_amount = balance * current_risk

        # 倉位金額（USDT） = 風險金額 / 止損距離百分比
        position_value = risk_amount / sl_distance_pct

        # 考慮槓桿：實際需要的保證金 = 倉位金額 / 槓桿
        margin_required = position_value / leverage

        # 確保不超過帳戶餘額的合理比例（最大 50%）
        max_margin = balance * 0.5
        if margin_required > max_margin:
            position_value = max_margin * leverage
            logger.warning(
                "倉位大小已限制至帳戶 50%% 保證金 (%.2f USDT)", max_margin
            )

        # 轉換為合約數量
        quantity = position_value / entry_price

        logger.info(
            "倉位計算 | 餘額: %.2f | 風險: %.1f%% | 止損距離: %.2f%% | "
            "倉位金額: %.2f USDT | 數量: %.6f | 槓桿: %dx",
            balance,
            current_risk * 100,
            sl_distance_pct * 100,
            position_value,
            quantity,
            leverage,
        )
        return quantity

    def get_current_risk_pct(self) -> float:
        """
        取得當前每筆交易的風險比例

        如果連續虧損達到限制，自動降低風險比例。

        Returns:
            風險比例（例如 0.02 代表 2%）
        """
        if self.consecutive_losses >= self.loss_streak_limit:
            logger.debug(
                "連續虧損 %d 次，使用降低後風險: %.1f%%",
                self.consecutive_losses,
                self.risk_reduced * 100,
            )
            return self.risk_reduced
        return self.risk_per_trade

    def update_trade_result(self, pnl: float) -> None:
        """
        交易結束後更新內部狀態

        Args:
            pnl: 該筆交易的損益（USDT，正數為獲利，負數為虧損）
        """
        self.trade_count += 1
        self.daily_pnl += pnl
        self.total_pnl += pnl
        self.current_balance += pnl

        if pnl >= 0:
            # 獲利：重置連續虧損計數器
            self.win_count += 1
            self.consecutive_losses = 0
            logger.info(
                "交易獲利 +%.2f USDT | 連續虧損已重置 | 當前餘額: %.2f",
                pnl,
                self.current_balance,
            )
        else:
            # 虧損：增加連續虧損計數
            self.consecutive_losses += 1
            logger.warning(
                "交易虧損 %.2f USDT | 連續虧損: %d 次 | 當前餘額: %.2f",
                pnl,
                self.consecutive_losses,
                self.current_balance,
            )

        # 更新峰值餘額
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
            logger.info("餘額新高: %.2f USDT", self.peak_balance)

        # 計算並記錄勝率
        win_rate = (self.win_count / self.trade_count * 100) if self.trade_count > 0 else 0
        logger.info(
            "交易統計 | 總交易: %d | 勝率: %.1f%% | 總損益: %.2f USDT",
            self.trade_count,
            win_rate,
            self.total_pnl,
        )

    def get_drawdown_pct(self) -> float:
        """
        計算當前從峰值的回撤百分比

        Returns:
            回撤百分比（例如 5.0 代表 5%）
        """
        if self.peak_balance <= 0:
            return 0.0
        drawdown = (self.peak_balance - self.current_balance) / self.peak_balance * 100
        return max(drawdown, 0.0)

    def get_daily_pnl(self) -> float:
        """
        取得當日已實現損益

        Returns:
            當日損益金額（USDT）
        """
        return self.daily_pnl

    def reset_daily(self) -> None:
        """
        重置每日損益計數器（每天開盤時呼叫）
        """
        logger.info("重置每日損益 | 昨日損益: %.2f USDT", self.daily_pnl)
        self.daily_pnl = 0.0

    def get_status(self) -> Dict[str, Any]:
        """
        取得風險管理器的完整狀態

        Returns:
            包含所有風控指標的字典
        """
        win_rate = (self.win_count / self.trade_count * 100) if self.trade_count > 0 else 0.0

        return {
            "current_balance": self.current_balance,
            "peak_balance": self.peak_balance,
            "total_pnl": self.total_pnl,
            "daily_pnl": self.daily_pnl,
            "drawdown_pct": self.get_drawdown_pct(),
            "max_drawdown_pct": self.max_drawdown_pct,
            "consecutive_losses": self.consecutive_losses,
            "loss_streak_limit": self.loss_streak_limit,
            "current_risk_pct": self.get_current_risk_pct(),
            "trade_count": self.trade_count,
            "win_count": self.win_count,
            "win_rate": win_rate,
            "can_trade": self.get_drawdown_pct() < self.max_drawdown_pct,
        }
