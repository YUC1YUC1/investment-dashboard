
import json
from datetime import date, datetime
import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="槓桿投資管理系統 V3", page_icon="📊", layout="wide")

st.markdown("""
<style>
.stApp {background:#F7F9FC;}
.block-container {padding-top:1.2rem;}
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
.good {color:#2E9D62; font-weight:800;}
.warn {color:#E59B2F; font-weight:800;}
.bad {color:#D94B4B; font-weight:800;}
.small {color:#6B7C93; font-size:.88rem;}
div[data-testid="stDataFrame"] {background:#fff; border:1px solid #E8EDF5; border-radius:16px;}
</style>
""", unsafe_allow_html=True)

DEFAULTS = {
    "loan":12540000.0,"rate":2.5,"years":30,"grace":24,
    "income":170000.0,"fixed":100000.0,"saving":30000.0,
    "voo":.50,"qqq":.20,"tw":.15,"cash":.15,
    "months":6,"fee":3.0,"fx_alert":34.0
}
if "settings" not in st.session_state:
    st.session_state.settings = DEFAULTS.copy()
if "trades" not in st.session_state:
    st.session_state.trades = pd.DataFrame(
        columns=["日期","商品","市場","成交價","匯率","股數","手續費","備註"]
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
        else:
            st.error("密碼錯誤")
    st.stop()

@st.cache_data(ttl=900, show_spinner=False)
def fetch_prices():
    mapping={"VOO":"VOO","QQQ":"QQQ","0050":"0050.TW","USD/TWD":"TWD=X"}
    out={}
    for name,ticker in mapping.items():
        try:
            s=yf.Ticker(ticker).history(period="5d", auto_adjust=False)["Close"].dropna()
            p=float(s.iloc[-1]); prev=float(s.iloc[-2]) if len(s)>1 else p
            out[name]={"price":p,"change":p/prev-1}
        except Exception:
            out[name]={"price":None,"change":None}
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

P=fetch_prices(); S=st.session_state.settings

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
    S["fx_alert"]=st.number_input("匯率警戒上限",value=float(S["fx_alert"]),min_value=0.0)
    st.session_state.settings=S
    backup={"settings":S,"trades":st.session_state.trades.to_dict(orient="records"),"time":datetime.now().isoformat()}
    st.download_button("下載完整備份",json.dumps(backup,ensure_ascii=False,indent=2),
                       f"investment_backup_{date.today()}.json","application/json",use_container_width=True)
    restore=st.file_uploader("還原備份 JSON",type=["json"])
    if restore and st.button("執行還原",use_container_width=True):
        data=json.load(restore)
        st.session_state.settings.update(data.get("settings",{}))
        st.session_state.trades=pd.DataFrame(data.get("trades",[]))
        st.rerun()

st.title("槓桿投資管理系統")
st.caption("V3 白色專業版｜即時市場、建倉、交易帳本、房貸與風險控管")

annual=S["rate"]/100
monthly_pay=monthly_payment(S["loan"],annual,S["years"]*12,S["grace"])
interest_only=S["loan"]*annual/12
safe_left=S["income"]-S["fixed"]-S["saving"]-monthly_pay
fx_now=P["USD/TWD"]["price"] or 32.16

if safe_left<0:
    advice="目前建議：先降低貸款本金或投資規模，寬限期後現金流不足。"; cls="bad"
elif monthly_pay/max(S["income"],1)>.40:
    advice="目前建議：維持較高現金比例，房貸占收入偏高。"; cls="warn"
elif fx_now>S["fx_alert"]:
    advice="目前建議：美元高於警戒線，本月可放慢換匯速度。"; cls="warn"
else:
    advice="目前建議：維持原計畫，不需要因短期波動改變配置。"; cls="good"

st.markdown(f'<div class="advice"><div class="{cls}">📌 {advice}</div><div class="small">系統依現金流、房貸占收入與匯率警戒值產生提示。</div></div>',unsafe_allow_html=True)

market_cols=st.columns(4)
for col,key in zip(market_cols,["VOO","QQQ","0050","USD/TWD"]):
    p,ch=P[key]["price"],P[key]["change"]
    col.metric(key,"暫無資料" if p is None else f"{p:,.2f}",None if ch is None else f"{ch:+.2%}")

summary=st.columns(4)
summary[0].metric("寬限期月息",f"NT${interest_only:,.0f}")
summary[1].metric("寬限期後月付",f"NT${monthly_pay:,.0f}")
summary[2].metric("房貸占收入",f"{monthly_pay/S['income']:.1%}" if S["income"] else "—")
summary[3].metric("扣支出後餘額",f"NT${safe_left:,.0f}")

tabs=st.tabs(["總覽","本月行動","交易帳本","資產配置","房貸","壓力測試","20年情境"])

with tabs[0]:
    L=ledger(st.session_state.trades)
    holdings=L.groupby("商品")["股數"].sum().to_dict() if not L.empty else {}
    voo_p=P["VOO"]["price"] or 690; qqq_p=P["QQQ"]["price"] or 725; tw_p=P["0050"]["price"] or 220
    cash_now=st.number_input("目前現金 TWD",value=float(S["loan"]*S["cash"]),step=10000.0)
    values={"VOO":holdings.get("VOO",0)*voo_p*fx_now,"QQQ":holdings.get("QQQ",0)*qqq_p*fx_now,
            "0050":holdings.get("0050",0)*tw_p,"現金":cash_now}
    total_assets=sum(values.values()); total_cost=float(L["台幣成本"].sum()) if not L.empty else 0
    pnl=total_assets-cash_now-total_cost
    cards=st.columns(4)
    cards[0].metric("總資產",f"NT${total_assets:,.0f}")
    cards[1].metric("淨資產",f"NT${total_assets-S['loan']:,.0f}")
    cards[2].metric("投資損益",f"NT${pnl:,.0f}")
    cards[3].metric("資產／貸款",f"{total_assets/S['loan']:.2f}x" if S["loan"] else "—")
    left,right=st.columns(2)
    with left: st.plotly_chart(px.pie(values=list(values.values()),names=list(values.keys()),hole=.5,title="目前資產配置"),use_container_width=True)
    with right:
        df=pd.DataFrame({"資產":list(values.keys()),"市值":list(values.values())})
        st.plotly_chart(px.bar(df,x="資產",y="市值",title="各資產市值"),use_container_width=True)

with tabs[1]:
    if abs(total_pct-1)>1e-9:
        st.error("請先將目標配置調整為 100%。")
    else:
        investable=S["loan"]*(1-S["cash"]); monthly=investable/S["months"]
        risky=S["voo"]+S["qqq"]+S["tw"]
        us_twd=monthly*(S["voo"]+S["qqq"])/risky; tw_twd=monthly*S["tw"]/risky
        usd=us_twd/fx_now; voo_usd=usd*S["voo"]/(S["voo"]+S["qqq"]); qqq_usd=usd-voo_usd
        voo_qty=max(0,(voo_usd-S["fee"])/(P["VOO"]["price"] or 690))
        qqq_qty=max(0,(qqq_usd-S["fee"])/(P["QQQ"]["price"] or 725))
        action=st.columns(4)
        action[0].metric("本月換匯",f"US${usd:,.0f}")
        action[1].metric("買進 VOO",f"{voo_qty:,.3f} 股")
        action[2].metric("買進 QQQ",f"{qqq_qty:,.3f} 股")
        action[3].metric("0050 預算",f"NT${tw_twd:,.0f}")
        plan=pd.DataFrame({"月份":[f"第{i}月" for i in range(1,S["months"]+1)],
                           "換匯USD":[usd]*S["months"],"VOO股數":[voo_qty]*S["months"],
                           "QQQ股數":[qqq_qty]*S["months"],"0050預算TWD":[tw_twd]*S["months"],
                           "累積完成率":[i/S["months"] for i in range(1,S["months"]+1)]})
        st.dataframe(plan,use_container_width=True,hide_index=True)

with tabs[2]:
    with st.form("add_trade",clear_on_submit=True):
        a,b,c,d=st.columns(4)
        dt=a.date_input("日期",date.today()); product=b.selectbox("商品",["VOO","QQQ","0050"])
        market_name=c.selectbox("市場",["美股","台股"]); price=d.number_input("成交價",min_value=0.0)
        e,f,g=st.columns(3)
        fx_input=e.number_input("匯率",value=float(fx_now)); qty=f.number_input("股數",min_value=0.0,step=.001)
        fee=g.number_input("手續費",min_value=0.0,value=float(S["fee"])); note=st.text_input("備註")
        if st.form_submit_button("新增交易",type="primary"):
            row=pd.DataFrame([{"日期":str(dt),"商品":product,"市場":market_name,"成交價":price,
                               "匯率":fx_input,"股數":qty,"手續費":fee,"備註":note}])
            st.session_state.trades=pd.concat([st.session_state.trades,row],ignore_index=True); st.rerun()
    st.session_state.trades=st.data_editor(st.session_state.trades,num_rows="dynamic",use_container_width=True)
    L=ledger(st.session_state.trades)
    if not L.empty:
        st.dataframe(L,use_container_width=True,hide_index=True)
        st.download_button("下載交易 CSV",L.to_csv(index=False).encode("utf-8-sig"),"交易紀錄.csv","text/csv")

with tabs[3]:
    L=ledger(st.session_state.trades); holdings=L.groupby("商品")["股數"].sum().to_dict() if not L.empty else {}
    values={"VOO":holdings.get("VOO",0)*(P["VOO"]["price"] or 690)*fx_now,
            "QQQ":holdings.get("QQQ",0)*(P["QQQ"]["price"] or 725)*fx_now,
            "0050":holdings.get("0050",0)*(P["0050"]["price"] or 220),"現金":S["loan"]*S["cash"]}
    targets={"VOO":S["voo"],"QQQ":S["qqq"],"0050":S["tw"],"現金":S["cash"]}
    total_value=sum(values.values()); rows=[]
    for k,v in values.items():
        current=v/total_value if total_value else 0; diff=current-targets[k]
        action="維持" if abs(diff)<=.02 else ("暫停買進" if diff>0 else "優先買進")
        rows.append([k,v,current,targets[k],diff,action])
    st.dataframe(pd.DataFrame(rows,columns=["資產","市值","目前比例","目標比例","偏離","建議"]),use_container_width=True,hide_index=True)

with tabs[4]:
    A=amortization(S["loan"],annual,S["years"]*12,S["grace"])
    yearly=A.assign(年度=((A["月份"]-1)//12)+1).groupby("年度",as_index=False).agg({"利息":"sum","本金":"sum","月付金":"sum","期末本金":"last"})
    st.plotly_chart(px.line(yearly,x="年度",y="期末本金",title="房貸餘額"),use_container_width=True)
    st.dataframe(yearly,use_container_width=True,hide_index=True)

with tabs[5]:
    investable=S["loan"]*(1-S["cash"]); rows=[]
    for drop in [0,-.1,-.2,-.3,-.4,-.5]:
        assets=investable*(1+drop)+S["loan"]*S["cash"]
        rows.append([drop,assets,assets-S["loan"],assets/S["loan"]])
    df=pd.DataFrame(rows,columns=["市場跌幅","總資產","淨資產","資產/貸款"])
    st.dataframe(df,use_container_width=True,hide_index=True)
    st.plotly_chart(px.bar(df,x="市場跌幅",y="淨資產",title="市場下跌壓力"),use_container_width=True)

with tabs[6]:
    A=amortization(S["loan"],annual,S["years"]*12,S["grace"]); rows=[]
    for year in range(21):
        bal=S["loan"] if year==0 else float(A.iloc[min(year*12-1,len(A)-1)]["期末本金"])
        for ret,label in [(.05,"保守5%"),(.07,"基準7%"),(.09,"樂觀9%")]:
            assets=S["loan"]*(1-S["cash"])*(1+ret)**year+S["loan"]*S["cash"]*(1.015)**year
            rows.append([year,label,assets-bal])
    st.plotly_chart(px.line(pd.DataFrame(rows,columns=["年度","情境","淨資產"]),
                            x="年度",y="淨資產",color="情境",title="20 年淨資產情境"),
                    use_container_width=True)

st.caption("市場資料來自 Yahoo Finance / yfinance，可能延遲。請定期下載 JSON 備份。")
