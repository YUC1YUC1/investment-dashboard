import json
from datetime import date, datetime
import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="槓桿投資 V2", page_icon="📊", layout="wide")

DEFAULTS = {
    "loan": 12540000.0, "rate": 2.5, "years": 30, "grace": 24,
    "income": 170000.0, "fixed": 100000.0, "saving": 30000.0,
    "voo": .50, "qqq": .20, "tw": .15, "cash": .15,
    "months": 6, "fee": 3.0, "fx_alert": 34.0,
}
if "settings" not in st.session_state:
    st.session_state.settings = DEFAULTS.copy()
if "trades" not in st.session_state:
    st.session_state.trades = pd.DataFrame(
        columns=["日期","商品","市場","成交價","匯率","股數","手續費","備註"]
    )

try:
    password = st.secrets.get("APP_PASSWORD", "")
except Exception:
    password = ""
if password and not st.session_state.get("auth"):
    st.title("🔒 私人投資儀表板")
    pwd = st.text_input("密碼", type="password")
    if st.button("登入", type="primary"):
        if pwd == password:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("密碼錯誤")
    st.stop()

@st.cache_data(ttl=900, show_spinner=False)
def prices():
    mapping = {"VOO":"VOO","QQQ":"QQQ","0050":"0050.TW","USD/TWD":"TWD=X"}
    result = {}
    for name, ticker in mapping.items():
        try:
            hist = yf.Ticker(ticker).history(period="5d", auto_adjust=False)["Close"].dropna()
            p = float(hist.iloc[-1])
            prev = float(hist.iloc[-2]) if len(hist)>1 else p
            result[name] = (p, p/prev-1)
        except Exception:
            result[name] = (None, None)
    return result

def pmt(principal, annual, months, grace):
    r = annual/12
    n = max(1, months-grace)
    if r == 0:
        return principal/n
    return principal*r*(1+r)**n/((1+r)**n-1)

def amort(principal, annual, months, grace):
    monthly = annual/12
    pay = pmt(principal, annual, months, grace)
    bal = principal
    rows = []
    for m in range(1, months+1):
        interest = bal*monthly
        payment = interest if m<=grace else min(pay, bal+interest)
        principal_paid = 0 if m<=grace else max(0, payment-interest)
        bal = max(0, bal-principal_paid)
        rows.append([m, interest, principal_paid, payment, bal])
    return pd.DataFrame(rows, columns=["月份","利息","本金","月付金","期末本金"])

def ledger(df):
    if df.empty:
        return df.copy()
    x = df.copy()
    for c in ["成交價","匯率","股數","手續費"]:
        x[c] = pd.to_numeric(x[c], errors="coerce").fillna(0)
    x["原幣金額"] = x["成交價"]*x["股數"]+x["手續費"]
    x["台幣成本"] = x.apply(
        lambda r: r["原幣金額"]*r["匯率"] if r["市場"]=="美股" else r["原幣金額"], axis=1
    )
    return x

S = st.session_state.settings
P = prices()

with st.sidebar:
    st.header("⚙️ 核心設定")
    S["loan"] = st.number_input("貸款本金", value=float(S["loan"]), step=100000.0)
    S["rate"] = st.number_input("年利率（%）", value=float(S["rate"]), step=.05)
    S["years"] = st.number_input("貸款年限", value=int(S["years"]), min_value=1)
    S["grace"] = st.number_input("寬限期（月）", value=int(S["grace"]), min_value=0)
    S["income"] = st.number_input("家庭月收入", value=float(S["income"]), step=5000.0)
    S["fixed"] = st.number_input("生活＋固定支出", value=float(S["fixed"]), step=5000.0)
    S["saving"] = st.number_input("安全儲蓄目標", value=float(S["saving"]), step=5000.0)
    st.divider()
    st.header("🎯 目標配置")
    S["voo"] = st.slider("VOO",0,100,int(S["voo"]*100))/100
    S["qqq"] = st.slider("QQQ",0,100,int(S["qqq"]*100))/100
    S["tw"] = st.slider("0050",0,100,int(S["tw"]*100))/100
    S["cash"] = st.slider("現金",0,100,int(S["cash"]*100))/100
    total = S["voo"]+S["qqq"]+S["tw"]+S["cash"]
    st.write(f"合計：**{total:.0%}**")
    if abs(total-1) > 1e-9:
        st.error("配置必須合計 100%")
    S["months"] = st.number_input("建倉月數", value=int(S["months"]), min_value=1, max_value=24)
    S["fee"] = st.number_input("美股ETF每筆手續費USD", value=float(S["fee"]), min_value=0.0)
    S["fx_alert"] = st.number_input("匯率警戒上限", value=float(S["fx_alert"]), min_value=0.0)
    st.session_state.settings = S

    backup = {
        "settings": S,
        "trades": st.session_state.trades.to_dict(orient="records"),
        "time": datetime.now().isoformat(),
    }
    st.download_button(
        "💾 下載完整備份",
        json.dumps(backup, ensure_ascii=False, indent=2),
        f"investment_backup_{date.today()}.json",
        "application/json",
        use_container_width=True,
    )
    restore = st.file_uploader("還原備份 JSON", type=["json"])
    if restore and st.button("執行還原", use_container_width=True):
        data = json.load(restore)
        st.session_state.settings.update(data.get("settings", {}))
        st.session_state.trades = pd.DataFrame(data.get("trades", []))
        st.rerun()

