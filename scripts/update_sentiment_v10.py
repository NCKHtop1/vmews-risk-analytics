import json,math,re,sys
from pathlib import Path
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
import torch
from transformers import AutoTokenizer,AutoModelForSequenceClassification
from pyvi import ViTokenizer
MODEL='mnguyn11/phobert-stock-sentiment-PTDLW';VERSION='VMEWS-SENTIMENT-10.0.0'
POS=[r'mua ròng mạnh',r'nợ xấu giảm',r'vượt kế hoạch',r'vượt kỳ vọng',r'lợi nhuận.{0,20}tăng',r'lãi.{0,20}tăng',r'trúng thầu',r'nâng khuyến nghị',r'khuyến nghị mua']
NEG=[r'bán ròng mạnh',r'nợ xấu tăng',r'thấp hơn.{0,20}kỳ vọng',r'không đạt.{0,20}kế hoạch',r'báo lỗ',r'lỗ ròng',r'giảm mạnh',r'bán tháo',r'hủy niêm yết',r'chậm thanh toán',r'bị điều tra',r'bị khởi tố',r'xử phạt',r'biên lợi nhuận.{0,25}suy yếu']
NEU=[r'đại hội đồng cổ đông',r'báo cáo thường niên',r'ngày đăng ký cuối cùng',r'đăng ký giao dịch',r'bác bỏ tin đồn',r'phủ nhận tin đồn']
def ts(x):
 try:return parsedate_to_datetime(str(x)).timestamp()
 except:
  try:return datetime.fromisoformat(str(x).replace('Z','+00:00')).timestamp()
  except:return 0
def override(text,base):
 t=text.lower()
 if any(re.search(x,t) for x in NEG):return 'NEG','finance-rule'
 if any(re.search(x,t) for x in POS):return 'POS','finance-rule'
 if any(re.search(x,t) for x in NEU):return 'NEU','finance-rule'
 return base,'phobert'
def main(root='.'):
 root=Path(root);src=json.loads((root/'data/research-news-v10.json').read_text(encoding='utf-8'));tok=AutoTokenizer.from_pretrained(MODEL,use_fast=False);mdl=AutoModelForSequenceClassification.from_pretrained(MODEL);mdl.eval();id2={int(k):str(v).upper() for k,v in mdl.config.id2label.items()};now=max([ts(x.get('published')) for a in src.get('symbols',{}).values() for x in a] or [datetime.now(timezone.utc).timestamp()]);out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'sourceVersion':src.get('version'),'model':MODEL,'method':'PhoBERT supervised financial sentiment with finance-language overrides and source/recency/materiality/relevance weighting','symbols':{}}
 for sym,items in src.get('symbols',{}).items():
  clean=[];seen=set()
  for x in sorted(items,key=lambda z:ts(z.get('published')),reverse=True):
   title=re.sub(r'\s+',' ',str(x.get('title') or '')).strip();k=title.lower()
   if not title or k in seen:continue
   seen.add(k);clean.append(x)
   if len(clean)>=30:break
  if not clean:continue
  texts=[ViTokenizer.tokenize(str(x.get('title') or '')) for x in clean];pred=[]
  for i in range(0,len(texts),16):
   z=tok(texts[i:i+16],return_tensors='pt',padding=True,truncation=True,max_length=192)
   with torch.no_grad():pr=torch.softmax(mdl(**z).logits,dim=-1)
   for row in pr:
    j=int(torch.argmax(row));lab=id2.get(j,str(j));lab='NEG' if 'NEG' in lab else ('POS' if 'POS' in lab else 'NEU');pred.append((lab,float(row[j])))
  scored=[];sw=ss=0.;cnt={'POS':0,'NEU':0,'NEG':0}
  for x,(base,conf) in zip(clean,pred):
   lab,how=override(str(x.get('title') or ''),base);cnt[lab]+=1;age=max(0,(now-ts(x.get('published')))/86400);rec=math.exp(-age/45);w=max(.01,float(x.get('sourceQuality') or .6)*float(x.get('materiality') or .5)*float(x.get('relevance') or 1)*rec);val=1 if lab=='POS' else -1 if lab=='NEG' else 0;ss+=w*val;sw+=w;scored.append({**x,'label':lab,'confidence':conf,'method':how,'weight':w})
  mean=ss/sw if sw else 0.;grade=(src.get('coverage',{}).get(sym) or {}).get('coverageGrade','THIN');out['symbols'][sym]={'available':True,'n':len(scored),'coverageGrade':grade,'counts':cnt,'signed':mean,'state':'TÍCH CỰC' if mean>.15 else 'TIÊU CỰC' if mean<-.15 else 'TRUNG TÍNH','items':scored}
 (root/'data/sentiment-v10.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'version':VERSION,'symbols':len(out['symbols']),'FRT':out['symbols'].get('FRT',{}).get('n',0)},ensure_ascii=False))
if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else '.')
