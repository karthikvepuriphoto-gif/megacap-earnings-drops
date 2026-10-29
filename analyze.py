import yfinance as yf, pandas as pd, numpy as np, json, warnings, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
warnings.filterwarnings('ignore')
T="AAPL MSFT GOOGL AMZN META NVDA TSLA NFLX AVGO ORCL INTC CSCO IBM XOM JPM JNJ WMT BRK-B GE C BAC AIG WFC PFE MRK KO PG T VZ CVX HD UNH V MA QCOM TXN AMD CRM ADBE PYPL DIS NKE BA MMM CAT LLY ABBV PEP COST MCD BMY AMGN HPQ MO GS MS TMO ABT".split()
H={'1w':5,'1m':21,'3m':63,'6m':126,'12m':252}
px=yf.download(T+['SPY','QQQ'],start='1999-01-01',auto_adjust=True,progress=False,group_by='ticker')
C=pd.DataFrame({t:px[t]['Close'] for t in T+['SPY','QQQ']}); O=pd.DataFrame({t:px[t]['Open'] for t in T+['SPY','QQQ']})
R=C.pct_change(); idx=C.index
rows=[];edates={};miss=[]
for t in T:
    try: e=yf.Ticker(t).get_earnings_dates(limit=100)
    except Exception as ex: miss.append(t); continue
    if e is None or len(e)==0: miss.append(t); continue
    days=set()
    for ts,r in e.iterrows():
        loc=ts.tz_localize(None)
        d=loc.normalize()
        # before 9:30 -> same day reaction, else next trading day
        if loc.hour<9 or (loc.hour==9 and loc.minute<30): pos=idx.searchsorted(d)
        else: pos=idx.searchsorted(d,side='right')
        if pos<len(idx): days.add(idx[pos]); 
        sp=r.get('Surprise(%)',np.nan)
        if pos<len(idx): edates[(t,idx[pos])]=sp
    s=C[t].dropna(); first=s.index[0]
    print(t,len(days),min(days).date() if days else None)
def fwd(t,d,entry_px,h):
    p=idx.get_loc(d)
    if p+h>=len(idx): return np.nan
    return C[t].iloc[p+h]/entry_px-1
ev=[]
for (t,d),sp in edates.items():
    r=R.at[d,t] if d in R.index else np.nan
    if pd.isna(r) or r>-0.06: continue
    p=idx.get_loc(d); row=dict(ticker=t,date=d,ret=r,surprise=sp,type='earnings')
    for k,h in H.items():
        row[k]=fwd(t,d,C[t].iloc[p],h)
        for b in ['SPY','QQQ']:
            row[k+'_x'+b]=row[k]-fwd(b,d,C[b].iloc[p],h) if not pd.isna(row[k]) else np.nan
        if p+1<len(idx):
            o=O[t].iloc[p+1]; row[k+'_open']=fwd(t,d,o,h)
        # staggered: 1/3 at d, d+5, d+21, valued at d+h (d+h must be >= 21)
        if h>=21 and p+h<len(idx):
            end=C[t].iloc[p+h]; row[k+'_stag']=np.mean([end/C[t].iloc[p+j]-1 for j in (0,5,21)])
    ev.append(row)
E=pd.DataFrame(ev).sort_values('date')
# record subset: worst post-earnings day to date for that ticker (among all earnings days)
allE=pd.DataFrame([dict(ticker=t,date=d,ret=R.at[d,t]) for (t,d) in edates if d in R.index]).dropna().sort_values('date')
allE['cummin']=allE.groupby('ticker').ret.cummin()
rec=set((r.ticker,pd.Timestamp(r.date)) for r in allE[allE.ret==allE.cummin].itertuples())
def isrec(t,d,r):
    prior=allE[(allE.ticker==t)&(allE.date<d)].ret
    return len(prior)>=4 and r<prior.min()
E['record']=[isrec(t,d,r) for t,d,r in zip(E.ticker,E.date,E.ret)]
# control: non-earnings drops
ed=set(edates); ctrl=[]
for t in T:
    if t not in {k[0] for k in ed}: continue
    first=min(d for (tt,d) in ed if tt==t)
    for d,r in R[t].dropna().items():
        if r>-0.06 or d<first: continue
        p=idx.get_loc(d)
        if any((t,idx[q]) in ed for q in range(max(0,p-3),min(len(idx),p+4))): continue
        row=dict(ticker=t,date=d,ret=r,type='control')
        for k,h in H.items():
            row[k]=fwd(t,d,C[t].iloc[p],h)
            row[k+'_xSPY']=row[k]-fwd('SPY',d,C['SPY'].iloc[p],h) if not pd.isna(row[k]) else np.nan
        ctrl.append(row)
K=pd.DataFrame(ctrl)
rng=np.random.default_rng(0)
def cboot(df,col,n=2000):
    d=df[['ticker',col]].dropna(); g={t:x[col].values for t,x in d.groupby('ticker')}; ks=list(g)
    if len(d)<3: return (np.nan,np.nan)
    m=[np.mean(np.concatenate([g[k] for k in rng.choice(ks,len(ks))])) for _ in range(n)]
    return tuple(np.percentile(m,[2.5,97.5]))
