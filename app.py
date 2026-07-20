
import json
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="YW Wealth OS", page_icon="📊", layout="wide")



st.markdown("""
<style>
.stApp {background:#F5F7FB; color:#183153;}
.block-container {padding-top:1rem; padding-bottom:2rem;}
[data-testid="stSidebar"] {
    background:#FFFFFF;
    border-right:1px solid #E5EAF2;
}
[data-testid="stMetric"] {
    background:#FFFFFF;
    border:1px solid #E5EAF2;
    padding:18px;
    border-radius:18px;
    box-shadow:0 8px 22px rgba(20,43,76,.06);
}
[data-testid="stMetricLabel"] {
    font-weight:700;
    color:#66758A;
}
[data-testid="stMetricValue"] {
    color:#183153;
}
.hero {
    background:linear-gradient(135deg,#EDF4FF,#FFFFFF);
    border:1px solid #E5EAF2;
    border-radius:22px;
    padding:22px 24px;
    margin:8px 0 18px 0;
}
.card {
    background:#FFFFFF;
    border:1px solid #E5EAF2;
    border-radius:18px;
    padding:18px 20px;
    box-shadow:0 8px 22px rgba(20,43,76,.06);
    margin-bottom:1rem;
}
.green {color:#248A57; font-weight:800;}
.yellow {color:#C68900; font-weight:800;}
.orange {color:#D16800; font-weight:800;}
.red {color:#C93C3C; font-weight:800;}
.small {color:#66758A; font-size:.88rem;}
</style>
""", unsafe_allow_html=True)


DEFAULTS = {
    "loan":12540000.0,"usable_funds":10000000.0,"rate":2.5,"years":30,"grace":24,
    "income":170000.0,"fixed":70000.0,"saving":30000.0,
    "voo":.50,"qqq":.20,"tw":.15,"cash":.15,
    "months":6,"completed_months":0,
    "fee":0.1,"bank":"國泰世華","bank_fx":32.33,
    "fx_green":31.5,"fx_yellow":33.0,"fx_orange":34.0,
}
if "settings" not in st.session_state:
    st.session_state.settings = DEFAULTS.copy()
if "trades" not in st.session_state:
    st.session_state.trades = pd.DataFrame(columns=["日期","商品","市場","成交價","匯率","股數","手續費","備註"])
if "fx_records" not in st.session_state:
    st.session_state.fx_records = pd.DataFrame(columns=["日期","銀行","買入匯率","換匯USD","台幣成本","備註"])

@st.cache_data(ttl=900, show_spinner=False)
def market_data():
    mapping={"VOO":"VOO","QQQ":"QQQ","0050":"0050.TW","USD/TWD":"TWD=X","S&P500":"^GSPC"}
    out={}
    for name,ticker in mapping.items():
        try:
            h=yf.Ticker(ticker).history(period="1y",auto_adjust=False)["Close"].dropna()
            p=float(h.iloc[-1]); prev=float(h.iloc[-2]) if len(h)>1 else p
            out[name]={"price":p,"change":p/prev-1,"low":float(h.min()),"high":float(h.max()),"avg":float(h.mean())}
        except Exception:
            out[name]={"price":None,"change":None,"low":None,"high":None,"avg":None}
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

def fx_signal(fx,s):
    if fx<=s["fx_green"]: return "綠燈","可提前換 1–2 個月需求",1.25,"green"
    if fx<=s["fx_yellow"]: return "黃燈","照原計畫分批換匯",1.0,"yellow"
    if fx<=s["fx_orange"]: return "橘燈","本月換匯降至 65%",.65,"orange"
    return "紅燈","非必要可延後換匯",.35,"red"


def save_payload():
    return {
        "settings":st.session_state.settings,
        "trades":st.session_state.trades.to_dict(orient="records"),
        "fx_records":st.session_state.fx_records.to_dict(orient="records"),
        "saved_at":datetime.now().isoformat()
    }

M=market_data()
S=st.session_state.settings

