
import math
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="1254萬槓桿投資管理系統",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
[data-testid="stMetricValue"] {font-size: 1.65rem;}
.small-note {color:#666; font-size:.88rem;}
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=900, show_spinner=False)
def fetch_market_data():
    tickers = {
        "VOO": "VOO",
        "QQQ": "QQQ",
        "0050": "0050.TW",
        "USD/TWD": "TWD=X",
        "S&P 500": "^GSPC",
    }
    out = {}
    for name, ticker in tickers.items():
        try:
            data = yf.Ticker(ticker).history(period="5d", auto_adjust=False)
            if data.empty:
                out[name] = None
                continue
            close = float(data["Close"].dropna().iloc[-1])
            prev = float(data["Close"].dropna().iloc[-2]) if len(data["Close"].dropna()) >= 2 else close
            out[name] = {
                "price": close,
                "change_pct": (close / prev - 1) if prev else 0,
                "updated": data.index[-1].strftime("%Y-%m-%d"),
            }
        except Exception:
            out[name] = None
    return out

def monthly_payment(principal, annual_rate, total_months, grace_months):
    monthly_rate = annual_rate / 12
    amort_months = total_months - grace_months
    if monthly_rate == 0:
        return principal / amort_months
    return principal * monthly_rate * (1 + monthly_rate) ** amort_months / ((1 + monthly_rate) ** amort_months - 1)

def build_amortization(principal, annual_rate, total_months, grace_months):
    r = annual_rate / 12
    payment_after_grace = monthly_payment(principal, annual_rate, total_months, grace_months)
    bal = principal
    rows = []
    for m in range(1, total_months + 1):
        interest = bal * r
        if m <= grace_months:
            payment = interest
            principal_paid = 0
        else:
            payment = min(payment_after_grace, bal + interest)
            principal_paid = max(0, payment - interest)
        end_bal = max(0, bal - principal_paid)
        rows.append([m, bal, interest, principal_paid, payment, end_bal])
        bal = end_bal
    return pd.DataFrame(rows, columns=["月份","期初本金","利息","本金","月付金","期末本金"])

def money(x):
    return f"NT${x:,.0f}"

st.title("📊 1254 萬槓桿投資管理系統")
st.caption("即時市場資料 + 建倉規劃 + 房貸現金流 + 壓力測試。市場資料每 15 分鐘快取一次。")

market = fetch_market_data()

with st.sidebar:
    st.header("核心設定")
    loan = st.number_input("貸款本金（TWD）", min_value=0, value=12_540_000, step=100_000)
    rate = st.number_input("年利率", min_value=0.0, value=2.5, step=0.05) / 100
    term_years = st.number_input("貸款年限", min_value=1, value=30, step=1)
    grace_months = st.number_input("寬限期（月）", min_value=0, value=24, step=1)
    family_income = st.number_input("家庭月收入（TWD）", min_value=0, value=170_000, step=5_000)
    fixed_costs = st.number_input("每月生活＋固定支出", min_value=0, value=100_000, step=5_000)

    st.divider()
    st.header("目標配置")
    voo_pct = st.slider("VOO", 0, 100, 50) / 100
    qqq_pct = st.slider("QQQ", 0, 100, 20) / 100
    tw_pct = st.slider("0050", 0, 100, 15) / 100
    cash_pct = st.slider("現金", 0, 100, 15) / 100
    total_pct = voo_pct + qqq_pct + tw_pct + cash_pct
    if abs(total_pct - 1) > 1e-6:
        st.error(f"配置合計目前為 {total_pct:.0%}，請調整為 100%。")

    build_months = st.number_input("建倉月數", min_value=1, max_value=24, value=6, step=1)
    us_fee = st.number_input("美股 ETF 每筆手續費（USD）", min_value=0.0, value=3.0, step=0.5)

# Market cards
st.subheader("即時市場")
cols = st.columns(4)
for col, key in zip(cols, ["VOO","QQQ","0050","USD/TWD"]):
    item = market.get(key)
    if item:
        prefix = "US$" if key in ("VOO","QQQ") else ""
        suffix = "" if key != "USD/TWD" else " TWD"
        col.metric(key, f"{prefix}{item['price']:,.2f}{suffix}", f"{item['change_pct']:+.2%}")
    else:
        col.metric(key, "資料暫時無法取得")

