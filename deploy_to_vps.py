"""
VPS 一鍵部署腳本
自動將 trading bot 部署到 Vultr VPS
"""
import os
import sys
import getpass
import paramiko
from scp import SCPClient

VPS_IP = os.environ.get("VPS_IP", "YOUR_VPS_IP")
VPS_USER = "root"
BOT_DIR = "/opt/trading-bot"
LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))

# 不上傳的檔案/資料夾
EXCLUDE = {
    "__pycache__", ".git", "trading.log", "trades",
    "data", "tests", "docs", "deploy_to_vps.py",
    "deploy_vps.sh", ".env"
}

DEPLOY_COMMANDS = f"""
set -e
export DEBIAN_FRONTEND=noninteractive
echo '[1/5] 更新系統...'
apt-get update -qq && apt-get install -y -qq -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" python3 python3-pip python3-venv

echo '[2/5] 建立目錄...'
mkdir -p {BOT_DIR}

echo '[3/5] 建立虛擬環境...'
cd {BOT_DIR}
python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo '[4/5] 建立系統服務...'
cat > /etc/systemd/system/trading-bot.service << 'EOF'
[Unit]
Description=Crypto Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory={BOT_DIR}
EnvironmentFile={BOT_DIR}/.env
Environment=PYTHONUNBUFFERED=1
ExecStart={BOT_DIR}/venv/bin/python main_with_scheduler.py
Restart=always
RestartSec=15
StandardOutput=append:{BOT_DIR}/trading.log
StandardError=append:{BOT_DIR}/trading.log

[Install]
WantedBy=multi-user.target
EOF

echo '[5/5] 啟動服務...'
systemctl daemon-reload
systemctl enable trading-bot
systemctl start trading-bot
sleep 3
systemctl status trading-bot --no-pager
echo '=============================='
echo ' 部署完成！'
echo '=============================='
"""


def upload_directory(scp, local_path, remote_path, exclude):
    """遞迴上傳資料夾"""
    for item in os.listdir(local_path):
        if item in exclude:
            continue
        local_item = os.path.join(local_path, item)
        remote_item = f"{remote_path}/{item}"
        if os.path.isdir(local_item):
            try:
                scp._channel.exec_command(f"mkdir -p {remote_item}")
            except Exception:
                pass
            upload_directory(scp, local_item, remote_item, exclude)
        else:
            scp.put(local_item, remote_item)


def main():
    print("=" * 50)
    print(" Crypto Trading Bot - VPS 部署")
    print(f" 目標主機: {VPS_IP}")
    print("=" * 50)

    password = os.environ.get("VPS_PASS") or getpass.getpass("\n請輸入 VPS 密碼（輸入時不顯示）: ")

    print("\n[連線中...]")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(VPS_IP, username=VPS_USER, password=password, timeout=15)
        print("[連線成功！]")
    except Exception as e:
        print(f"[連線失敗] {e}")
        sys.exit(1)

    # 建立目標目錄
    ssh.exec_command(f"mkdir -p {BOT_DIR}")

    # 上傳 .env（API 金鑰）
    print("\n[上傳設定檔...]")
    with SCPClient(ssh.get_transport()) as scp:
        scp.put(os.path.join(LOCAL_DIR, ".env"), f"{BOT_DIR}/.env")
        scp.put(os.path.join(LOCAL_DIR, "config.yaml"), f"{BOT_DIR}/config.yaml")

    # 上傳程式碼
    print("[上傳程式碼...（需要約1分鐘）]")
    with SCPClient(ssh.get_transport(), progress=lambda f, s, p: print(f"  {f}", end="\r")) as scp:
        for item in os.listdir(LOCAL_DIR):
            if item in EXCLUDE:
                continue
            local_item = os.path.join(LOCAL_DIR, item)
            if os.path.isfile(local_item):
                scp.put(local_item, f"{BOT_DIR}/{item}")
            elif os.path.isdir(local_item):
                scp.put(local_item, BOT_DIR, recursive=True)

    print("\n[程式碼上傳完成]")

    # 執行部署指令
    print("\n[執行部署...]")
    stdin, stdout, stderr = ssh.exec_command(DEPLOY_COMMANDS, get_pty=True)
    for line in stdout:
        print(line, end="")

    # 顯示固定 IP 提示
    print(f"""
==============================
 幣安 API 白名單請加入：
 {VPS_IP}
==============================
查看日誌指令（VPS上執行）：
  tail -f {BOT_DIR}/trading.log
""")

    ssh.close()


if __name__ == "__main__":
    main()
