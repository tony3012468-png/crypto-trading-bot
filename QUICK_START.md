# ⚡ 快速啟動 - 24 小時自動交易 + 每日報告

你的機器人現在已完全配置好！按以下步驟部署到雲端：

---

## 🔐 Step 1: 更新並保護你的密鑰

### 重要！不要在代碼中硬編碼密鑰

1. **Binance API**
   - 登入 [Binance](https://www.binance.com)
   - 去 "API Management"
   - **刪除舊的 API 密鑰** (在 .env 中的)
   - 創建新的 API 密鑰
   - 複製 Key 和 Secret

2. **Telegram Bot**
   - 用 @BotFather 創建新 Bot (可選)
   - 或確認你的現有 Bot Token 有效
   - 確認 Chat ID (`TELEGRAM_CHAT_ID`) 正確

3. **保存你的密鑰** (臨時，用於部署)
   ```
   BINANCE_API_KEY=xxxxx
   BINANCE_API_SECRET=xxxxx
   TELEGRAM_BOT_TOKEN=xxxxx
   TELEGRAM_CHAT_ID=xxxxx
   ```

---

## 📤 Step 2: 上傳到 GitHub

```bash
# 如果還沒初始化 git
git init
git add .
git commit -m "Crypto trading bot with daily reports"

# 創建 GitHub 倉庫並上傳
git remote add origin https://github.com/YOUR_USERNAME/crypto-trading-bot.git
git branch -M main
git push -u origin main
```

---

## 🚀 Step 3: 選擇部署平台

### 推薦: Render (最簡單)

1. 去 [render.com](https://render.com)
2. 用 GitHub 登入
3. 點 "New +" → "Web Service"
4. 選擇你的倉庫
5. 設定:
   - **Name**: `crypto-trading-bot`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main_with_scheduler.py`
   - **Instance**: Starter ($7/月) 或 Free (會休眠)

6. 添加環境變量:
   ```
   BINANCE_API_KEY=xxxxx
   BINANCE_API_SECRET=xxxxx
   TELEGRAM_BOT_TOKEN=xxxxx
   TELEGRAM_CHAT_ID=xxxxx
   ```

7. 點 "Create Web Service" 並等待部署完成 (~2 分鐘)

### 或: Replit

1. 去 [replit.com](https://replit.com)
2. 點 "Create Repl" → "Import from GitHub"
3. 輸入你的倉庫 URL
4. 在右側 "Secrets" (🔑) 添加環境變量
5. 點 "Run" 啟動

---

## ✅ Step 4: 驗證部署

1. **查看日誌**
   - Render: 儀表板 → "Logs" 標籤
   - Replit: Console 窗口
   - 應該看到 "機器人已啟動" 和 "報告調度器已啟動"

2. **測試 Telegram 通知**
   - 檢查你的 Telegram 是否收到機器人啟動通知

3. **等待首份報告**
   - 每天晚上 7 PM (UTC+8) 自動生成報告
   - 或者手動測試: 修改 `main_with_scheduler.py` 中的時間為當前時間 + 1 分鐘

---

## 📊 每日報告包含

每晚 7 PM，你會收到:
- 📋 **交易摘要** (Telegram 文本)
  - 總交易數、勝率、累計盈虧
  - 平均獲利/虧損、利潤因子

- 📈 **詳細圖表** (Telegram 圖片)
  - 盈虧曲線
  - 交易勝負比例
  - 單筆交易分佈
  - 交易對績效對比
  - 時間分佈
  - 統計信息

- 🎯 **優化建議**
  - 基於當日績效自動生成

---

## 🔄 管理你的機器人

### 修改配置
編輯 `config.yaml` 並推送到 GitHub:
```bash
git add config.yaml
git commit -m "Update config"
git push
```
Render/Replit 會自動重新部署

### 修改報告時間
編輯 `main_with_scheduler.py`:
```python
self.report_hour = 19  # 改為想要的小時
self.report_minute = 0
```

### 停止機器人
在 Render/Replit 儀表板中:
- Render: 點 "Suspend Service"
- Replit: 停止運行

---

## 💰 成本

- **Render Starter**: $7/月 (推薦)
- **Replit Pro**: $7/月
- **或**: 使用免費方案 + Uptime Robot 保活

---

## 🆘 如果出錯

1. **查看日誌** - 檢查詳細的錯誤信息
2. **驗證環境變量** - 確保 API Key 正確
3. **檢查交易文件** - `trades/` 目錄是否有交易記錄
4. **測試 Telegram** - 確保 Bot Token 有效

---

## 🎉 完成！

你的交易機器人現在:
- ✅ 24 小時自動運行
- ✅ 每日自動生成報告
- ✅ 通過 Telegram 推播通知
- ✅ 不需要本地電腦開著

**記得每 3 個月更新一次 API 密鑰! 🔒**

---

需要詳細部署步驟？查看 `DEPLOYMENT_GUIDE.md`
