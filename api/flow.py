import os,json,math,re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
os.environ['VNSTOCK_DATA_DIR']='/tmp/.vnstock';os.environ['HOME']='/tmp';os.environ['USERPROFILE']='/tmp';os.environ['XDG_CACHE_HOME']='/tmp/.cache';os.environ['XDG_CONFIG_HOME']='/tmp/.config'
for p in ['/tmp/.vnstock','/tmp/.vnstock/id','/tmp/.cache','/tmp/.config']:
 try:os.makedirs(p,exist_ok=True)
 except:pass
VERSION='VMEWS-FLOW-1.0.0'
def n(x):
 try:
  y=float(x);return y if math.isfinite(y) else None
 except:return None
def flat(df):
 try:
  if getattr(df.columns,'nlevels',1)>1:df=df.copy();df.columns=[str(c[-1]) for c in df.columns]
  else:df=df.copy();df.columns=[str(c) for c in df.columns]
 except:pass
 return df
def sumcol(df,c,k):
 if c not in df.columns:return None
 try:return float(df.tail(k)[c].fillna(0).sum())
 except:return None
def ratio(a,b,c):
 if a is None or b is None or c is None:return None
 den=abs(b)+abs(c);return a/den if den>1e-9 else 0.0
def direction(x):
 if x is None:return 'CHƯA CÓ'
 if x>=.12:return 'MUA RÒNG MẠNH'
 if x>=.03:return 'MUA RÒNG'
 if x<=-.12:return 'BÁN RÒNG MẠNH'
 if x<=-.03:return 'BÁN RÒNG'
 return 'CÂN BẰNG'
def payload(symbol):
 from vnstock import Trading
 s=re.sub('[^A-Z0-9]','',str(symbol).upper())[:8]
 if not s:raise ValueError('Invalid symbol')
 t=Trading(symbol=s,source='VCI');out={'version':VERSION,'symbol':s,'available':False,'historicalModelFeature':False,'note':'Dòng tiền khối ngoại/tự doanh hiện dùng làm ngữ cảnh xác nhận. Chưa đưa vào mô hình số quá khứ vì API miễn phí không cung cấp chuỗi point-in-time dài ổn định trong kiểm thử.'}
 try:
  z=flat(t.prop_trade())
  if 'date' in z.columns:z=z.sort_values('date')
  h={}
  for k in (1,5,20):
   fn=sumcol(z,'net_foreign_value',k);fb=sumcol(z,'foreign_buy_value',k);fs=sumcol(z,'foreign_sell_value',k);pn=sumcol(z,'total_prop_trade_net',k);pb=sumcol(z,'total_prop_buy',k);ps=sumcol(z,'total_prop_sell',k);fr=ratio(fn,fb,fs);pr=ratio(pn,pb,ps);h[str(k)]={'foreignNetValue':fn,'foreignNetRatio':fr,'foreignState':direction(fr),'proprietaryNetValue':pn,'proprietaryNetRatio':pr,'proprietaryState':direction(pr)}
  out['recent']=h;out['rows']=len(z);out['available']=len(z)>0
  if len(z) and 'date' in z.columns:out['asOf']=str(z.iloc[-1]['date'])
 except Exception as e:out['recentError']=str(e)
 try:
  q=flat(t.price_board([s]));r=q.iloc[0] if len(q) else None
  if r is not None:
   room=n(r.get('current_room'));total=n(r.get('total_room'));fb=n(r.get('foreign_buy_value'));fs=n(r.get('foreign_sell_value'));out['snapshot']={'foreignBuyValue':fb,'foreignSellValue':fs,'currentRoom':room,'totalRoom':total,'roomRemainingRatio':room/total if room is not None and total and total>0 else None}
 except Exception as e:out['snapshotError']=str(e)
 return out
class handler(BaseHTTPRequestHandler):
 def sendj(self,code,p):
  raw=json.dumps(p,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Access-Control-Allow-Origin','*');self.send_header('Cache-Control','s-maxage=300, stale-while-revalidate=600');self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  q=parse_qs(urlparse(self.path).query)
  try:self.sendj(200,payload(q.get('symbol',['FPT'])[0]))
  except Exception as e:self.sendj(503,{'version':VERSION,'error':'FLOW_CONTEXT_FAILED','message':str(e)})