with st.sidebar:
    st.header("核心設定")
    S["loan"]=st.number_input("總貸款本金（計息基礎）",value=float(S["loan"]),step=100000.0)
    S["usable_funds"]=st.number_input(
        "實際可運用資金",
        value=float(S.get("usable_funds",10000000.0)),
        min_value=0.0,
        max_value=float(S["loan"]),
        step=100000.0
    )
    refinanced_amount=max(0.0,S["loan"]-S["usable_funds"])
    st.caption(f"其中 NT${refinanced_amount:,.0f} 用於代償舊房貸，不納入投資建倉。")
    S["rate"]=st.number_input("年利率（%）",value=float(S["rate"]),step=.05)
    S["years"]=st.number_input("貸款年限",value=int(S["years"]),min_value=1)
    S["grace"]=st.number_input("寬限期（月）",value=int(S["grace"]),min_value=0)
    S["income"]=st.number_input("家庭月收入",value=float(S["income"]),step=5000.0)
    S["fixed"]=st.number_input("生活＋固定支出",value=float(S["fixed"]),step=5000.0)
    S["saving"]=st.number_input("安全儲蓄目標",value=float(S["saving"]),step=5000.0)

    st.divider(); st.subheader("配置")
    S["voo"]=st.slider("VOO",0,100,int(S["voo"]*100))/100
    S["qqq"]=st.slider("QQQ",0,100,int(S["qqq"]*100))/100
    S["tw"]=st.slider("0050",0,100,int(S["tw"]*100))/100
    S["cash"]=st.slider("現金",0,100,int(S["cash"]*100))/100
    total_pct=S["voo"]+S["qqq"]+S["tw"]+S["cash"]
    st.caption(f"合計：{total_pct:.0%}")
    if abs(total_pct-1)>1e-9: st.error("配置必須等於 100%")

    S["months"]=st.number_input("建倉月數",value=int(S["months"]),min_value=1,max_value=24)
    S["completed_months"]=st.number_input("已完成月份",value=int(S["completed_months"]),min_value=0,max_value=int(S["months"]))
    S["fee"]=st.number_input("定期定額每筆手續費USD",value=float(S["fee"]),step=.1)

    st.divider(); st.subheader("國泰換匯")
    S["bank"]=st.text_input("銀行",value=S["bank"])
    S["bank_fx"]=st.number_input("美元買入價",value=float(S["bank_fx"]),step=.01,format="%.4f")
    S["fx_green"]=st.number_input("綠燈上限",value=float(S["fx_green"]),step=.1)
    S["fx_yellow"]=st.number_input("黃燈上限",value=float(S["fx_yellow"]),step=.1)
    S["fx_orange"]=st.number_input("橘燈上限",value=float(S["fx_orange"]),step=.1)
    st.session_state.settings=S

    st.divider()
    st.download_button("下載完整備份",json.dumps(save_payload(),ensure_ascii=False,indent=2),
                       f"investment_backup_{date.today()}.json","application/json",use_container_width=True)
    restore=st.file_uploader("還原備份 JSON",type=["json"])
    if restore and st.button("執行還原",use_container_width=True):
        data=json.load(restore)
        st.session_state.settings.update(data.get("settings",{}))
        st.session_state.trades=pd.DataFrame(data.get("trades",[]))
        st.session_state.fx_records=pd.DataFrame(data.get("fx_records",[]))
        st.rerun()

annual=S["rate"]/100
monthly_pay=monthly_payment(S["loan"],annual,S["years"]*12,S["grace"])
interest_only=S["loan"]*annual/12
safe_left=S["income"]-S["fixed"]-S["saving"]-monthly_pay
market_fx=M["USD/TWD"]["price"] or 32.19
bank_fx=S["bank_fx"]
light,fx_text,fx_factor,fx_class=fx_signal(bank_fx,S)

