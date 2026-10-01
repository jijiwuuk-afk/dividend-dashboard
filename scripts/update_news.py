#!/usr/bin/env python3
import json, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import html, re, time

ROOT=Path(__file__).resolve().parents[1]
HOLDINGS=json.loads((ROOT/"data/holdings.json").read_text(encoding="utf-8"))

def clean(s):
    s=html.unescape(re.sub("<[^>]+>","",s or ""))
    return re.sub(r"\s+"," ",s).strip()

def age_text(dt):
    now=datetime.now(timezone.utc)
    d=now-dt
    sec=max(0,int(d.total_seconds()))
    if sec<3600:return f"{sec//60}분 전"
    if sec<86400:return f"{sec//3600}시간 전"
    return f"{sec//86400}일 전"

def fetch_rss(query, lang="ko", country="KR"):
    q=urllib.parse.quote(query+" when:7d")
    url=f"https://news.google.com/rss/search?q={q}&hl={lang}&gl={country}&ceid={country}:{lang}"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 DividendDashboard/1.0"})
    with urllib.request.urlopen(req,timeout=20) as r:
        return r.read()

def fetch_prices(symbol):
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=1y&interval=1d&includePrePost=false&events=div%2Csplits"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 DividendDashboard/1.0"})
    with urllib.request.urlopen(req,timeout=20) as r:
        raw=json.loads(r.read().decode("utf-8"))
    res=raw.get("chart",{}).get("result",[{}])[0]
    timestamps=res.get("timestamp",[]) or []
    closes=((res.get("indicators",{}).get("quote",[{}])[0]).get("close",[]) or [])
    prices=[]
    for ts,cl in zip(timestamps,closes):
        if cl is None: continue
        dt=datetime.fromtimestamp(ts,tz=timezone.utc).astimezone(timezone(timedelta(hours=9)))
        prices.append({"date":dt.strftime("%m/%d"),"close":round(float(cl),4)})
    return {"prices":prices[-270:]}

items=[]
seen=set()
cutoff=datetime.now(timezone.utc)-timedelta(days=7)

for h in HOLDINGS:
    # Korean locale works reasonably for both local and global names.
    try:
        raw=fetch_rss(h["query"])
        root=ET.fromstring(raw)
        count=0
        for it in root.findall(".//item"):
            title=clean(it.findtext("title"))
            link=clean(it.findtext("link"))
            pub=clean(it.findtext("pubDate"))
            source_el=it.find("source")
            source=clean(source_el.text if source_el is not None else "")
            try:
                dt=parsedate_to_datetime(pub).astimezone(timezone.utc)
            except Exception:
                dt=datetime.now(timezone.utc)
            if dt<cutoff: continue
            key=re.sub(r"[^0-9a-zA-Z가-힣]+","",title.lower())[:180]
            dedupe=(h["ticker"],key)
            if not title or dedupe in seen: continue
            seen.add(dedupe)
            items.append({
                "ticker":h["ticker"],
                "name":h["name"],
                "title":title,
                "link":link,
                "source":source,
                "published":dt.astimezone(timezone(timedelta(hours=9))).strftime("%m-%d %H:%M"),
                "published_iso":dt.isoformat(),
                "age":age_text(dt)
            })
            count+=1
            if count>=4: break
        time.sleep(0.08)
    except Exception as e:
        continue

items.sort(key=lambda x:x["published_iso"],reverse=True)
out={
    "updated_at":datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"),
    "items":items[:100]
}
(ROOT/"data/news.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
print("updated",len(out["items"]))

# market data for dashboard sparklines
market={}
symbol_map={
"005930":"005930.KS","000660":"000660.KS","005380":"005380.KS",
"379780":"379780.KS","368590":"368590.KS","458730":"458730.KS","0072R0":"0072R0.KS",
"322410":"322410.KS","379800":"379800.KS","379810":"379810.KS","487230":"487230.KS",
"489250":"489250.KS","490490":"490490.KS",
"AMD":"AMD","ZETA":"ZETA","TSM":"TSM","NVDA":"NVDA","GEV":"GEV","SNDK":"SNDK","QQQM":"QQQM",
"CAT":"CAT","VOO":"VOO","INTC":"INTC","COST":"COST","GOOG":"GOOG","SCHD":"SCHD","AVGO":"AVGO",
"GLDM":"GLDM","TSLA":"TSLA","JEPI":"JEPI","JEPQ":"JEPQ"}
for h in HOLDINGS:
    sym=symbol_map.get(h["ticker"],h["ticker"])
    try:
        market[sym]=fetch_prices(sym)
        time.sleep(0.03)
    except Exception:
        market[sym]={"prices":[]}
try:
    fx=fetch_prices("KRW=X")
    if fx.get("prices"):
        market["_meta"]={"usdkrw":fx["prices"][-1]["close"]}
except Exception:
    market["_meta"]={"usdkrw":1360.81}
(ROOT/"data/market_data.json").write_text(json.dumps(market,ensure_ascii=False,indent=2),encoding="utf-8")
print("market updated",len(market))
