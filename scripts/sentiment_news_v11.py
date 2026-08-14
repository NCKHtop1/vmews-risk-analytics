import json,re,math,os
from pathlib import Path
from datetime import datetime,timezone
import torch
from transformers import AutoTokenizer,AutoModelForSequenceClassification
from pyvi import ViTokenizer

ROOT=Path(os.environ.get('GITHUB_WORKSPACE','.'));MODEL='mnguyn11/phobert-stock-sentiment-PTDLW';VERSION='VMEWS-SENTIMENT-11.0.0'
POS=[r'mua ròng mạnh',r'nợ xấu giảm',r'vượt kế hoạch',r'vượt kỳ vọng',r'lợi nhuận.{0,25}tăng',r'lãi.{0,25}tăng',r'trúng thầu',r'nâng khuyến nghị',r'khuyến nghị mua',r'tăng trưởng.{0,25}hai chữ số']
NEG=[r'bán ròng mạnh',r'nợ xấu tăng',r'thấp hơn.{0,25}kỳ vọng',r'không đạt.{0,25}kế hoạch',r'báo lỗ',r'lỗ ròng',r'giảm mạnh',r'bán tháo',r'hủy niêm yết',r'chậm thanh toán',r'bị điều tra',r'bị khởi tố',r'xử phạt',r'biên lợi nhuận.{0,30}suy yếu',r'cảnh báo.{0,20}rủi ro']
NEU=[r'đại hội đồng cổ đông',r'báo cáo thường niên',r'ngày đăng ký cuối cùng',r'đăng ký giao dịch',r'bác bỏ tin đồn',r'phủ nhận tin đồn',r'đính chính']
def override(text,base):
    t=text.lower()
    if any(re.search(x,t) for x in NEG):return 'NEG','finance-rule'
    if any(re.search(x,t) for x in POS):return 'POS','finance-rule'
    if any(re.search(x,t) for x in NEU):return 'NEU','finance-rule'
    return base,'phobert'
def main():
    src=json.loads((ROOT/'data/news-history-v11.json').read_text(encoding='utf-8'));tok=AutoTokenizer.from_pretrained(MODEL,use_fast=False);mdl=AutoModelForSequenceClassification.from_pretrained(MODEL);mdl.eval();id2={int(k):str(v).upper() for k,v in mdl.config.id2label.items()};out={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),'sourceVersion':src['version'],'model':MODEL,'symbols':{}};allrows=[]
    for s,a in src['symbols'].items():
        for x in a:allrows.append((s,x))
    labels={};batch=32
    for i in range(0,len(allrows),batch):
        part=allrows[i:i+batch];texts=[ViTokenizer.tokenize(str(x['title'])) for _,x in part];z=tok(texts,return_tensors='pt',padding=True,truncation=True,max_length=192)
        with torch.no_grad():pr=torch.softmax(mdl(**z).logits,dim=-1)
        for (s,x),row in zip(part,pr):
            j=int(torch.argmax(row));lab=id2.get(j,str(j));lab='NEG' if 'NEG' in lab else 'POS' if 'POS' in lab else 'NEU';lab,how=override(x['title'],lab);labels[x['id']]={'label':lab,'confidence':float(row[j]),'method':how}
        if i and i%(batch*100)==0:print(json.dumps({'sentimentRows':i,'total':len(allrows)}))
    for s,a in src['symbols'].items():
        rows=[];cnt={'POS':0,'NEU':0,'NEG':0};ss=sw=0.
        for x in a:
            p=labels.get(x['id'],{'label':'NEU','confidence':0.,'method':'fallback'});lab=p['label'];cnt[lab]+=1;val=1 if lab=='POS' else -1 if lab=='NEG' else 0;w=max(.02,float(x.get('sourceQuality',.6))*float(x.get('materiality',.5)));ss+=w*val;sw+=w;rows.append({**x,**p,'weight':w})
        out['symbols'][s]={'n':len(rows),'counts':cnt,'signed':ss/sw if sw else 0.,'items':rows}
    out['summary']={'symbols':len(out['symbols']),'articles':sum(z['n'] for z in out['symbols'].values()),'positive':sum(z['counts']['POS'] for z in out['symbols'].values()),'negative':sum(z['counts']['NEG'] for z in out['symbols'].values()),'neutral':sum(z['counts']['NEU'] for z in out['symbols'].values())}
    (ROOT/'data/sentiment-v11.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(json.dumps(out['summary'],ensure_ascii=False))
if __name__=='__main__':main()
