
import json
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="槓桿投資管理系統 V4", page_icon="📊", layout="wide")

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
.panel {
  background:#FFFFFF; border:1px solid #E8EDF5; border-radius:18px;
  padding:18px 20px; box-shadow:0 8px 24px rgba(24,49,83,.06);
  margin-bottom:1rem;
}
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
    "income":170000.0,"fixed":100000.0,"saving":30000.0,
    "voo":.50,"qqq":.20,"tw":.15,"cash":.15,
    "months":6,"fee":3.0,
    "fx_green":31.5,"fx_yellow":33.0,"fx_orange":34.0,
    "sp500_buy1":-0.10,"sp500_buy2":-0.20,
}
def load_settings_from_url(defaults):
    settings = defaults.copy()
    numeric_keys = {
        "loan": float, "rate": float, "years": int, "grace": int,
        "income": float, "fixed": float, "saving": float,
        "voo": float, "qqq": float, "tw": float, "cash": float,
        "months": int, "fee": float,
        "fx_green": float, "fx_yellow": float, "fx_orange": float,
        "sp500_buy1": float, "sp500_buy2": float,
    }
    for key, caster in numeric_keys.items():
        try:
            value = st.query_params.get(key)
            if value not in (None, ""):
                settings[key] = caster(value)
        except Exception:
            pass
    return settings

def save_settings_to_url(settings):
    for key, value in settings.items():
        st.query_params[key] = str(value)

if "settings" not in st.session_state:
    st.session_state.settings = load_settings_from_url(DEFAULTS)
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
        st.error("密碼錯誤")
    st.stop()

