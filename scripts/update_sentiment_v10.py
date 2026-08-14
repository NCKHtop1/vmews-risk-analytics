import json,math,re,sys
from pathlib import Path
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
import torch
from transformers import AutoTokenizer,AutoModelForSequenceClassification
from pyvi import ViTokenizer

MODEL='mnguyn11/phobert-stock-sentiment-PTDLW';VERSION='VMEWS-SENTIMENT-11.0.0';MAX_ITEMS=60
POS=[r'mua ròng mạnh',r'nợ xấu giảm',r'vượt kế hoạch',r'vượt kỳ vọng',r'lợi nhuận.{0,25}tăng',r'lãi.{0,25}tăng',r'trúng thầu',r'nâng khuyến nghị',r'khuyến nghị mua',r'biên lợi nhuận.{0,25}cải thiện']
NEG=[r'bán ròng mạnh',r'nợ xấu tăng',r'thấp hơn.{0,25}kỳ vọng',r'không đạt.{0,25}kế hoạch',r'báo lỗ',r'lỗ ròng',r'giảm mạnh',r'bán tháo',r'hủy niêm yết',r'chậm thanh toán',r'bị điều tra',r'bị khởi tố',r'xử phạt',r'biên lợi nhuận.{0,25}suy yếu',r'cảnh báo.{0,20}giao dịch']
NEU=[r'đại hội đồng cổ đông',r'báo cáo thường niên',r'ngày đăng ký cuối cùng',r'đăng ký giao dịch',r'bác bỏ tin đồn',r'phủ nhận tin đồn',r'xác nhận thông tin']
def ts(x):
 try:return parsedate_to_datetime(str(x)).timestamp()
 except:
  try:return datetime.fromisoformat(str(x).replace('Z','+00:00')).timestamp()
  except:return 0
def override(text,base):
 t=text.lower()
 # Negative qualifiers must be evaluated before generic positive phrases.
 if any(re.search(x,t) for x in NEG):return 'NEG','finance-rule'
 if any(re.search(x,t) for x in NEU):return 'NEU','finance-rule'
 if any(re.search(x,t) for x in POS):return 'POS','finance-rule'
 return base,'phobert'
def main(root='.'):
 root=Path(root);p=root/'data/research-news-v10.json';src=json.loads(p.read_text(encoding='utf-8')) if p.exists() and p.stat().st_size>10 else {'symbols':{},'coverage':{}}
 tok=AutoTokenizer.from_pretrained(MODEL,use_fast=False);mdl=AutoModelForSequenceClassification.from_pretrained(MODEL);mdl.eval();id2={int(k):str(v).upper() for k,v in mdl.config.id2label.items()};now=max([ts(x.get('published')) for a in src.get('symbols',{}).values() for x in a] or [datetime.now(timezone.utc).timestamp()]);out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'sourceVersion':src.get('version'),'model':MODEL,'method':'PhoBERT supervised Vietnamese stock sentiment plus deterministic finance-language overrides; source, recency, materiality and entity relevance weights.','maxItemsPerSymbol':MAX_ITEMS,'symbols':{}}
 for sym,items in src.get('symbols',{}).items():
  clean=[];seen=set()
  for x in sorted(items,key=lambda z:ts(z.get('published')),reverse=True):
   title=re.sub(r'\s+',' ',str(x.get('title') or '')).strip();k=title.lower()
   if not title or k in seen:continue
   seen.add(k);clean.append(x)
   if len(clean)>=MAX_ITEMS:break
  if not clean:continue
  texts=[ViTokenizer.tokenize(str(x.get('title') or '')) for x in clean];pred=[]
  for i in range(0,len(texts),32):
   z=tok(texts[i:i+32],return_tensors='pt',padding=True,truncation=True,max_length=192)
   with torch.no_grad():pr=torch.softmax(mdl(**z).logits,dim=-1)
   for row in pr:
    j=int(torch.argmax(row));lab=id2.get(j,str(j));lab='NEG' if 'NEG' in lab else ('POS' if 'POS' in lab else 'NEU');pred.append((lab,float(row[j])))
  scored=[];sw=ss=0.;cnt={'POS':0,'NEU':0,'NEG':0};methods={'phobert':0,'finance-rule':0};srcCnt={}
  for x,(base,conf) in zip(clean,pred):
   lab,how=override(str(x.get('title') or ''),base);cnt[lab]+=1;methods[how]=methods.get(how,0)+1;srcCnt[x.get('sourceClass','MAINSTREAM')]=srcCnt.get(x.get('sourceClass','MAINSTREAM'),0)+1;age=max(0,(now-ts(x.get('published')))/86400);rec=math.exp(-age/60);w=max(.005,float(x.get('sourceQuality') or .6)*float(x.get('materiality') or .5)*float(x.get('relevance') or 1)*rec*(.7+.3*float(conf)));val=1 if lab=='POS' else -1 if lab=='NEG' else 0;ss+=w*val;sw+=w;scored.append({**x,'label':lab,'confidence':conf,'method':how,'weight':w})
  mean=ss/sw if sw else 0.;grade=(src.get('coverage',{}).get(sym) or {}).get('coverageGrade','THIN');out['symbols'][sym]={'available':True,'n':len(scored),'coverageGrade':grade,'counts':cnt,'methods':methods,'sourceClasses':srcCnt,'signed':mean,'state':'TÍCH CỰC' if mean>.15 else 'TIÊU CỰC' if mean<-.15 else 'TRUNG TÍNH','items':scored}
 (root/'data/sentiment-v10.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');ns=len(out['symbols']);ni=sum(z['n'] for z in out['symbols'].values());print(json.dumps({'version':VERSION,'symbols':ns,'items':ni,'FRT':out['symbols'].get('FRT',{}).get('n',0)},ensure_ascii=False))
if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else '.')
