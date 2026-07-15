
# 1254萬槓桿投資管理系統（網頁版）

## 本機執行
1. 安裝 Python 3.11 或以上版本。
2. 開啟命令提示字元，進入此資料夾。
3. 執行：
   pip install -r requirements.txt
   streamlit run app.py
4. 瀏覽器會自動開啟。

## 免費部署到 Streamlit Community Cloud
1. 建立 GitHub 帳號與一個新的 repository。
2. 上傳 `app.py`、`requirements.txt`。
3. 在 Streamlit Community Cloud 選擇該 repository，入口檔設為 `app.py`。
4. 部署完成後會得到一個可用手機與電腦開啟的網址。

## 功能
- 自動抓取 VOO、QQQ、0050 與 USD/TWD
- 6 個月建倉指揮中心
- 房貸 30 年試算
- 資產配置與再平衡
- -10% 至 -50% 壓力測試
- 20 年淨資產情境

## 注意
市場資料可能延遲或暫時無法取得。此工具是個人財務規劃試算，不構成投資建議。