@st.cache_data(ttl=900, show_spinner=False)
def fetch_market():
    mapping = {
        "VOO":"VOO","QQQ":"QQQ","0050":"0050.TW",
        "USD/TWD":"TWD=X","S&P 500":"^GSPC","DXY":"DX-Y.NYB"
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

def market_position(item):
    p=item["price"]; lo=item["low_1y"]; hi=item["high_1y"]
    if None in (p,lo,hi) or hi==lo: return None
    return (p-lo)/(hi-lo)

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

    st.divider(); st.subheader("美元燈號門檻")
    S["fx_green"]=st.number_input("綠燈上限",value=float(S["fx_green"]),step=.1)
    S["fx_yellow"]=st.number_input("黃燈上限",value=float(S["fx_yellow"]),step=.1)
    S["fx_orange"]=st.number_input("橘燈上限",value=float(S["fx_orange"]),step=.1)
    st.session_state.settings=S

    st.divider()
    st.subheader("儲存設定")
    if st.button("💾 儲存目前設定", use_container_width=True):
        save_settings_to_url(S)
        st.success("已儲存在目前網址。請把這個網址加入書籤；重新整理後會保留設定。")
    if st.button("↩️ 還原預設設定", use_container_width=True):
        st.query_params.clear()
        st.session_state.settings = DEFAULTS.copy()
        st.rerun()
    st.caption("此功能把設定寫入網址參數，不會把帳密或券商資料上傳。交易紀錄仍請使用 JSON 備份。")

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
st.caption("V4｜美元換匯儀表板、每日操作建議、建倉、交易帳本、房貸與壓力測試")

annual=S["rate"]/100
monthly_pay=monthly_payment(S["loan"],annual,S["years"]*12,S["grace"])
interest_only=S["loan"]*annual/12
safe_left=S["income"]-S["fixed"]-S["saving"]-monthly_pay
fx_now=M["USD/TWD"]["price"] or 32.16
fx_light,fx_text,fx_class,fx_factor=fx_signal(fx_now,S)

sp_pos=market_position(M["S&P 500"])
if sp_pos is None:
    stock_text="市場位置暫時無法判斷。"
elif sp_pos<.35:
    stock_text="美股位於一年區間較低位置，可按計畫或略加速投入。"
elif sp_pos>.80:
    stock_text="美股接近一年高檔，建議維持分批，不一次追價。"
else:
    stock_text="美股位於一年區間中段，照原計畫分批即可。"

if safe_left<0:
    overall="先降低槓桿，寬限期後現金流不足。"; overall_class="bad"
elif monthly_pay/max(S["income"],1)>.40:
    overall="投資可執行，但房貸占收入偏高，應保留較多現金。"; overall_class="orange"
else:
    overall="現金流尚可，依紀律分批投入。"; overall_class="green"

st.markdown(
    f'<div class="advice"><div class="{overall_class}">📌 今日總結：{overall}</div>'
    f'<div style="margin-top:8px"><b>美元：</b>{fx_light}｜{fx_text}</div>'
    f'<div style="margin-top:5px"><b>美股：</b>{stock_text}</div></div>',
    unsafe_allow_html=True
)

market_cols=st.columns(6)
for col,key in zip(market_cols,["VOO","QQQ","0050","USD/TWD","S&P 500","DXY"]):
    p,ch=M[key]["price"],M[key]["change"]
    col.metric(key,"暫無資料" if p is None else f"{p:,.2f}",None if ch is None else f"{ch:+.2%}")

tabs=st.tabs(["首頁","美元儀表板","本月行動","交易帳本","資產配置","房貸","壓力測試","20年情境"])

with tabs[0]:
    c=st.columns(4)
    c[0].metric("寬限期月息",f"NT${interest_only:,.0f}")
    c[1].metric("寬限期後月付",f"NT${monthly_pay:,.0f}")
    c[2].metric("房貸占收入",f"{monthly_pay/S['income']:.1%}" if S["income"] else "—")
    c[3].metric("扣支出後餘額",f"NT${safe_left:,.0f}")

    L=ledger(st.session_state.trades)
    holdings=L.groupby("商品")["股數"].sum().to_dict() if not L.empty else {}
    cash_now=st.number_input("目前現金 TWD",value=float(S["loan"]*S["cash"]),step=10000.0)
    values={
        "VOO":holdings.get("VOO",0)*(M["VOO"]["price"] or 690)*fx_now,
        "QQQ":holdings.get("QQQ",0)*(M["QQQ"]["price"] or 725)*fx_now,
        "0050":holdings.get("0050",0)*(M["0050"]["price"] or 220),
        "現金":cash_now
    }
    total_assets=sum(values.values())
    total_cost=float(L["台幣成本"].sum()) if not L.empty else 0
    m=st.columns(4)
    m[0].metric("總資產",f"NT${total_assets:,.0f}")
    m[1].metric("淨資產",f"NT${total_assets-S['loan']:,.0f}")
    m[2].metric("投資損益",f"NT${total_assets-cash_now-total_cost:,.0f}")
    m[3].metric("資產／貸款",f"{total_assets/S['loan']:.2f}x" if S["loan"] else "—")
    left,right=st.columns(2)
    with left: st.plotly_chart(px.pie(values=list(values.values()),names=list(values.keys()),hole=.5,title="目前資產配置"),use_container_width=True)
    with right:
        df=pd.DataFrame({"資產":list(values.keys()),"市值":list(values.values())})
        st.plotly_chart(px.bar(df,x="資產",y="市值",title="各資產市值"),use_container_width=True)

with tabs[1]:
    st.subheader("美元換匯儀表板")
    item=M["USD/TWD"]
    pos=market_position(item)
    c=st.columns(4)
    c[0].metric("目前匯率",f"{fx_now:,.2f}")
    c[1].metric("一年平均","—" if item["avg_1y"] is None else f"{item['avg_1y']:.2f}")
    c[2].metric("一年低點","—" if item["low_1y"] is None else f"{item['low_1y']:.2f}")
    c[3].metric("一年高點","—" if item["high_1y"] is None else f"{item['high_1y']:.2f}")
    st.markdown(f'<div class="panel"><div class="{fx_class}" style="font-size:1.35rem">{fx_light}｜{fx_text}</div></div>',unsafe_allow_html=True)

    if pos is not None:
        st.progress(min(max(pos,0),1), text=f"目前位於一年區間的 {pos:.0%} 位置")
    score=100
    if fx_now>S["fx_orange"]: score=35
    elif fx_now>S["fx_yellow"]: score=55
    elif fx_now>S["fx_green"]: score=75
    else: score=92
    st.metric("換匯適合度",f"{score} / 100")
    st.caption("評分依你自訂門檻與一年區間位置產生，並非匯率預測。")

with tabs[2]:
    if abs(total_pct-1)>1e-9:
        st.error("請先將配置調整為 100%。")
    else:
        investable=S["loan"]*(1-S["cash"])
        monthly=investable/S["months"]
        risky=S["voo"]+S["qqq"]+S["tw"]
        us_twd=monthly*(S["voo"]+S["qqq"])/risky
        tw_twd=monthly*S["tw"]/risky
        standard_usd=us_twd/fx_now
        suggested_usd=standard_usd*fx_factor
        voo_usd=suggested_usd*S["voo"]/(S["voo"]+S["qqq"])
        qqq_usd=suggested_usd-voo_usd
        voo_qty=max(0,(voo_usd-S["fee"])/(M["VOO"]["price"] or 690))
        qqq_qty=max(0,(qqq_usd-S["fee"])/(M["QQQ"]["price"] or 725))
        c=st.columns(5)
        c[0].metric("標準換匯",f"US${standard_usd:,.0f}")
        c[1].metric("燈號調整後",f"US${suggested_usd:,.0f}")
        c[2].metric("VOO",f"{voo_qty:,.3f} 股")
        c[3].metric("QQQ",f"{qqq_qty:,.3f} 股")
        c[4].metric("0050預算",f"NT${tw_twd:,.0f}")
        st.info(f"本月美元建議採標準計畫的 {fx_factor:.0%}。")

with tabs[3]:
    with st.form("add_trade",clear_on_submit=True):
        a,b,c,d=st.columns(4)
        dt=a.date_input("日期",date.today())
        product=b.selectbox("商品",["VOO","QQQ","0050"])
        market_name=c.selectbox("市場",["美股","台股"])
        price=d.number_input("成交價",min_value=0.0)
        e,f,g=st.columns(3)
        fx_input=e.number_input("匯率",value=float(fx_now))
        qty=f.number_input("股數",min_value=0.0,step=.001)
        fee=g.number_input("手續費",min_value=0.0,value=float(S["fee"]))
        note=st.text_input("備註")
        if st.form_submit_button("新增交易",type="primary"):
            row=pd.DataFrame([{"日期":str(dt),"商品":product,"市場":market_name,"成交價":price,
                               "匯率":fx_input,"股數":qty,"手續費":fee,"備註":note}])
            st.session_state.trades=pd.concat([st.session_state.trades,row],ignore_index=True)
            st.rerun()
    st.session_state.trades=st.data_editor(st.session_state.trades,num_rows="dynamic",use_container_width=True)
    L=ledger(st.session_state.trades)
    if not L.empty:
        st.dataframe(L,use_container_width=True,hide_index=True)
        st.download_button("下載交易 CSV",L.to_csv(index=False).encode("utf-8-sig"),"交易紀錄.csv","text/csv")

with tabs[4]:
    L=ledger(st.session_state.trades)
    holdings=L.groupby("商品")["股數"].sum().to_dict() if not L.empty else {}
    values={
        "VOO":holdings.get("VOO",0)*(M["VOO"]["price"] or 690)*fx_now,
        "QQQ":holdings.get("QQQ",0)*(M["QQQ"]["price"] or 725)*fx_now,
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

with tabs[5]:
    A=amortization(S["loan"],annual,S["years"]*12,S["grace"])
    yearly=A.assign(年度=((A["月份"]-1)//12)+1).groupby("年度",as_index=False).agg({"利息":"sum","本金":"sum","月付金":"sum","期末本金":"last"})
    st.plotly_chart(px.line(yearly,x="年度",y="期末本金",title="房貸餘額"),use_container_width=True)
    st.dataframe(yearly,use_container_width=True,hide_index=True)

with tabs[6]:
    investable=S["loan"]*(1-S["cash"]); rows=[]
    for drop in [0,-.1,-.2,-.3,-.4,-.5]:
        assets=investable*(1+drop)+S["loan"]*S["cash"]
        rows.append([drop,assets,assets-S["loan"],assets/S["loan"]])
    df=pd.DataFrame(rows,columns=["市場跌幅","總資產","淨資產","資產/貸款"])
    st.dataframe(df,use_container_width=True,hide_index=True)
    st.plotly_chart(px.bar(df,x="市場跌幅",y="淨資產",title="市場下跌壓力"),use_container_width=True)

with tabs[7]:
    A=amortization(S["loan"],annual,S["years"]*12,S["grace"]); rows=[]
    for year in range(21):
        bal=S["loan"] if year==0 else float(A.iloc[min(year*12-1,len(A)-1)]["期末本金"])
        for ret,label in [(.05,"保守5%"),(.07,"基準7%"),(.09,"樂觀9%")]:
            assets=S["loan"]*(1-S["cash"])*(1+ret)**year+S["loan"]*S["cash"]*(1.015)**year
            rows.append([year,label,assets-bal])
    st.plotly_chart(px.line(pd.DataFrame(rows,columns=["年度","情境","淨資產"]),
                            x="年度",y="淨資產",color="情境",title="20 年淨資產情境"),use_container_width=True)

st.caption("設定可透過「儲存目前設定」保留在網址；交易紀錄請定期下載 JSON 備份。美元燈號不是匯率預測。市場資料可能延遲。")
