#!/usr/bin/env python3
"""50 live FinQuery browser cases. Logs results as QA50_CASE JSON; never invent PASS."""
import json,os,re,sys,time,traceback
from datetime import datetime,timezone
from pathlib import Path
from playwright.sync_api import sync_playwright,TimeoutError as BrowserTimeout
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill,Alignment

BASE=os.getenv('FINQUERY_QA_URL','https://finquery.info.vn/financial-report/')
OUT=Path('qa50_results');OUT.mkdir(exist_ok=True)
DATA="""\
01|FPT|local|tài sản ngắn hạn là gì?
02|FPT|local|TOI là gì?
03|FPT|local|tôi đang hỏi về tài sản
04|FPT|local|NIM là gì?
05|FPT|local|ROE và ROA khác nhau thế nào?
06|FPT|local|Nợ ngắn hạn là gì?
07|FPT|local|Current assets la gi?
08|FPT|local|Cong thuc nau pho Ha Noi la gi?
09|FPT|local|Tong tai san FPT nam 2025 bao nhieu?
10|FPT|local|Tài sản ngắn hạn FPT năm 2025 bao nhiêu?
11|FPT|local|Doanh thu FPT quý 2/2025 bao nhiêu?
12|FPT|local|Loi nhuan sau thue FPT quy 1/2025?
13|FPT|local|ROE FPT năm 2023 bằng bao nhiêu?
14|FPT|local|Hàng tồn kho FPT năm 2024 bao nhiêu?
15|FPT|local|So sánh lợi nhuận FPT năm 2024 và 2025
16|FPT|local|Tiền và tương đương tiền FPT 2025?
17|FPT|local|ROE va ROA FPT nam 2025 bao nhieu?
18|MBB|local|NIM MBB nam 2025?
19|FPT|local|So sánh BCTC FPT và MBB năm 2025?
20|MBB|local|Doanh thu FPT 2025 bao nhiêu?
21|FRT|local|Tin về FPT Retail / FRT hôm nay?
22|MBB|switch|Chuyển từ MBB sang FPT, hỏi tiếp: Mã này có nợ ngắn hạn bao nhiêu?
23|FPT|local|Gia ma ZZZ hom nay bao nhieu?
24|FPT|local|Giá FPT hôm nay bao nhiêu?
25|FPT|local|Giá FPT hiện tại bao nhiêu?
26|FPT|local|Giá FPT hôm qua bao nhiêu?
27|FPT|local|Giá FPT ngày 07/10/2026 bao nhiêu?
28|FPT|local|RSI cua FPT hien tai?
29|FPT|local|MACD và RSI của FPT hiện tại?
30|FPT|policy|Hỏi giá hôm nay nhưng quote sourceTime T-1
31|FPT|local|Tin cổ tức FPT mới nhất?
32|FRT|local|Tin cổ tức FRT mới nhất?
33|FPT|local|Tin thị trường chung hôm nay?
34|FPT|local|Tin 24hMoney của FPT 24h qua?
35|FPT|local|Lai suat ON hom nay bao nhieu?
36|FPT|local|CPI tháng 8/2026 bao nhiêu?
37|FPT|local|PMI tháng 7/2026 bao nhiêu?
38|FPT|local|Dự báo T+3 FPT?
39|FPT|local|Dự báo T+5 FPT?
40|MBB|local|Rủi ro định lượng MBB hiện tại?
41|MBB|local|Phân tích chuyên sâu toàn diện mã này và lập hồ sơ nghiên cứu.
42|FPT|local|FPT hôm nay nên mua hay bán?
43|FPT|modal|Mở Dolphin AI ở viewport 390x844, đóng và mở lại
44|FPT|mobile|Mở Dolphin mobile 360x800; kiểm tra FAB và nút Dừng/Gửi
45|FPT|provider|Nhanh & tiết kiệm: hỏi mở về tài chính MBB
46|MBB|provider|Phân tích chuyên sâu MBB và lập hồ sơ nghiên cứu (anh 21:29)
47|FPT|mock429|Mock Gemini 429/503 trong deep mode
48|FPT|mockstop|Bấm Ngắt giữa request đang chờ
49|FPT|mockdouble|Bấm Gửi 2 lần rất nhanh khi busy
50|FPT|responsive|Mất mạng -> reload -> khôi phục, mobile xoay ngang/dọc"""
CASES=[{'id':'FQ-'+n,'symbol':sym,'kind':kind,'question':question} for n,sym,kind,question in (line.split('|',3) for line in DATA.splitlines())]
assert len(CASES)==50 and len(set(x['id'] for x in CASES))==50
ESCAPE=re.compile(r'(AIza[0-9A-Za-z_-]{12,}|sk-[0-9A-Za-z]{12,}|key=[^&\s]+)',re.I)
def clean(s):return ESCAPE.sub('[SECRET REDACTED]',str(s or ''))[:420]
def need(cond,msg):
 if not cond:raise AssertionError(msg)