usable_funds=S.get("usable_funds",10000000.0)
refinanced_amount=max(0.0,S["loan"]-usable_funds)
capital_efficiency=usable_funds/S["loan"] if S["loan"] else 0
strategic_cash=usable_funds*S["cash"]
investable=usable_funds*(1-S["cash"])
monthly_total=investable/S["months"]
risky=S["voo"]+S["qqq"]+S["tw"]
monthly_us_twd=monthly_total*(S["voo"]+S["qqq"])/risky
monthly_0050=monthly_total*S["tw"]/risky
standard_usd=monthly_us_twd/bank_fx
suggested_usd=standard_usd*fx_factor
voo_usd=suggested_usd*S["voo"]/(S["voo"]+S["qqq"])
qqq_usd=suggested_usd-voo_usd
twd_needed=suggested_usd*bank_fx
progress=S["completed_months"]/S["months"] if S["months"] else 0

st.title("YW Wealth OS")
st.caption("1,254 萬總貸款｜1,000 萬可運用資金｜國泰定期定額、換匯、房貸與風險管理")

overall="依原計畫執行"
overall_class="green"
if safe_left<0:
    overall="先降低槓桿，寬限期後現金流不足"; overall_class="red"
elif monthly_pay/max(S["income"],1)>.40:
    overall="可執行但需維持較高現金比例"; overall_class="orange"

st.markdown(
    f'<div class="hero"><div class="{overall_class}">📌 今日建議：{overall}</div>'
    f'<div style="margin-top:8px"><b>美元：</b>{light}｜{fx_text}</div>'
    f'<div style="margin-top:6px"><b>本月操作：</b>換 US${suggested_usd:,.0f}，'
    f'VOO 定期定額 US${voo_usd:,.0f}，QQQ 定期定額 US${qqq_usd:,.0f}，'
    f'0050 預算 NT${monthly_0050:,.0f}</div></div>',
    unsafe_allow_html=True
)

finance_cols=st.columns(4)
finance_cols[0].metric("總貸款本金",f"NT${S['loan']:,.0f}",help="利息與月付金均以此金額計算")
finance_cols[1].metric("實際可運用資金",f"NT${usable_funds:,.0f}",help="可用於投資配置與保留現金的總額")
finance_cols[2].metric("代償舊房貸",f"NT${refinanced_amount:,.0f}",help="由台新直接清償前一銀行，無法動用")
finance_cols[3].metric("資金運用效率",f"{capital_efficiency:.1%}",help="實際可運用資金 ÷ 總貸款本金")

st.info(
    f"你目前負擔 **NT${S['loan']:,.0f}** 的貸款利息，"
    f"但投資與現金配置只能使用 **NT${usable_funds:,.0f}**；"
    f"另有 **NT${refinanced_amount:,.0f}** 已用於代償舊房貸。"
)

market_cols=st.columns(5)
for col,key in zip(market_cols,["VOO","QQQ","0050","USD/TWD","S&P500"]):
    p,ch=M[key]["price"],M[key]["change"]
    col.metric(key,"暫無資料" if p is None else f"{p:,.2f}",None if ch is None else f"{ch:+.2%}")

tabs=st.tabs(["🏠 指揮中心","💳 國泰操作清單","📅 進度中心","💵 換匯紀錄","📒 交易帳本","📊 資產配置","🏦 房貸","⚠️ 壓力測試","🗓️ 月報"])

with tabs[0]:
    c=st.columns(4)
    c[0].metric("寬限期月息（按1,254萬）",f"NT${interest_only:,.0f}")
    c[1].metric("寬限期後月付（按1,254萬）",f"NT${monthly_pay:,.0f}")
    c[2].metric("可運用本金",f"NT${usable_funds:,.0f}")
    c[3].metric("建倉完成率",f"{progress:.0%}")
    d=st.columns(3)
    d[0].metric("扣支出後餘額",f"NT${safe_left:,.0f}")
    d[1].metric("代償舊房貸",f"NT${refinanced_amount:,.0f}")
    d[2].metric("資金運用效率",f"{capital_efficiency:.1%}")
    st.progress(progress,text=f"已完成 {S['completed_months']} / {S['months']} 個月")

