import json
from sklearn.metrics import accuracy_score,f1_score,classification_report
from transformers import AutoTokenizer,AutoModelForSequenceClassification
from pyvi import ViTokenizer
import torch
MODEL='mnguyn11/phobert-stock-sentiment-PTDLW'
CASES=[('POS','FPT báo lãi quý II tăng 20%, vượt kế hoạch kinh doanh.'),('POS','HPG ghi nhận sản lượng thép tăng mạnh và biên lợi nhuận cải thiện.'),('POS','VCB được công ty chứng khoán nâng khuyến nghị lên mua.'),('POS','PNJ công bố doanh thu và lợi nhuận cùng tăng trưởng hai chữ số.'),('POS','Khối ngoại mua ròng mạnh cổ phiếu trong ba phiên liên tiếp.'),('POS','Doanh nghiệp trúng thầu dự án lớn, giá trị hợp đồng vượt kỳ vọng.'),('POS','Nợ xấu giảm và chất lượng tài sản của ngân hàng được cải thiện.'),('POS','Công ty hoàn thành vượt kế hoạch lợi nhuận năm.'),('POS','Doanh nghiệp thông báo cổ tức tiền mặt cao hơn năm trước.'),('POS','Dòng tiền quay lại nhóm ngân hàng với thanh khoản tăng mạnh.'),('NEG','Công ty bị cơ quan quản lý xử phạt do vi phạm công bố thông tin.'),('NEG','Lợi nhuận sau thuế giảm 40% so với cùng kỳ.'),('NEG','Khối ngoại bán ròng mạnh cổ phiếu trong nhiều phiên.'),('NEG','Nợ xấu tăng nhanh và chi phí dự phòng gây áp lực lên lợi nhuận.'),('NEG','Doanh nghiệp chậm thanh toán nghĩa vụ trái phiếu đến hạn.'),('NEG','Cổ phiếu đối mặt nguy cơ hủy niêm yết bắt buộc.'),('NEG','Giá bán giảm khiến biên lợi nhuận ngành thép suy yếu.'),('NEG','Lãnh đạo doanh nghiệp bị điều tra liên quan đến sai phạm.'),('NEG','Doanh thu quý giảm mạnh và công ty báo lỗ ròng.'),('NEG','Nhà đầu tư bán tháo khiến cổ phiếu giảm sàn với thanh khoản lớn.'),('NEU','Công ty sẽ tổ chức đại hội đồng cổ đông thường niên vào tháng tới.'),('NEU','Doanh nghiệp công bố báo cáo tài chính quý theo quy định.'),('NEU','VN-Index đóng cửa phiên giao dịch ở mức 1.520 điểm.'),('NEU','Công ty thông báo ngày đăng ký cuối cùng để thực hiện quyền.'),('NEU','Doanh nghiệp phát hành báo cáo thường niên năm 2025.'),('NEU','Ban lãnh đạo tổ chức cuộc gặp nhà đầu tư định kỳ.'),('NEU','Sở giao dịch thông báo giá tham chiếu của cổ phiếu trong ngày đầu niêm yết.'),('NEU','Cổ đông lớn đăng ký giao dịch cổ phiếu theo quy định.'),('NEU','Cổ phiếu dao động nhẹ quanh tham chiếu với thanh khoản trung bình.'),('NEU','Doanh nghiệp hoàn tất thủ tục thay đổi địa chỉ trụ sở.'),('NEU','FPT không ghi nhận khoản lỗ bất thường trong quý.'),('NEU','Công ty bác bỏ tin đồn bị điều tra đang lan truyền trên mạng xã hội.'),('NEG','Lợi nhuận vẫn tăng nhưng thấp hơn đáng kể so với kỳ vọng thị trường.'),('NEU','Doanh thu giảm nhưng lợi nhuận tăng nhờ biên gộp cải thiện.'),('POS','Kết quả kinh doanh không giảm như lo ngại trước đó và vượt dự báo thận trọng.'),('NEG','Doanh nghiệp không đạt kế hoạch lợi nhuận dù doanh thu tăng.')]
tok=AutoTokenizer.from_pretrained(MODEL,use_fast=False);model=AutoModelForSequenceClassification.from_pretrained(MODEL);model.eval();id2={int(k):str(v).upper() for k,v in model.config.id2label.items()}
def norm(x):
 x=x.upper()
 if 'NEG' in x:return 'NEG'
 if 'POS' in x:return 'POS'
 return 'NEU'
pred=[];rows=[]
for gold,text in CASES:
 s=ViTokenizer.tokenize(text);inp=tok(s,return_tensors='pt',truncation=True,max_length=256)
 with torch.no_grad():pr=torch.softmax(model(**inp).logits,dim=-1)[0]
 j=int(torch.argmax(pr));lab=norm(id2.get(j,str(j)));pred.append(lab);rows.append({'gold':gold,'pred':lab,'confidence':float(pr[j]),'text':text})
y=[x[0] for x in CASES];out={'model':MODEL,'n':len(y),'accuracy':accuracy_score(y,pred),'macroF1':f1_score(y,pred,average='macro'),'report':classification_report(y,pred,output_dict=True,zero_division=0),'rows':rows};print(json.dumps(out,ensure_ascii=False,default=float))
if out['accuracy']<.62 or out['macroF1']<.60:raise SystemExit('SENTIMENT_DL_REVIEW_REQUIRED')