st.title("📊 槓桿投資管理系統 V2 專業版")
st.caption("即時市場、交易帳本、建倉規劃、再平衡、房貸與壓力測試。")

cols = st.columns(4)
for col, key in zip(cols, ["VOO","QQQ","0050","USD/TWD"]):
    price, change = P[key]
    col.metric(key, "暫無資料" if price is None else f"{price:,.2f}",
               None if change is None else f"{change:+.2%}")

annual = S["rate"]/100
monthly_pay = pmt(S["loan"], annual, S["years"]*12, S["grace"])
interest_only = S["loan"]*annual/12
safe_left = S["income"]-S["fixed"]-S["saving"]-monthly_pay

m = st.columns(4)
m[0].metric("寬限期月息", f"NT${interest_only:,.0f}")
m[1].metric("寬限期後月付", f"NT${monthly_pay:,.0f}")
m[2].metric("房貸占收入", f"{monthly_pay/S['income']:.1%}" if S["income"] else "—")
m[3].metric("扣支出後餘額", f"NT${safe_left:,.0f}")

tabs = st.tabs(["總覽","交易帳本","建倉","再平衡","房貸","壓力測試","20年情境"])

with tabs[0]:
    L = ledger(st.session_state.trades)
    holdings = L.groupby("商品")["股數"].sum().to_dict() if not L.empty else {}
    fx = P["USD/TWD"][0] or 32.16
    voo_p, qqq_p, tw_p = P["VOO"][0] or 690, P["QQQ"][0] or 725, P["0050"][0] or 220
    cash_now = st.number_input("目前現金 TWD", value=float(S["loan"]*S["cash"]), step=10000.0)
    values = {
        "VOO": holdings.get("VOO",0)*voo_p*fx,
        "QQQ": holdings.get("QQQ",0)*qqq_p*fx,
        "0050": holdings.get("0050",0)*tw_p,
        "現金": cash_now,
    }
    total_assets = sum(values.values())
    cost = float(L["台幣成本"].sum()) if not L.empty else 0
    c = st.columns(4)
    c[0].metric("總資產", f"NT${total_assets:,.0f}")
    c[1].metric("淨資產", f"NT${total_assets-S['loan']:,.0f}")
    c[2].metric("投資損益", f"NT${total_assets-cash_now-cost:,.0f}")
    c[3].metric("資產/貸款", f"{total_assets/S['loan']:.2f}x" if S["loan"] else "—")
    st.plotly_chart(px.pie(values=list(values.values()), names=list(values.keys()),
                           hole=.45, title="目前資產配置"), use_container_width=True)

with tabs[1]:
    with st.form("trade", clear_on_submit=True):
        a,b,c,d = st.columns(4)
        dt = a.date_input("日期", date.today())
        product = b.selectbox("商品", ["VOO","QQQ","0050"])
        market_name = c.selectbox("市場", ["美股","台股"])
        price = d.number_input("成交價", min_value=0.0)
        e,f,g = st.columns(3)
        fx_in = e.number_input("匯率", value=float(P["USD/TWD"][0] or 32.16))
        qty = f.number_input("股數", min_value=0.0, step=.001)
        fee = g.number_input("手續費", min_value=0.0, value=float(S["fee"]))
        note = st.text_input("備註")
        if st.form_submit_button("新增交易", type="primary"):
            row = pd.DataFrame([{
                "日期":str(dt),"商品":product,"市場":market_name,"成交價":price,
                "匯率":fx_in,"股數":qty,"手續費":fee,"備註":note
            }])
            st.session_state.trades = pd.concat([st.session_state.trades,row], ignore_index=True)
            st.rerun()
    st.session_state.trades = st.data_editor(
        st.session_state.trades, num_rows="dynamic", use_container_width=True
    )
    L = ledger(st.session_state.trades)
    if not L.empty:
        st.dataframe(L, use_container_width=True, hide_index=True)
        st.download_button("下載交易CSV", L.to_csv(index=False).encode("utf-8-sig"),
                           "交易紀錄.csv", "text/csv")

