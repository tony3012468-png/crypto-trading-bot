# 🚀 雲端部署指南 - Render 或 Replit

你的交易機器人現在可以 24/7 在雲端運行，每日 7 PM 自動生成報告！

## 📋 前置準備

### 1. 更新密鑰（重要！）
在部署前，**必須更新你的 API 密鑰**：

- **Binance API Key & Secret**: 登入 Binance，生成新的 API 密鑰
- **Telegram Bot Token & Chat ID**: 確保有效

### 2. 準備部署

克隆或上傳你的項目到 GitHub：
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/crypto-trading-bot.git
git branch -M main
git push -u origin main
```

---

## 🎯 選項 A：在 Render 上部署（推薦）

### Step 1: 在 Render 上建立帳戶
訪問 [render.com](https://render.com) 並用 GitHub 帳戶註冊

### Step 2: 建立新 Web Service

1. 點擊 "New +" → 選擇 "Web Service"
2. 連接你的 GitHub 倉庫
3. 設定以下信息：
   - **Name**: `crypto-trading-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main_with_scheduler.py`
   - **Instance Type**: `Free` (或 Starter $7/月)

### Step 3: 添加環境變量

在 Render 儀表板中，找到 "Environment" 部分，添加：

```
BINANCE_API_KEY=你的API密鑰
BINANCE_API_SECRET=你的API秘密
TELEGRAM_BOT_TOKEN=你的BOT TOKEN
TELEGRAM_CHAT_ID=你的CHAT ID
```

### Step 4: 部署

點擊 "Create Web Service"，Render 會自動部署你的應用。

**注意**：
- Free tier 會在 15 分鐘無活動後進入休眠（但報告調度器仍會運行）
- 為了 24/7 運行，建議升級到 Starter ($7/月) 或更高

---

## 🎯 選項 B：在 Replit 上部署

### Step 1: 在 Replit 上建立帳戶
訪問 [replit.com](https://replit.com) 並用 GitHub 帳戶註冊

### Step 2: 導入項目

1. 點擊 "Create Repl"
2. 選擇 "Import from GitHub"
3. 輸入你的倉庫 URL

### Step 3: 添加環境變量

在 Replit 編輯器右側，找到 "Secrets" (🔑 圖標)，添加：

```
BINANCE_API_KEY=你的API密鑰
BINANCE_API_SECRET=你的API秘密
TELEGRAM_BOT_TOKEN=你的BOT TOKEN
TELEGRAM_CHAT_ID=你的CHAT ID
```

### Step 4: 運行

點擊頂部的 "Run" 按鈕開始運行

### Step 5: 保持運行（可選但推薦）

Replit Free 會在非活動後停止。為了 24/7 運行，考慮：
- 升級到 Replit Pro ($7/月)
- 或使用外部服務定期 ping（如 Uptime Robot）

---

## 📊 監控你的機器人

### 查看日誌

- **Render**: 在儀表板 "Logs" 標籤查看實時日誌
- **Replit**: 在編輯器下方的 "Console" 查看輸出

### 每日報告

每天晚上 7 PM (UTC+8)，你會在 Telegram 上收到：
1. 📋 交易摘要（文本）
2. 📊 完整圖表（圖片）

---

## 🔧 常見問題

### 報告沒有生成？
1. 檢查 Telegram 設定是否正確
2. 查看日誌中是否有錯誤信息
3. 確保交易日誌文件存在於 `trades/` 目錄

### 機器人停止運行？
- Replit Free 可能會自動停止
- 可用 [Uptime Robot](https://uptimerobot.com) 定期 ping 保持活動
- 或升級到付費方案

### 如何修改報告時間？
編輯 `main_with_scheduler.py` 中的：
```python
self.report_hour = 19  # 改為需要的小時 (0-23, UTC+8)
self.report_minute = 0
```

然後重新推送到 GitHub，Render/Replit 會自動部署。

---

## 💰 成本估計

| 平台 | 免費方案 | 推薦方案 | 價格 |
|------|--------|--------|------|
| **Render** | Free (15 分鐘休眠) | Starter | $7/月 |
| **Replit** | Free (限制) | Pro | $7/月 |

---

## 🔒 安全建議

1. **不要在代碼中放密鑰** - 使用環境變量
2. **定期更新 API 密鑰** - 每 3 個月輪換一次
3. **使用 IP 白名單** - 在 Binance 設定中限制 API 訪問 IP
4. **監控交易** - 定期檢查日誌和報告

---

## ❓ 需要幫助？

如有問題，檢查：
1. 日誌輸出中的錯誤信息
2. 環境變量是否正確設定
3. API 密鑰是否有效
4. Telegram Bot 是否正確配置

---

**祝你的交易機器人 24/7 盈利！🚀**