def summ(df,label,cols=('1w','1m','3m','6m','12m')):
    out=[]
    for k in cols:
        c=k+'_xSPY'; d=df[[k,c,'ticker']].dropna()
        lo,hi=cboot(df,c)
        out.append(dict(set=label,h=k,n=len(d),stocks=d.ticker.nunique(),mean_raw=d[k].mean(),median_raw=d[k].median(),mean_xSPY=d[c].mean(),median_xSPY=d[c].median(),ci_lo=lo,ci_hi=hi,hit_vs_SPY=(d[c]>0).mean(),hit_raw=(d[k]>0).mean()))
    return out
res=[]
for th in (-0.06,-0.08,-0.10):
    s=E[E.ret<=th]; res+=summ(s,f'earnings<={int(th*100)}%')
s8=E[E.ret<=-0.08]
res+=summ(s8[s8.record],'record drop (<=-8%)')
res+=summ(s8[s8.date<'2015-01-01'],'<=-8% pre-2015')
res+=summ(s8[s8.date>='2015-01-01'],'<=-8% 2015+')
res+=summ(s8[s8.surprise<0],'<=-8% EPS miss')
res+=summ(s8[s8.surprise>=0],'<=-8% EPS beat (guidance/other)')
res+=summ(K[K.ret<=-0.08],'CONTROL non-earnings <=-8%')
S=pd.DataFrame(res); S.to_csv('results/summary.csv',index=False)
# QQQ + entry comparison for -8%
ent=[]
for k in H:
    d=s8
    ent.append(dict(h=k,close_day0=d[k].mean(),next_open=d[k+'_open'].mean() if k+'_open' in d else np.nan,staggered=d[k+'_stag'].mean() if k+'_stag' in d else np.nan,xQQQ_mean=d[k+'_xQQQ'].mean(),xQQQ_hit=(d[k+'_xQQQ'].dropna()>0).mean()))
pd.DataFrame(ent).to_csv('results/entry_timing.csv',index=False)
E.to_csv('results/events.csv',index=False); K.to_csv('results/control_events.csv',index=False)
# cases
cases=[('META','2022-02-03'),('META','2022-10-27'),('NFLX','2022-04-20'),('NFLX','2022-01-21'),('AMZN','2022-04-29'),('AMZN','2014-10-24'),('MSFT','2000-04-03'),('MSFT','2009-01-22'),('INTC','2024-08-02'),('INTC','2020-07-24'),('GOOGL','2025-10-01'),('GOOGL','2012-10-18'),('GOOGL','2019-04-30'),('GOOGL','2023-10-25'),('NFLX','2011-10-25'),('AAPL','2013-01-24'),('IBM','2004-04-15'),('TSLA','2024-04-24')]
cs=[]
for t,d in cases:
    d=pd.Timestamp(d); m=E[(E.ticker==t)&(abs((E.date-d).dt.days)<=10)]
    if len(m): r=m.iloc[0]; cs.append(dict(ticker=t,date=r.date.date(),drop=r.ret,m1=r['1m'],m3=r['3m'],m12=r['12m'],m12_xSPY=r['12m_xSPY'],record=r.record))
# also all GOOGL events
for _,r in E[(E.ticker=='GOOGL')&(E.ret<=-0.06)].iterrows():
    if not any(c['ticker']=='GOOGL' and c['date']==r.date.date() for c in cs): cs.append(dict(ticker='GOOGL',date=r.date.date(),drop=r.ret,m1=r['1m'],m3=r['3m'],m12=r['12m'],m12_xSPY=r['12m_xSPY'],record=r.record))
pd.DataFrame(cs).to_csv('results/case_studies.csv',index=False)
# charts
def path(df,n=252):
    P=[];Q=[]
    for _,r in df.iterrows():
        p=idx.get_loc(r.date)
        if p+n>=len(idx): continue
        a=C[r.ticker].iloc[p:p+n+1].values/C[r.ticker].iloc[p]; b=C['SPY'].iloc[p:p+n+1].values/C['SPY'].iloc[p]
        P.append(a);Q.append(b)
    return np.nanmean(P,0)-1,np.nanmean(Q,0)-1,len(P)
a,b,n=path(s8); ca,cb,cn=path(K[K.ret<=-0.08])
plt.figure(figsize=(9,5));plt.plot(a*100,label=f'Stock after post-earnings drop <=-8% (n={n})');plt.plot(b*100,label='SPY same dates');plt.plot(ca*100,'--',label=f'Non-earnings drop <=-8% control (n={cn})')
plt.axhline(0,c='k',lw=.5);plt.xlabel('Trading days after drop-day close');plt.ylabel('Avg return %');plt.legend();plt.title('Mega-caps after big one-day drops');plt.savefig('charts/avg_path.png',dpi=120,bbox_inches='tight')
plt.figure(figsize=(9,5));x=s8['12m_xSPY'].dropna()*100;plt.hist(x.clip(-100,200),bins=40);plt.axvline(x.median(),c='r',label=f'median {x.median():.1f}%');plt.xlabel('12m return vs SPY, %');plt.legend();plt.title('Distribution: 12-month excess return after post-earnings drop <=-8%');plt.savefig('charts/dist_12m.png',dpi=120,bbox_inches='tight')
g=C['GOOGL'].dropna(); print('GOOGL last',g.index[-1].date(),R['GOOGL'].iloc[-1])
json.dump(dict(missing=miss,last=str(idx[-1].date())),open('results/meta.json','w'))
pd.set_option('display.width',250); print(S.round(3).to_string()); print(pd.DataFrame(ent).round(3)); print(pd.DataFrame(cs).round(3).to_string())
