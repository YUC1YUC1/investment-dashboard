
import json
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="槓桿投資管理系統 V5", page_icon="📊", layout="wide")

st.markdown("""
<style>
.stApp {background:#F7F9FC;}
.block-container {padding-top:1.1rem; padding-bottom:2rem;}
[data-testid="stSidebar"] {background:#FFFFFF; border-right:1px solid #E8EDF5;}
[data-testid="stMetric"] {
  background:#FFFFFF; border:1px solid #E8EDF5; padding:18px;
  border-radius:18px; box-shadow:0 8px 24px rgba(24,49,83,.06);
}
[data-testid="stMetricLabel"] {font-weight:700; color:#6B7C93;}
[data-testid="stMetricValue"] {font-size:1.65rem; color:#183153;}
.advice {
  background:linear-gradient(135deg,#EDF4FF,#F8FBFF);
  border:1px solid #DCE8FF; border-radius:20px; padding:20px 22px;
  margin:8px 0 18px 0;
}
.green {color:#2E9D62; font-weight:800;}
.yellow {color:#D99000; font-weight:800;}
.orange {color:#D96B00; font-weight:800;}
.red {color:#D94B4B; font-weight:800;}
.small {color:#6B7C93; font-size:.88rem;}
div[data-testid="stDataFrame"] {background:#fff; border:1px solid #E8EDF5; border-radius:16px;}
</style>
""", unsafe_allow_html=True)

DEFAULTS = {
    "loan":12540000.0,"rate":2.5,"years":30,"grace":24,
    "income":170000.0,"fixed":70000.0,"saving":30000.0,
    "voo":.50,"qqq":.20,"tw":.15,"cash":.15,
    "months":6,"fee":3.0,
    "fx_green":31.5,"fx_yellow":33.0,"fx_orange":34.0,
    "bank_name":"國泰世華","bank_fx":32.33,
    "order_mode":"定期定額"
}
if "settings" not in st.session_state:
    st.session_state.settings = DEFAULTS.copy()
if "trades" not in st.session_state:
    st.session_state.trades = pd.DataFrame(
        columns=["日期","商品","市場","成交價","匯率","股數","手續費","備註"]
    )
if "fx_records" not in st.session_state:
    st.session_state.fx_records = pd.DataFrame(
        columns=["日期","銀行","買入匯率","換匯USD","台幣成本","備註"]
    )

try:
    app_password = st.secrets.get("APP_PASSWORD","")
except Exception:
    app_password = ""

if app_password and not st.session_state.get("auth"):
    st.title("🔒 私人投資儀表板")
    pwd = st.text_input("密碼", type="password")
    if st.button("登入", type="primary"):
        if pwd == app_password:
            st.session_state.auth = True
            st.rerun()
        st.error("密碼錯誤")
    st.stop()

@st.cache_data(ttl=900, show_spinner=False)
def fetch_market():
    mapping = {
        "VOO":"VOO","QQQ":"QQQ","0050":"0050.TW",
        "USD/TWD":"TWD=X","S&P 500":"^GSPC"
    }
    out={}
    for name,ticker in mapping.items():
        try:
            hist=yf.Ticker(ticker).history(period="1y", auto_adjust=False)["Close"].dropna()
            latest=float(hist.iloc[-1])
            prev=float(hist.iloc[-2]) if len(hist)>1 else latest
            out[name]={
                "price":latest,
                "change":latest/prev-1 if prev else 0,
                "low_1y":float(hist.min()),
                "high_1y":float(hist.max()),
                "avg_1y":float(hist.mean()),
            }
        except Exception:
            out[name]={"price":None,"change":None,"low_1y":None,"high_1y":None,"avg_1y":None}
    return out

def monthly_payment(principal, annual, months, grace):
    r=annual/12; n=max(1,months-grace)
    return principal/n if r==0 else principal*r*(1+r)**n/((1+r)**n-1)

