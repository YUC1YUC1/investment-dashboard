# 槓桿投資管理系統 V4

V4 新增：
- 美元換匯燈號
- 一年匯率區間位置
- 換匯適合度分數
- 依燈號自動調整本月換匯金額
- S&P 500 一年區間位置提示
- 每日總結

更新方式：
1. 解壓縮。
2. 將 app.py、requirements.txt、README.md 與 .streamlit 資料夾覆蓋到原 repository。
3. GitHub Desktop Commit to main。
4. Push origin。
5. Streamlit Cloud 自動重新部署。


## V4.1 設定保存
左側欄新增「儲存目前設定」：
- 按下後，貸款、生活支出、配置比例與換匯門檻會寫入目前網址。
- 請把更新後的網址加入瀏覽器書籤。
- 使用同一網址重新整理或下次開啟，設定會保留。
- 交易紀錄較多，不放在網址中；請使用「下載完整備份 JSON」保存。