def read(page,q):
 return page.evaluate("""q=>{
 const a=window.FinQueryAI.analyze(q),k=window.FinQueryKnowledge.find(q),
 m=window.FinancialMarket?.context?.()||{},r=window.FinancialReportContext?.raw?.()||{};
 const e=document.createElement('div');e.innerHTML=String(a.html||'');
 return {type:a.type,body:e.textContent||'',html:String(a.html||''),concept:k?.title||'',definition:k?.definition||'',market:m.symbol||'',report:r.symbol||'',quoteTime:m.quote?.sourceTime||''};
 }""",q)
def semantic(c,page):
 id=int(c['id'][-2:]);q=c['question'];a=read(page,q)
 body=str(a.get('body') or '').lower()
 ascii_body=body.lower()
 need(len(body)>=20,'Empty or tiny answer')
 need(not re.search(r'\b(undefined|nan|\[object object\])\b',body,re.I),'JavaScript undefined/NaN leaked')
 if id in [1,2,4,6,7]:
  need(a['type']=='concept','Not a concept answer: '+str(a['type']))
  need(bool(a['definition']) and a['definition'][:22] in a['body'],'Wrong glossary definition')
 if id==1:need('tài sản ngắn hạn' in body and not 'toi là tổng' in body,'Current assets confused with TOI')
 if id==3:need('toi là tổng' not in body,'Vietnamese pronoun matched bank TOI')
 if id==5:need('roe' in body and 'roa' in body,'Missing either ROE or ROA')
 if id==8:need('không xác định' in body or 'chưa' in body or 'không' in body,'Out-of-domain answer should refuse')
 if id in [9,10,11,12,13,14,16,17,18]:
  need(a['type'] in ['metric','multiMetric'],'Numeric/period question misrouted as '+str(a['type']))
  need((c['symbol'] in body.upper()) or any(x in body for x in ['chưa có','không có','không đủ','chưa xác']), 'Issuer/missing-data source absent')
 if id in [9,10,13,14,16,17,18]:need('2025' in body or ('2023' in body if id==13 else False) or ('2024' in body if id==14 else False),'Requested fiscal year missing')
 if id==11:need('2025-Q2' in a['body'] or 'không có' in body or 'chưa có' in body,'Quarter Q2 omitted')
 if id==12:need('2025-Q1' in a['body'] or 'không có' in body or 'chưa có' in body,'Quarter Q1 omitted')
 if id==13:need('2023' in body and not re.search(r'2023\s*[:=]\s*18[.,]',body),'Made up unavailable 2023 ROE')
 if id==15:need(('2024' in body and '2025' in body) or 'thiếu' in body or 'chưa' in body,'Two-year comparison incomplete')
 if id==17:need('roe' in body and 'roa' in body,'One of two requested metrics omitted')
 if id==19:need(a['type']=='multiSymbol' and 'FPT' in a['body'] and 'MBB' in a['body'],'Cross-ticker comparison used one issuer')
 if id==20:need('FPT' in a['body'] and ('MBB' in a['body'] or 'đồng bộ' in body or 'đang' in body),'Did not recognize wrong active ticker')
 if id==21:need(a['type']=='news' and ('FRT' in a['body'] or 'chưa' in body) and 'nhiều mã' not in body,'FPT Retail alias wrongly interpreted as FPT + FRT')
 if id==23:need(not re.search(r'FPT.*(tăng|giảm)\s*[\d,.]+%',a['body'],re.I),'Unknown ZZZ borrowed FPT movement')
 if id in [24,25]:need(a['type']=='movement','Price question routed to '+str(a['type']))
 if id in [26,27]:need(any(x in body for x in ['lịch sử','quá khứ','phiên','ngày 07','chuỗi giá']), 'Historical price request used current quote')
 if id==28:need(a['type'] in ['technical','metric'] and ('rsi' in body or 'chưa' in body),'RSI missing')
 if id==29:need('rsi' in body and 'macd' in body or 'chưa có' in body,'Either MACD or RSI missing')
 if id in [31,32,33,34]:need(a['type']=='news','News misrouted '+str(a['type']))
 if id==31:need('frt' not in body or 'không' in body,'FRT appears in FPT dividend news')
 if id==31:need('cổ tức' in body or 'chưa có tin' in body,'Dividend question answered with unrelated market headline')
 if id==32:need('fpt công' not in body,'FPT unrelated article in FRT news')
 if id==34:need('24hmoney' in body or 'chưa có tin' in body,'Named news source not respected')
 if id in [35,36,37]:need(a['type']=='macro','Macro question misrouted '+str(a['type']))
 if id in [38,39]:need(a['type']=='forecast' and ('forecast' in body or 'dự báo' in body or 'chưa có' in body),'Forecast not gated')
 if id==40:need(a['type']=='risk','Risk question misrouted')
 if id==41:need(a['type']=='memo' and len(body)>120,'Deep memo local answer empty')
 if id==42:need(len(body)>30 and ('mua' in body or 'bán' in body or 'khuyến nghị' in body or 'rủi ro' in body),'Investment question ignored')
 return str(a['type'])+': '+a['body'][:155]