with tabs[1]:
    st.subheader("本月國泰操作清單")
    checklist=pd.DataFrame([
        ["1","國泰世華換匯",f"US${suggested_usd:,.0f}",f"需準備 NT${twd_needed:,.0f}"],
        ["2","國泰證券 VOO 定期定額",f"US${voo_usd:,.0f}",f"手續費 US${S['fee']:.1f}"],
        ["3","國泰證券 QQQ 定期定額",f"US${qqq_usd:,.0f}",f"手續費 US${S['fee']:.1f}"],
        ["4","0050",f"NT${monthly_0050:,.0f}","依當月價格買進"],
    ],columns=["步驟","操作","金額","備註"])
    st.dataframe(checklist,use_container_width=True,hide_index=True)
    if st.button("✅ 本月已完成",type="primary"):
        if S["completed_months"]<S["months"]:
            S["completed_months"]+=1
            st.session_state.settings=S
            st.success("已更新建倉進度。請下載完整備份保存。")
            st.rerun()

with tabs[2]:
    st.metric("建倉進度",f"{S['completed_months']} / {S['months']} 月")
    st.progress(progress)
    remaining_months=max(0,S["months"]-S["completed_months"])
    remaining_capital=monthly_total*remaining_months
    c=st.columns(3)
    c[0].metric("剩餘月份",remaining_months)
    c[1].metric("剩餘預計投入（不含現金）",f"NT${remaining_capital:,.0f}")
    c[2].metric("戰略現金（取自1,000萬）",f"NT${strategic_cash:,.0f}")

with tabs[3]:
    with st.form("fx_form",clear_on_submit=True):
        a,b,c,d=st.columns(4)
        dt=a.date_input("日期",date.today())
        bank=b.text_input("銀行",value=S["bank"])
        rate=c.number_input("買入匯率",value=float(bank_fx),step=.01,format="%.4f")
        usd=d.number_input("換匯USD",min_value=0.0,step=1000.0)
        note=st.text_input("備註")
        if st.form_submit_button("新增換匯"):
            row=pd.DataFrame([{"日期":str(dt),"銀行":bank,"買入匯率":rate,"換匯USD":usd,"台幣成本":rate*usd,"備註":note}])
            st.session_state.fx_records=pd.concat([st.session_state.fx_records,row],ignore_index=True)
            st.rerun()
    st.session_state.fx_records=st.data_editor(st.session_state.fx_records,num_rows="dynamic",use_container_width=True)
    if not st.session_state.fx_records.empty:
        x=st.session_state.fx_records.copy()
        for c in ["買入匯率","換匯USD","台幣成本"]:
            x[c]=pd.to_numeric(x[c],errors="coerce").fillna(0)
        total_usd=x["換匯USD"].sum(); total_twd=x["台幣成本"].sum()
        avg=total_twd/total_usd if total_usd else 0
        m=st.columns(3)
        m[0].metric("累積美元",f"US${total_usd:,.0f}")
        m[1].metric("累積台幣成本",f"NT${total_twd:,.0f}")
        m[2].metric("平均換匯",f"{avg:.4f}")

with tabs[4]:
    with st.form("trade_form",clear_on_submit=True):
        a,b,c,d=st.columns(4)
        dt=a.date_input("日期",date.today(),key="trade_date")
        product=b.selectbox("商品",["VOO","QQQ","0050"])
        market=c.selectbox("市場",["美股","台股"])
        price=d.number_input("成交價",min_value=0.0)
        e,f,g=st.columns(3)
        fx=e.number_input("匯率",value=float(bank_fx))
        qty=f.number_input("股數",min_value=0.0,step=.001)
        fee=g.number_input("手續費",min_value=0.0,value=float(S["fee"]))
        note=st.text_input("備註",key="trade_note")
        if st.form_submit_button("新增交易"):
            row=pd.DataFrame([{"日期":str(dt),"商品":product,"市場":market,"成交價":price,"匯率":fx,"股數":qty,"手續費":fee,"備註":note}])
            st.session_state.trades=pd.concat([st.session_state.trades,row],ignore_index=True)
            st.rerun()
    st.session_state.trades=st.data_editor(st.session_state.trades,num_rows="dynamic",use_container_width=True)
    L=ledger(st.session_state.trades)
    if not L.empty: st.dataframe(L,use_container_width=True,hide_index=True)