def amortization(principal, annual, months, grace):
    r=annual/12; pay=monthly_payment(principal,annual,months,grace)
    bal=principal; rows=[]
    for m in range(1,months+1):
        interest=bal*r
        payment=interest if m<=grace else min(pay,bal+interest)
        principal_paid=0 if m<=grace else max(0,payment-interest)
        bal=max(0,bal-principal_paid)
        rows.append([m,interest,principal_paid,payment,bal])
    return pd.DataFrame(rows,columns=["月份","利息","本金","月付金","期末本金"])

def ledger(df):
    if df.empty: return df.copy()
    x=df.copy()
    for c in ["成交價","匯率","股數","手續費"]:
        x[c]=pd.to_numeric(x[c],errors="coerce").fillna(0)
    x["原幣金額"]=x["成交價"]*x["股數"]+x["手續費"]
    x["台幣成本"]=x.apply(lambda r:r["原幣金額"]*r["匯率"] if r["市場"]=="美股" else r["原幣金額"],axis=1)
    return x

def fx_signal(fx, s):
    if fx <= s["fx_green"]:
        return "綠燈","適合積極換匯，可提前準備未來 1–2 個月美元需求。","green",1.25
    if fx <= s["fx_yellow"]:
        return "黃燈","依原定計畫分批換匯，不追價也不必停手。","yellow",1.0
    if fx <= s["fx_orange"]:
        return "橘燈","匯率偏高，建議本月只換原計畫的 50%–75%。","orange",0.65
    return "紅燈","匯率明顯偏高，沒有立即需求時可延後換匯。","red",0.35

M=fetch_market(); S=st.session_state.settings

with st.sidebar:
    st.header("設定")
    S["loan"]=st.number_input("貸款本金",value=float(S["loan"]),step=100000.0)
    S["rate"]=st.number_input("年利率（%）",value=float(S["rate"]),step=.05)
    S["years"]=st.number_input("貸款年限",value=int(S["years"]),min_value=1)
    S["grace"]=st.number_input("寬限期（月）",value=int(S["grace"]),min_value=0)
    S["income"]=st.number_input("家庭月收入",value=float(S["income"]),step=5000.0)
    S["fixed"]=st.number_input("生活＋固定支出",value=float(S["fixed"]),step=5000.0)
    S["saving"]=st.number_input("安全儲蓄目標",value=float(S["saving"]),step=5000.0)

    st.divider(); st.subheader("目標配置")
    S["voo"]=st.slider("VOO",0,100,int(S["voo"]*100))/100
    S["qqq"]=st.slider("QQQ",0,100,int(S["qqq"]*100))/100
    S["tw"]=st.slider("0050",0,100,int(S["tw"]*100))/100
    S["cash"]=st.slider("現金",0,100,int(S["cash"]*100))/100
    total_pct=S["voo"]+S["qqq"]+S["tw"]+S["cash"]
    st.caption(f"配置合計：{total_pct:.0%}")
    if abs(total_pct-1)>1e-9: st.error("配置必須合計 100%")
    S["months"]=st.number_input("建倉月數",value=int(S["months"]),min_value=1,max_value=24)
    S["fee"]=st.number_input("美股 ETF 每筆手續費 USD",value=float(S["fee"]),min_value=0.0)
    S["order_mode"]=st.selectbox("國泰下單方式",["定期定額","定期定股"],index=0 if S["order_mode"]=="定期定額" else 1)

    st.divider(); st.subheader("實際換匯成本")
    S["bank_name"]=st.text_input("銀行",value=S["bank_name"])
    S["bank_fx"]=st.number_input("銀行美元買入價（銀行賣給你）",value=float(S["bank_fx"]),step=.01,format="%.4f")
    st.caption("所有換匯成本、需要準備的台幣與建議股數，都使用這個實際買入價計算。")

    st.divider(); st.subheader("美元燈號門檻")
    S["fx_green"]=st.number_input("綠燈上限",value=float(S["fx_green"]),step=.1)
    S["fx_yellow"]=st.number_input("黃燈上限",value=float(S["fx_yellow"]),step=.1)
    S["fx_orange"]=st.number_input("橘燈上限",value=float(S["fx_orange"]),step=.1)
    st.session_state.settings=S

    backup={
        "settings":S,
        "trades":st.session_state.trades.to_dict(orient="records"),
        "fx_records":st.session_state.fx_records.to_dict(orient="records"),
        "time":datetime.now().isoformat()
    }
    st.download_button("下載完整備份",json.dumps(backup,ensure_ascii=False,indent=2),
                       f"investment_backup_{date.today()}.json","application/json",use_container_width=True)
    restore=st.file_uploader("還原備份 JSON",type=["json"])
    if restore and st.button("執行還原",use_container_width=True):
        data=json.load(restore)
        st.session_state.settings.update(data.get("settings",{}))
        st.session_state.trades=pd.DataFrame(data.get("trades",[]))
        st.session_state.fx_records=pd.DataFrame(data.get("fx_records",[]))
        st.rerun()