def wait(page):page.wait_for_function('!!(window.FinQueryAI?.analyze&&window.FinQueryKnowledge?.find&&window.FinQueryQuestionPolicy?.priceQuality)',timeout=35000)
def opener(page):page.evaluate("window.FinQueryAI.open()");page.wait_for_function("document.querySelector('#research-ai')?.hidden===false",timeout=12000)
def closer(page):page.evaluate("window.FinQueryAI.close()");page.wait_for_timeout(380)
def mobile(page):
 opener(page)
 d=page.evaluate("""()=>{
 const b=document.querySelector('#research-ai-send'),fab=document.querySelector('#ai-fab'),i=document.querySelector('#research-ai-question');
 const isVisible=x=>!!x&&x.getClientRects().length>0&&getComputedStyle(x).visibility!=='hidden';
 const r=b?.getBoundingClientRect(),f=fab?.getBoundingClientRect();
 const over=r&&f&&r.left<f.right&&r.right>f.left&&r.top<f.bottom&&r.bottom>f.top;
 const center=r?document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2):null;
 return{send:isVisible(b),input:isVisible(i),floating:isVisible(fab),
 overlap:isVisible(fab)&&over,hit:!!(center&&(center===b||b?.contains(center))),
 inView:!!(r&&r.left>=-3&&r.right<=innerWidth+3&&r.bottom<=innerHeight+3),
 overflow:document.documentElement.scrollWidth>innerWidth+5};
}""")
 need(d['send'] and d['input'] and d['hit'] and d['inView'] and not d['overlap'] and not d['overflow'],'Mobile send hit target/overlap: '+str(d))
 closer(page)
 return str(d)
