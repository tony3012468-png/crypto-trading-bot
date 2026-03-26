"""
快速設定腳本 - 幫助用戶快速配置交易機器人
"""

import os
import sys
import shutil


def main():
    print("=" * 60)
    print("  Crypto Trading Bot Pro - 快速設定精靈")
    print("=" * 60)
    print()

    # 檢查 Python 版本
    if sys.version_info < (3, 10):
        print(f"[ERROR] 需要 Python 3.10+，你的版本是 {sys.version}")
        sys.exit(1)
    print(f"[OK] Python {sys.version_info.major}.{sys.version_info.minor}")

    # 檢查依賴
    missing = []
    for pkg in ["ccxt", "pandas", "ta", "yaml", "dotenv", "rich", "requests"]:
        try:
            __import__(pkg)
        except ImportError:
            if pkg == "yaml":
                missing.append("pyyaml")
            elif pkg == "dotenv":
                missing.append("python-dotenv")
            else:
                missing.append(pkg)

    if missing:
        print(f"\n[!] 缺少以下依賴: {', '.join(missing)}")
        install = input("是否自動安裝？(y/n): ").strip().lower()
        if install == "y":
            os.system(f"{sys.executable} -m pip install {' '.join(missing)}")
        else:
            print("請手動執行: pip install -r requirements.txt")
            sys.exit(1)
    else:
        print("[OK] 所有依賴已安裝")

    # 設定 .env
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    env_example = os.path.join(os.path.dirname(__file__), ".env.example")

    if not os.path.exists(env_path):
        if os.path.exists(env_example):
            shutil.copy(env_example, env_path)

        print("\n--- API 金鑰設定 ---")
        api_key = input("請輸入 Binance API Key: ").strip()
        api_secret = input("請輸入 Binance API Secret: ").strip()

        if api_key and api_secret:
            with open(env_path, "w") as f:
                f.write(f"# Binance API\n")
                f.write(f"BINANCE_API_KEY={api_key}\n")
                f.write(f"BINANCE_API_SECRET={api_secret}\n")
                f.write(f"\n# Telegram (optional)\n")
                f.write(f"TELEGRAM_BOT_TOKEN=\n")
                f.write(f"TELEGRAM_CHAT_ID=\n")
            print("[OK] API 金鑰已儲存到 .env")
        else:
            print("[!] 未輸入 API 金鑰，請稍後手動編輯 .env 檔案")
    else:
        print("[OK] .env 已存在")

    # 建立資料目錄
    for d in ["data", "trades"]:
        os.makedirs(d, exist_ok=True)
    print("[OK] 資料目錄已建立")

    print("\n" + "=" * 60)
    print("  設定完成！")
    print("=" * 60)
    print()
    print("下一步：")
    print(f"  1. 執行回測: {sys.executable} run_backtest.py")
    print(f"  2. 啟動機器人: {sys.executable} main.py")
    print()
    print("建議先用回測驗證策略，確認結果為正再啟動實盤交易。")


if __name__ == "__main__":
    main()