st.title("槓桿投資管理系統")
st.caption("V5｜銀行實際買入價、換匯紀錄、定期定額／定期定股建議、建倉、房貸與風險控管")

annual=S["rate"]/100
monthly_pay=monthly_payment(S["loan"],annual,S["years"]*12,S["grace"])
interest_only=S["loan"]*annual/12
safe_left=S["income"]-S["fixed"]-S["saving"]-monthly_pay

market_fx=M["USD/TWD"]["price"] or 32.19
bank_fx=S["bank_fx"]
spread=bank_fx-market_fx
fx_light,fx_text,fx_class,fx_factor=fx_signal(bank_fx,S)

st.markdown(
    f'<div class="advice"><div class="{fx_class}">💵 {S["bank_name"]}換匯：{fx_light}</div>'
    f'<div style="margin-top:8px">實際買入價 <b>{bank_fx:.4f}</b>｜市場參考價 {market_fx:.4f}｜價差 {spread:+.4f}</div>'
    f'<div style="margin-top:5px">{fx_text}</div></div>',
    unsafe_allow_html=True
)

market_cols=st.columns(5)
for col,key in zip(market_cols,["VOO","QQQ","0050","USD/TWD","S&P 500"]):
    p,ch=M[key]["price"],M[key]["change"]
    col.metric(key,"暫無資料" if p is None else f"{p:,.2f}",None if ch is None else f"{ch:+.2%}")

tabs=st.tabs(["首頁","換匯儀表板","本月行動","換匯紀錄","交易帳本","資產配置","房貸","壓力測試"])

with tabs[0]:
    c=st.columns(4)
    c[0].metric("寬限期月息",f"NT${interest_only:,.0f}")
    c[1].metric("寬限期後月付",f"NT${monthly_pay:,.0f}")
    c[2].metric("房貸占收入",f"{monthly_pay/S['income']:.1%}" if S["income"] else "—")
    c[3].metric("扣支出後餘額",f"NT${safe_left:,.0f}")

with tabs[1]:
    st.subheader("美元換匯儀表板")
    item=M["USD/TWD"]
    c=st.columns(5)
    c[0].metric("市場參考價",f"{market_fx:.4f}")
    c[1].metric("銀行實際買入價",f"{bank_fx:.4f}")
    c[2].metric("銀行價差",f"{spread:+.4f}")
    c[3].metric("一年平均","—" if item["avg_1y"] is None else f"{item['avg_1y']:.4f}")
    c[4].metric("換匯燈號",fx_light)
    score=92 if bank_fx<=S["fx_green"] else 75 if bank_fx<=S["fx_yellow"] else 55 if bank_fx<=S["fx_orange"] else 35
    st.metric("換匯適合度",f"{score} / 100")
    st.caption("燈號使用你實際會成交的銀行買入價，不再使用市場賣出／中間價計算成本。")