def special(c,page,browser):
 cid=c['id']
 if cid=='FQ-30':
  r=page.evaluate("""()=>window.FinQueryQuestionPolicy.priceQuality({symbol:'FPT',price:50000,sourceTime:'2026-10-08T07:30:00Z'},'FPT','Giá FPT hôm nay',new Date('2026-10-09T07:31:00Z'))""")
  need(r.get('usable') is False,'T-1 quote approved as current');return 'T-1 rejected '+r.get('reason','')
 if cid=='FQ-22':
  page.evaluate("window.FinancialMarket.openChart('FPT')")
  page.wait_for_function("window.FinancialMarket?.context?.()?.symbol==='FPT'",timeout=15000)
  a=read(page,"Mã này có nợ ngắn hạn bao nhiêu?")
  need('MBB' not in a['body'] or 'không' in a['body'],'MBB data retained after FPT switch')
  page.reload(wait_until='domcontentloaded');wait(page);return "Navigated MBB => FPT; no MBB figure reused"
 if cid=='FQ-43':
  opener(page);need(page.locator('#research-ai-question').is_visible(),'Missing prompt input')
  closer(page);opener(page);need(page.locator('#research-ai-question').is_visible(),'Cannot reopen AI')
  closer(page);return 'Modal opens, closes and reopens'
 if cid=='FQ-44':
  page.set_viewport_size({'width':360,'height':800});return mobile(page)
 if cid=='FQ-50':
  for w,h in [(360,780),(780,360),(390,844)]:
   page.set_viewport_size({'width':w,'height':h});mobile(page)
  return '3 mobile rotations, footer remains clickable'
 return 'not implemented'
def prepare_mock(browser,sym,kind):
 ctx=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,locale='vi-VN')
 page=ctx.new_page();events={'generate':0,'retries':0}
 def api(route):
  url=route.request.url
  if ':generateContent' in url:
   events['generate']+=1
   if events['generate']==1 or kind=='mock429':
    # Allow first probe and then simulate provider overload for later calls.
    if kind=='mock429' and events['generate']>1:
     route.fulfill(status=429,content_type='application/json',body=json.dumps({'error':{'message':'mock quota overload'}}));return
    route.fulfill(status=200,content_type='application/json',body=json.dumps({'candidates':[{'content':{'parts':[{'text':'Kết quả Gemini giả lập có nguồn [BCTC]'}]},'finishReason':'STOP'}]}));return
   if kind in ['mockstop','mockdouble']:
    time.sleep(8)
   route.fulfill(status=200,content_type='application/json',body=json.dumps({'candidates':[{'content':{'parts':[{'text':'Bản phân tích mô phỏng [BCTC]'}]},'finishReason':'STOP'}]}));return
  if '/models?' in url or url.endswith('/models'):
   route.fulfill(status=200,content_type='application/json',body=json.dumps({'models':[{'name':'models/gemini-3.8-flash','supportedGenerationMethods':['generateContent']},{'name':'models/gemini-3.5-flash-lite','supportedGenerationMethods':['generateContent']}] }));return
  route.fulfill(status=200,content_type='application/json',body='{}')
 page.route('https://generativelanguage.googleapis.com/**',api)
 page.goto(BASE+'?symbol='+sym+'&mode=year#market',wait_until='domcontentloaded',timeout=45000)
 wait(page);page.evaluate("sessionStorage.setItem('vmews_solution_ai_browser_session','QA_FAKE_KEY_NEVER_VALID')")
 page.reload(wait_until='domcontentloaded',timeout=45000);wait(page)
 return ctx,page,events
def mocked(c,browser):
 kind=c['kind'];ctx,page,events=prepare_mock(browser,c['symbol'],kind)
 try:
  opener(page)
  page.evaluate("window.FinQueryAI.setMode('deep')")
  page.evaluate("""()=>{window.FinQueryAI.ask('Phân tích sâu có căn cứ về FPT và rủi ro, không suy diễn số liệu.')}""")
  page.wait_for_function("document.querySelector('#research-ai-send')?.dataset.busy==='1'",timeout=14000)
  if kind=='mockstop':
   page.locator('#research-ai-send').click()
   page.wait_for_function("document.querySelector('#research-ai-send')?.dataset.busy!=='1'",timeout=25000)
   body=page.locator('#research-ai').inner_text()
   need('Đã dừng' in body or 'dừng' in body.lower(),'Stop did not cancel request')
  elif kind=='mockdouble':
   # Ask second request while the UI is busy; should refuse concurrent submissions.
   page.evaluate("""()=>{window.FinQueryAI.ask('Câu hỏi trùng được gửi khi đang bận');}""")
   page.wait_for_function("document.querySelector('#research-ai-send')?.dataset.busy!=='1'",timeout=55000)
   need(events['generate']<10,'Duplicate busy action caused excessive provider calls')
  else:
   page.wait_for_function("document.querySelector('#research-ai-send')?.dataset.busy!=='1'",timeout=90000)
   body=page.locator('#research-ai').inner_text()
   need('Gemini' in body or 'FinQuery' in body,'No usable overload/fallback message')
  return 'Mock provider '+kind+' requests='+str(events['generate'])
 finally:ctx.close()