with tabs[5]:
    L=ledger(st.session_state.trades)
    holdings=L.groupby("商品")["股數"].sum().to_dict() if not L.empty else {}
    values={
        "VOO":holdings.get("VOO",0)*(M["VOO"]["price"] or 690)*bank_fx,
        "QQQ":holdings.get("QQQ",0)*(M["QQQ"]["price"] or 725)*bank_fx,
        "0050":holdings.get("0050",0)*(M["0050"]["price"] or 220),
        "現金":strategic_cash
    }
    targets={"VOO":S["voo"],"QQQ":S["qqq"],"0050":S["tw"],"現金":S["cash"]}
    total=sum(values.values()); rows=[]
    for k,v in values.items():
        cur=v/total if total else 0; diff=cur-targets[k]
        action="維持" if abs(diff)<=.02 else ("暫停買進" if diff>0 else "優先買進")
        rows.append([k,v,cur,targets[k],diff,action])
    df=pd.DataFrame(rows,columns=["資產","市值","目前比例","目標比例","偏離","建議"])
    st.dataframe(df,use_container_width=True,hide_index=True)
    st.plotly_chart(px.pie(df,values="市值",names="資產",hole=.5,title="資產配置"),use_container_width=True)

with tabs[6]:
    m=st.columns(4)
    m[0].metric("計息本金",f"NT${S['loan']:,.0f}")
    m[1].metric("可運用資金",f"NT${usable_funds:,.0f}")
    m[2].metric("代償舊房貸",f"NT${refinanced_amount:,.0f}")
    m[3].metric("寬限期月息",f"NT${interest_only:,.0f}")
    A=amortization(S["loan"],annual,S["years"]*12,S["grace"])
    yearly=A.assign(年度=((A["月份"]-1)//12)+1).groupby("年度",as_index=False).agg({"利息":"sum","本金":"sum","月付金":"sum","期末本金":"last"})
    st.plotly_chart(px.line(yearly,x="年度",y="期末本金",title="房貸餘額"),use_container_width=True)
    st.dataframe(yearly,use_container_width=True,hide_index=True)

with tabs[7]:
    rows=[]
    for drop in [0,-.1,-.2,-.3,-.4,-.5]:
        assets=investable*(1+drop)+strategic_cash
        rows.append([drop,assets,assets-S["loan"],assets/S["loan"]])
    df=pd.DataFrame(rows,columns=["市場跌幅","可運用資產市值","扣除1,254萬貸款後淨值","資產/貸款"])
    st.dataframe(df,use_container_width=True,hide_index=True)
    st.plotly_chart(px.bar(df,x="市場跌幅",y="扣除1,254萬貸款後淨值",title="市場下跌壓力"),use_container_width=True)

with tabs[8]:
    L=ledger(st.session_state.trades)
    invested=float(L["台幣成本"].sum()) if not L.empty else 0
    fx_count=len(st.session_state.fx_records)
    report=pd.DataFrame([
        ["總貸款本金",f"NT${S['loan']:,.0f}"],
        ["實際可運用資金",f"NT${usable_funds:,.0f}"],
        ["代償舊房貸",f"NT${refinanced_amount:,.0f}"],
        ["資金運用效率",f"{capital_efficiency:.1%}"],
        ["已完成建倉月份",f"{S['completed_months']} / {S['months']}"],
        ["累積交易投入",f"NT${invested:,.0f}"],
        ["換匯紀錄筆數",fx_count],
        ["本月建議換匯",f"US${suggested_usd:,.0f}"],
        ["本月 VOO 定期定額",f"US${voo_usd:,.0f}"],
        ["本月 QQQ 定期定額",f"US${qqq_usd:,.0f}"],
        ["本月 0050 預算",f"NT${monthly_0050:,.0f}"],
    ],columns=["項目","內容"])
    st.dataframe(report,use_container_width=True,hide_index=True)

st.caption("操作建議為規則式試算，不是保證報酬或匯率預測。房貸利息按總貸款 1,254 萬計算，投資配置按可運用資金 1,000 萬計算。")
