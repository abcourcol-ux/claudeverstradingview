import sys
rows=[l.split() for l in open(sys.argv[1])]
B=[dict(t=r[0],o=float(r[1]),h=float(r[2]),l=float(r[3]),c=float(r[4])) for r in rows]
def mins(t):  # minutes since 23:00 UTC 19/11
    m=int(t[:2])*60+int(t[2:]); return (m-23*60)%1440
WIN={'NY':(15*60+30,22*60), 'Nuit':(30,4*60)}  # in minutes since 23:00 -> NY 14:30-21:00 UTC; night 23:30-03:00 UTC
SLMIN=float(sys.argv[2]) if len(sys.argv)>2 else 5.0; K=1.5
# ATR rma14
atr=[None]*len(B); trs=[]
for i,b in enumerate(B):
    tr=b['h']-b['l'] if i==0 else max(b['h']-b['l'],abs(b['h']-B[i-1]['c']),abs(b['l']-B[i-1]['c']))
    trs.append(tr)
    if i==13: atr[i]=sum(trs)/14
    elif i>13: atr[i]=(atr[i-1]*13+tr)/14
s=0;vw=[]
for i,b in enumerate(B): s+=(b['h']+b['l']+b['c'])/3; vw.append(s/(i+1))
def utc(t): return t[:2]+'h'+t[2:]
pos=None; trades=[]; n=0
for i,b in enumerate(B):
    m=mins(b['t'])
    # manage open position on this bar
    if pos and i>=pos['fill']:
        if i==pos['fill']: pos['e']=b['o']
        path=[b['o'],b['h'],b['l'],b['c']] if abs(b['o']-b['h'])<abs(b['o']-b['l']) else [b['o'],b['l'],b['h'],b['c']]
        d=pos['d']; done=False
        for a,z in zip(path,path[1:]):
            lo,hi=min(a,z),max(a,z)
            for _ in range(4):
                st=pos['st']
                tgts=[k for k in ('tp1','tp2','tpf') if k not in pos['hit']]
                ev=[]
                if lo<=st<=hi: ev.append((abs(st-a),'stop',st))
                for k in tgts:
                    p=pos[k]
                    if lo<=p<=hi: ev.append((abs(p-a),k,p))
                if not ev: break
                ev.sort(); _,k,p=ev[0]
                if k=='stop':
                    left=3-len(pos['hit']); pos['r']+=left/3*d*(p-pos['e'])/pos['R']; pos['exit']=('SL' if not pos['hit'] else 'BE')+' '+utc(b['t']); done=True; break
                pos['hit'].append(k); pos['r']+=1/3*d*(p-pos['e'])/pos['R']
                if k=='tp1': pos['st']=pos['e0']
                if k=='tpf': pos['exit']='TP final '+utc(b['t']); done=True; break
                a=p
            if done: break
        w=WIN[pos['w']]
        if not done and m+5>=w[1]-5:
            left=3-len(pos['hit']); pos['r']+=left/3*d*(b['c']-pos['e'])/pos['R']; pos['exit']='Fin de fenêtre '+utc(b['t']); done=True
        if done: trades.append(pos); pos=None
        continue
    if pos or atr[i-1] is None or i==0: continue
    for w,(a,z) in WIN.items():
        if a<=m<z and m-a>=15 and (z-(m+5))>=45:
            rs=trs[i]/atr[i-1]
            d=1 if (rs>=2 and b['c']>vw[i] and b['c']>b['o']) else -1 if (rs>=2 and b['c']<vw[i] and b['c']<b['o']) else 0
            if d and abs(b['c']-vw[i])<=3*atr[i] and n<5 and i+1<len(B):
                R=max(SLMIN,K*atr[i]); e=b['c']
                pos=dict(w=w,d=d,sig=b['t'],fill=i+1,e0=e,e=e,R=R,st=e-d*R,tp1=e+d*R,tp2=e+2*d*R,tpf=e+3*d*R,hit=[],r=0.0,atr=atr[i]); n+=1
for p in trades:
    print(f"{p['w']:4} signal {utc(p['sig'])} UTC {'ACHAT' if p['d']>0 else 'VENTE'} entrée {p['e']:.2f} SL {p['st'] if not p['hit'] else p['e0']-p['d']*p['R']:.2f} ({p['R']*10:.0f} pips, ATR {p['atr']:.2f}) TP {'+'.join(p['hit']) or '-'} → {p['exit']} : {p['r']:+.2f}R = {p['r']*25:+.0f}$")
print('TOTAL', round(sum(p['r'] for p in trades),2),'R =',round(sum(p['r'] for p in trades)*25),'$ sur',len(trades),'trades')
print('--- bougies à forte amplitude (≥1,6 ATR) dans les fenêtres')
for i,b in enumerate(B):
    if i<15: continue
    m=mins(b['t']); rs=trs[i]/atr[i-1]
    for w,(a,z) in WIN.items():
        if a<=m<z and rs>=1.6: print(w,utc(b['t']),round(rs,2),'c>vwap' if b['c']>vw[i] else 'c<vwap','haussière' if b['c']>b['o'] else 'baissière', 'ext' if abs(b['c']-vw[i])>3*atr[i] else '', round((b['c']-vw[i])/atr[i],1))