total_months = int(term_years * 12)
grace_interest = loan * rate / 12
post_grace_payment = monthly_payment(loan, rate, total_months, int(grace_months))
safe_balance = family_income - fixed_costs - post_grace_payment

st.subheader("核心風險指標")
m1, m2, m3, m4 = st.columns(4)
m1.metric("寬限期每月利息", money(grace_interest))
m2.metric("寬限期後月付金", money(post_grace_payment))
m3.metric("房貸占家庭收入", f"{post_grace_payment/family_income:.1%}" if family_income else "—")
m4.metric("寬限期後每月餘額", money(safe_balance))

if safe_balance < 0:
    st.error("寬限期結束後，每月現金流為負，這個槓桿規模不建議直接執行。")
elif post_grace_payment / family_income > 0.4:
    st.warning("寬限期後房貸占家庭收入超過 40%，建議降低貸款本金或提高現金部位。")
else:
    st.success("以目前輸入條件，現金流尚可執行，但仍需承受市場大跌與收入變動風險。")

tabs = st.tabs(["建倉指揮中心","資產配置","房貸現金流","壓力測試","20年情境"])

with tabs[0]:
    st.subheader("每月建倉建議")
    if abs(total_pct - 1) < 1e-6:
        investable = loan * (1 - cash_pct)
        monthly_total = investable / build_months
        risky_total_pct = voo_pct + qqq_pct + tw_pct
        us_share = (voo_pct + qqq_pct) / risky_total_pct if risky_total_pct else 0
        tw_share = tw_pct / risky_total_pct if risky_total_pct else 0
        monthly_us_twd = monthly_total * us_share
        monthly_0050_twd = monthly_total * tw_share

        fx = market["USD/TWD"]["price"] if market.get("USD/TWD") else 32.16
        voo_price = market["VOO"]["price"] if market.get("VOO") else 690
        qqq_price = market["QQQ"]["price"] if market.get("QQQ") else 725

        monthly_usd = monthly_us_twd / fx
        voo_budget = monthly_usd * voo_pct / (voo_pct + qqq_pct)
        qqq_budget = monthly_usd - voo_budget
        voo_shares = max(0, (voo_budget - us_fee) / voo_price)
        qqq_shares = max(0, (qqq_budget - us_fee) / qqq_price)

        a,b,c,d = st.columns(4)
        a.metric("本月換匯", f"US${monthly_usd:,.0f}")
        b.metric("VOO", f"{voo_shares:,.3f} 股")
        c.metric("QQQ", f"{qqq_shares:,.3f} 股")
        d.metric("0050 預算", money(monthly_0050_twd))

        plan = pd.DataFrame({
            "月份":[f"第{i}月" for i in range(1,int(build_months)+1)],
            "換匯USD":[monthly_usd]*int(build_months),
            "VOO股數":[voo_shares]*int(build_months),
            "QQQ股數":[qqq_shares]*int(build_months),
            "0050預算TWD":[monthly_0050_twd]*int(build_months),
            "累積完成率":[i/int(build_months) for i in range(1,int(build_months)+1)]
        })
        st.dataframe(plan.style.format({
            "換匯USD":"{:,.0f}","VOO股數":"{:,.3f}","QQQ股數":"{:,.3f}",
            "0050預算TWD":"{:,.0f}","累積完成率":"{:.0%}"
        }), use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("目前持有部位")
    c1,c2,c3,c4 = st.columns(4)
    voo_qty = c1.number_input("VOO 股數", min_value=0.0, value=0.0, step=1.0)
    qqq_qty = c2.number_input("QQQ 股數", min_value=0.0, value=0.0, step=1.0)
    tw_qty = c3.number_input("0050 股數", min_value=0.0, value=0.0, step=100.0)
    cash_now = c4.number_input("現金 TWD", min_value=0.0, value=float(loan*cash_pct), step=10000.0)

    fx = market["USD/TWD"]["price"] if market.get("USD/TWD") else 32.16
    voo_price = market["VOO"]["price"] if market.get("VOO") else 690
    qqq_price = market["QQQ"]["price"] if market.get("QQQ") else 725
    tw_price = market["0050"]["price"] if market.get("0050") else 220

    values = {
        "VOO": voo_qty*voo_price*fx,
        "QQQ": qqq_qty*qqq_price*fx,
        "0050": tw_qty*tw_price,
        "現金": cash_now,
    }
    total_value = sum(values.values())
    alloc = pd.DataFrame({
        "資產": list(values.keys()),
        "目前市值": list(values.values()),
        "目前比例": [v/total_value if total_value else 0 for v in values.values()],
        "目標比例": [voo_pct, qqq_pct, tw_pct, cash_pct]
    })
    alloc["偏離"] = alloc["目前比例"] - alloc["目標比例"]
    alloc["建議"] = alloc["偏離"].apply(lambda x: "維持" if abs(x)<=0.02 else ("暫停買進" if x>0 else "優先買進"))
    st.dataframe(alloc.style.format({"目前市值":"{:,.0f}","目前比例":"{:.1%}","目標比例":"{:.1%}","偏離":"{:+.1%}"}), use_container_width=True, hide_index=True)
    fig = px.pie(alloc, values="目前市值", names="資產", title="目前資產配置")
    st.plotly_chart(fig, use_container_width=True)

with tabs[2]:
    amort = build_amortization(loan, rate, total_months, int(grace_months))
    st.dataframe(amort.head(36).style.format({
        "期初本金":"{:,.0f}","利息":"{:,.0f}","本金":"{:,.0f}","月付金":"{:,.0f}","期末本金":"{:,.0f}"
    }), use_container_width=True, hide_index=True)
    yearly = amort.copy()
    yearly["年度"] = ((yearly["月份"]-1)//12)+1
    yearly = yearly.groupby("年度", as_index=False).agg({"利息":"sum","本金":"sum","月付金":"sum","期末本金":"last"})
    fig = px.line(yearly, x="年度", y="期末本金", title="貸款餘額")
    st.plotly_chart(fig, use_container_width=True)

with tabs[3]:
    investable = loan*(1-cash_pct)
    stress = []
    for drop in [0,-0.1,-0.2,-0.3,-0.4,-0.5]:
        assets = investable*(1+drop) + loan*cash_pct
        net = assets-loan
        stress.append([f"{drop:.0%}",assets,net,assets/loan if loan else 0])
    stress_df = pd.DataFrame(stress,columns=["市場跌幅","總資產","淨資產","資產/貸款"])
    st.dataframe(stress_df.style.format({"總資產":"{:,.0f}","淨資產":"{:,.0f}","資產/貸款":"{:.2f}x"}),use_container_width=True,hide_index=True)
    fig = px.bar(stress_df, x="市場跌幅", y="淨資產", title="不同跌幅下淨資產")
    st.plotly_chart(fig,use_container_width=True)

with tabs[4]:
    years = list(range(0,21))
    amort = build_amortization(loan, rate, total_months, int(grace_months))
    balances = [loan] + [float(amort.iloc[min(y*12-1,len(amort)-1)]["期末本金"]) for y in years[1:]]
    rows=[]
    for y,bal in zip(years,balances):
        for ret,label in [(0.05,"保守5%"),(0.07,"基準7%"),(0.09,"樂觀9%")]:
            asset = loan*(1-cash_pct)*(1+ret)**y + loan*cash_pct*(1.015)**y
            rows.append([y,label,asset-bal])
    proj=pd.DataFrame(rows,columns=["年度","情境","淨資產"])
    fig=px.line(proj,x="年度",y="淨資產",color="情境",title="20年淨資產推估")
    st.plotly_chart(fig,use_container_width=True)
    st.caption("報酬率僅為假設，未扣除稅負、匯差、交易成本與實際市場路徑差異。")

st.divider()
st.markdown('<div class="small-note">資料來源：Yahoo Finance（透過 yfinance）。即時性可能延遲，且資料供應中斷時會使用備援價格。此工具僅供個人規劃，不構成投資建議。</div>', unsafe_allow_html=True)