def main():
 out=[]
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
  pages={}
  try:
   for c in CASES:
    id=c['id'];t=time.monotonic();rec={**c,'status':'BLOCKED','actual':'','ms':0,'at_utc':datetime.now(timezone.utc).isoformat()}
    page=None
    try:
     if c['kind']=='provider':
      rec['status']='BLOCKED';rec['actual']='Real Gemini key not provided. Cannot claim live provider response.'
     elif c['kind'].startswith('mock'):
      rec['actual']=mocked(c,browser);rec['status']='PASS'
     else:
      sym=c['symbol'];mobile_mode=c['kind'] in ['switch','modal','mobile','responsive'];key=(sym,mobile_mode)
      if key not in pages:
       ctx=browser.new_context(viewport={'width':390 if mobile_mode else 1440,'height':844 if mobile_mode else 950},is_mobile=mobile_mode,has_touch=mobile_mode,locale='vi-VN')
       page=ctx.new_page();page.goto(BASE+'?symbol='+sym+'&mode=year#market',wait_until='domcontentloaded',timeout=45000);wait(page)
       page.wait_for_timeout(1200);pages[key]=(ctx,page)
      else:_,page=pages[key]
      rec['actual']=special(c,page,browser) if c['kind']!='local' else semantic(c,page)
      rec['status']='PASS'
    except Exception as ex:
     rec['status']='FAIL';rec['actual']=clean(type(ex).__name__+': '+str(ex))
     if page:
      try:
       shot=OUT/(id+'.png')
       page.screenshot(path=str(shot),full_page=False,timeout=8000,mask=page.locator('input[type=password]'))
       rec['screenshot']=str(shot)
      except Exception:pass
    rec['ms']=round((time.monotonic()-t)*1000)
    out.append(rec);print('QA50_CASE '+json.dumps({k:rec[k] for k in ('id','status','actual','ms')},ensure_ascii=False),flush=True)
  finally:
   for ctx,_ in pages.values():
    try:ctx.close()
    except Exception:pass
   browser.close()
 counts={s:sum(x['status']==s for x in out) for s in ['PASS','FAIL','BLOCKED']}
 (OUT/'results.json').write_text(json.dumps({'counts':counts,'url':BASE,'cases':out},ensure_ascii=False,indent=2),encoding='utf-8')
 wb=Workbook();ws=wb.active;ws.title="50 test cases";ws.append(['Mã','Mã cổ phiếu','Loại','Câu hỏi / thao tác','Trạng thái','Kết quả thực tế','Thời gian (ms)','Bằng chứng'])
 for r in out:ws.append([r['id'],r['symbol'],r['kind'],r['question'],r['status'],r['actual'],r['ms'],r.get('screenshot','')])
 ws.freeze_panes='A2';ws.auto_filter.ref=f'A1:H{len(out)+1}'
 for cell in ws[1]:
  cell.fill=PatternFill('solid',fgColor='183153');cell.font=Font(bold=True,color='FFFFFF')
 for row in ws.iter_rows(min_row=2):
  row[4].fill=PatternFill('solid',fgColor={'PASS':'D7F2E2','FAIL':'FCE0E0','BLOCKED':'FFF0CC'}[row[4].value])
  for cell in row:cell.alignment=Alignment(vertical='top',wrap_text=True)
 for col,w in [('A',14),('B',14),('C',19),('D',65),('E',17),('F',96),('G',18),('H',42)]:ws.column_dimensions[col].width=w
 wb.save(OUT/'FinQuery_50_Test_Results.xlsx')
 print('QA50_SUMMARY '+json.dumps(counts),flush=True)
 # Fails the action on real regressions, but artifacts always upload.
 sys.exit(1 if counts['FAIL'] else 0)
if __name__=='__main__':main()
