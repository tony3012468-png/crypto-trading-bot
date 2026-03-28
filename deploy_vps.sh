#!/bin/bash
# ============================================================
# Crypto Trading Bot - VPS 一鍵部署腳本
# 在 Ubuntu 22.04 VPS 上執行
# ============================================================

set -e  # 任何錯誤立即停止

echo "=============================="
echo " Crypto Trading Bot 部署開始"
echo "=============================="

# 1. 更新系統
echo "[1/7] 更新系統套件..."
apt-get update -qq && apt-get upgrade -y -qq

# 2. 安裝必要工具
echo "[2/7] 安裝 Python、pip、git..."
apt-get install -y -qq python3 python3-pip python3-venv git screen

# 3. 建立專案目錄
echo "[3/7] 建立專案目錄..."
mkdir -p /opt/trading-bot
cd /opt/trading-bot

# 4. 上傳提示
echo "[4/7] 等待程式碼上傳..."
echo ""
echo "  請在你的 Windows 電腦上執行以下指令上傳程式碼："
echo "  (另開一個終端機，不要關掉這個)"
echo ""
echo "  scp -r \"C:/Users/tony3/OneDrive/Desktop/VSCODE/crypto-trading-bot/.\" root@<你的VPS_IP>:/opt/trading-bot/"
echo ""
read -p "上傳完成後按 Enter 繼續..."

# 5. 建立虛擬環境並安裝套件
echo "[5/7] 安裝 Python 套件..."
cd /opt/trading-bot
python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 6. 建立 systemd 服務（開機自動啟動）
echo "[6/7] 建立系統服務..."
cat > /etc/systemd/system/trading-bot.service << 'EOF'
[Unit]
Description=Crypto Trading Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/trading-bot
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/trading-bot/venv/bin/python main_with_scheduler.py
Restart=always
RestartSec=10
StandardOutput=append:/opt/trading-bot/trading.log
StandardError=append:/opt/trading-bot/trading.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable trading-bot
systemctl start trading-bot

echo ""
echo "[7/7] 完成！"
echo "=============================="
echo " 部署成功"
echo "=============================="
echo ""
echo "常用指令："
echo "  查看狀態：  systemctl status trading-bot"
echo "  查看日誌：  tail -f /opt/trading-bot/trading.log"
echo "  重啟機器人：systemctl restart trading-bot"
echo "  停止機器人：systemctl stop trading-bot"
echo ""
echo "你的 VPS 固定 IP 請加入幣安 API 白名單！"