with tabs[2]:
    if abs(total-1) > 1e-9:
        st.error("先把配置調成 100%")
    else:
        fx = P["USD/TWD"][0] or 32.16
        voo_p, qqq_p = P["VOO"][0] or 690, P["QQQ"][0] or 725
        investable = S["loan"]*(1-S["cash"])
        monthly = investable/S["months"]
        risk_total = S["voo"]+S["qqq"]+S["tw"]
        us_twd = monthly*(S["voo"]+S["qqq"])/risk_total
        tw_twd = monthly*S["tw"]/risk_total
        usd = us_twd/fx
        voo_usd = usd*S["voo"]/(S["voo"]+S["qqq"])
        qqq_usd = usd-voo_usd
        voo_qty = max(0,(voo_usd-S["fee"])/voo_p)
        qqq_qty = max(0,(qqq_usd-S["fee"])/qqq_p)
        c = st.columns(4)
        c[0].metric("本月換匯", f"US${usd:,.0f}")
        c[1].metric("VOO", f"{voo_qty:,.3f} 股")
        c[2].metric("QQQ", f"{qqq_qty:,.3f} 股")
        c[3].metric("0050預算", f"NT${tw_twd:,.0f}")
        plan = pd.DataFrame({
            "月份":[f"第{i}月" for i in range(1,S["months"]+1)],
            "換匯USD":[usd]*S["months"], "VOO股數":[voo_qty]*S["months"],
            "QQQ股數":[qqq_qty]*S["months"], "0050預算":[tw_twd]*S["months"],
        })
        st.dataframe(plan, use_container_width=True, hide_index=True)

with tabs[3]:
    L = ledger(st.session_state.trades)
    holdings = L.groupby("商品")["股數"].sum().to_dict() if not L.empty else {}
    fx = P["USD/TWD"][0] or 32.16
    values = {
        "VOO": holdings.get("VOO",0)*(P["VOO"][0] or 690)*fx,
        "QQQ": holdings.get("QQQ",0)*(P["QQQ"][0] or 725)*fx,
        "0050": holdings.get("0050",0)*(P["0050"][0] or 220),
        "現金": S["loan"]*S["cash"],
    }
    target = {"VOO":S["voo"],"QQQ":S["qqq"],"0050":S["tw"],"現金":S["cash"]}
    total_value = sum(values.values())
    rows=[]
    for k,v in values.items():
        cur = v/total_value if total_value else 0
        diff = cur-target[k]
        action = "維持" if abs(diff)<=.02 else ("暫停買進" if diff>0 else "優先買進")
        rows.append([k,v,cur,target[k],diff,action])
    df = pd.DataFrame(rows, columns=["資產","市值","目前比例","目標比例","偏離","建議"])
    st.dataframe(df, use_container_width=True, hide_index=True)

with tabs[4]:
    A = amort(S["loan"], annual, S["years"]*12, S["grace"])
    yearly = A.assign(年度=((A["月份"]-1)//12)+1).groupby("年度",as_index=False).agg(
        {"利息":"sum","本金":"sum","月付金":"sum","期末本金":"last"}
    )
    st.plotly_chart(px.line(yearly,x="年度",y="期末本金",title="房貸餘額"),
                    use_container_width=True)
    st.dataframe(yearly, use_container_width=True, hide_index=True)

with tabs[5]:
    investable = S["loan"]*(1-S["cash"])
    rows=[]
    for drop in [0,-.1,-.2,-.3,-.4,-.5]:
        assets = investable*(1+drop)+S["loan"]*S["cash"]
        rows.append([drop,assets,assets-S["loan"],assets/S["loan"]])
    df = pd.DataFrame(rows, columns=["跌幅","總資產","淨資產","資產/貸款"])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.plotly_chart(px.bar(df,x="跌幅",y="淨資產",title="市場下跌壓力"),
                    use_container_width=True)

with tabs[6]:
    A = amort(S["loan"], annual, S["years"]*12, S["grace"])
    rows=[]
    for year in range(21):
        bal = S["loan"] if year==0 else float(A.iloc[min(year*12-1,len(A)-1)]["期末本金"])
        for ret,label in [(.05,"保守5%"),(.07,"基準7%"),(.09,"樂觀9%")]:
            assets = S["loan"]*(1-S["cash"])*(1+ret)**year + S["loan"]*S["cash"]*(1.015)**year
            rows.append([year,label,assets-bal])
    df = pd.DataFrame(rows,columns=["年度","情境","淨資產"])
    st.plotly_chart(px.line(df,x="年度",y="淨資產",color="情境",
                            title="20年淨資產情境"), use_container_width=True)

st.caption("市場資料來自 Yahoo Finance / yfinance，可能延遲。免費 Streamlit Cloud 不保證本機檔案永久保存，請定期下載 JSON 備份。")