with tabs[2]:
    if abs(total_pct-1)>1e-9:
        st.error("請先將配置調整為 100%。")
    else:
        investable=S["loan"]*(1-S["cash"])
        monthly=investable/S["months"]
        risky=S["voo"]+S["qqq"]+S["tw"]
        us_twd=monthly*(S["voo"]+S["qqq"])/risky
        tw_twd=monthly*S["tw"]/risky
        standard_usd=us_twd/bank_fx
        suggested_usd=standard_usd*fx_factor
        twd_needed=suggested_usd*bank_fx
        voo_usd=suggested_usd*S["voo"]/(S["voo"]+S["qqq"])
        qqq_usd=suggested_usd-voo_usd
        voo_price=M["VOO"]["price"] or 690
        qqq_price=M["QQQ"]["price"] or 725
        voo_qty=max(0,(voo_usd-S["fee"])/voo_price)
        qqq_qty=max(0,(qqq_usd-S["fee"])/qqq_price)

        c=st.columns(6)
        c[0].metric("標準換匯",f"US${standard_usd:,.0f}")
        c[1].metric("燈號調整後",f"US${suggested_usd:,.0f}")
        c[2].metric("需準備台幣",f"NT${twd_needed:,.0f}")
        c[3].metric("VOO",f"{voo_qty:,.3f} 股")
        c[4].metric("QQQ",f"{qqq_qty:,.3f} 股")
        c[5].metric("0050預算",f"NT${tw_twd:,.0f}")

        if S["order_mode"]=="定期定額":
            st.success("目前建議使用定期定額：每月投入固定金額，較符合你的建倉與現金流規劃。")
            st.write(f"- VOO 每月預算：約 US${voo_usd:,.0f}")
            st.write(f"- QQQ 每月預算：約 US${qqq_usd:,.0f}")
        else:
            st.info("你選擇定期定股：每月股數固定，但所需台幣會隨股價與匯率變動。")
            st.write(f"- VOO 每月：約 {voo_qty:,.3f} 股")
            st.write(f"- QQQ 每月：約 {qqq_qty:,.3f} 股")

with tabs[3]:
    st.subheader("新增換匯紀錄")
    with st.form("fx_form",clear_on_submit=True):
        a,b,c,d=st.columns(4)
        fx_date=a.date_input("日期",date.today())
        bank=b.text_input("銀行",value=S["bank_name"])
        rate_input=c.number_input("買入匯率",value=float(bank_fx),step=.01,format="%.4f")
        usd_amount=d.number_input("換匯USD",min_value=0.0,step=1000.0)
        note=st.text_input("備註")
        if st.form_submit_button("新增換匯紀錄",type="primary"):
            twd_cost=rate_input*usd_amount
            row=pd.DataFrame([{
                "日期":str(fx_date),"銀行":bank,"買入匯率":rate_input,
                "換匯USD":usd_amount,"台幣成本":twd_cost,"備註":note
            }])
            st.session_state.fx_records=pd.concat([st.session_state.fx_records,row],ignore_index=True)
            st.rerun()

    st.session_state.fx_records=st.data_editor(
        st.session_state.fx_records,num_rows="dynamic",use_container_width=True
    )
    if not st.session_state.fx_records.empty:
        x=st.session_state.fx_records.copy()
        for col in ["買入匯率","換匯USD","台幣成本"]:
            x[col]=pd.to_numeric(x[col],errors="coerce").fillna(0)
        total_usd=x["換匯USD"].sum()
        total_twd=x["台幣成本"].sum()
        avg_fx=total_twd/total_usd if total_usd else 0
        c=st.columns(3)
        c[0].metric("累積換匯USD",f"US${total_usd:,.0f}")
        c[1].metric("累積台幣成本",f"NT${total_twd:,.0f}")
        c[2].metric("平均換匯成本",f"{avg_fx:.4f}")
        st.download_button("下載換匯CSV",x.to_csv(index=False).encode("utf-8-sig"),"換匯紀錄.csv","text/csv")

