# 槓桿投資管理系統 V2 專業版

將 app.py、requirements.txt、.streamlit/config.toml 覆蓋到原 GitHub repository，
在 GitHub Desktop Commit 後 Push，Streamlit Cloud 會自動更新。

## 密碼保護
Streamlit Cloud → App settings → Secrets，加入：
APP_PASSWORD = "你的密碼"

## 資料保存
免費 Streamlit Cloud 不保證本機檔案永久保存。本版可下載完整 JSON 備份，
下次使用時再上傳還原。