with tabs[4]:
    with st.form("trade_form",clear_on_submit=True):
        a,b,c,d=st.columns(4)
        trade_date=a.date_input("日期",date.today(),key="trade_date")
        product=b.selectbox("商品",["VOO","QQQ","0050"])
        market_name=c.selectbox("市場",["美股","台股"])
        price=d.number_input("成交價",min_value=0.0)
        e,f,g=st.columns(3)
        fx_input=e.number_input("匯率",value=float(bank_fx))
        qty=f.number_input("股數",min_value=0.0,step=.001)
        fee=g.number_input("手續費",min_value=0.0,value=float(S["fee"]))
        note=st.text_input("備註",key="trade_note")
        if st.form_submit_button("新增交易",type="primary"):
            row=pd.DataFrame([{"日期":str(trade_date),"商品":product,"市場":market_name,
                               "成交價":price,"匯率":fx_input,"股數":qty,"手續費":fee,"備註":note}])
            st.session_state.trades=pd.concat([st.session_state.trades,row],ignore_index=True)
            st.rerun()
    st.session_state.trades=st.data_editor(st.session_state.trades,num_rows="dynamic",use_container_width=True)
    L=ledger(st.session_state.trades)
    if not L.empty:
        st.dataframe(L,use_container_width=True,hide_index=True)

with tabs[5]:
    L=ledger(st.session_state.trades)
    holdings=L.groupby("商品")["股數"].sum().to_dict() if not L.empty else {}
    values={
        "VOO":holdings.get("VOO",0)*(M["VOO"]["price"] or 690)*bank_fx,
        "QQQ":holdings.get("QQQ",0)*(M["QQQ"]["price"] or 725)*bank_fx,
        "0050":holdings.get("0050",0)*(M["0050"]["price"] or 220),
        "現金":S["loan"]*S["cash"]
    }
    targets={"VOO":S["voo"],"QQQ":S["qqq"],"0050":S["tw"],"現金":S["cash"]}
    total_value=sum(values.values()); rows=[]
    for k,v in values.items():
        current=v/total_value if total_value else 0
        diff=current-targets[k]
        action="維持" if abs(diff)<=.02 else ("暫停買進" if diff>0 else "優先買進")
        rows.append([k,v,current,targets[k],diff,action])
    st.dataframe(pd.DataFrame(rows,columns=["資產","市值","目前比例","目標比例","偏離","建議"]),use_container_width=True,hide_index=True)

with tabs[6]:
    A=amortization(S["loan"],annual,S["years"]*12,S["grace"])
    yearly=A.assign(年度=((A["月份"]-1)//12)+1).groupby("年度",as_index=False).agg(
        {"利息":"sum","本金":"sum","月付金":"sum","期末本金":"last"}
    )
    st.plotly_chart(px.line(yearly,x="年度",y="期末本金",title="房貸餘額"),use_container_width=True)
    st.dataframe(yearly,use_container_width=True,hide_index=True)

with tabs[7]:
    investable=S["loan"]*(1-S["cash"]); rows=[]
    for drop in [0,-.1,-.2,-.3,-.4,-.5]:
        assets=investable*(1+drop)+S["loan"]*S["cash"]
        rows.append([drop,assets,assets-S["loan"],assets/S["loan"]])
    df=pd.DataFrame(rows,columns=["市場跌幅","總資產","淨資產","資產/貸款"])
    st.dataframe(df,use_container_width=True,hide_index=True)
    st.plotly_chart(px.bar(df,x="市場跌幅",y="淨資產",title="市場下跌壓力"),use_container_width=True)

st.caption("銀行買入價需由你依國泰數位通路當下報價更新。市場參考價與銀行實際成交價可能不同。")
