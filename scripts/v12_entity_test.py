from v12_entity import entity_relevance
CASES=[
 ('HCM','Công ty Cổ phần Chứng khoán Thành phố Hồ Chí Minh','Cổ đông VIB thông qua chuyển Trụ sở ở Hà Nội vào Tp.HCM',False),
 ('HCM','Công ty Cổ phần Chứng khoán Thành phố Hồ Chí Minh','Cổ phiếu HCM tăng mạnh sau kết quả kinh doanh quý II',True),
 ('HCM','Công ty Cổ phần Chứng khoán Thành phố Hồ Chí Minh','HCM: lợi nhuận môi giới cải thiện trong quý II',True),
 ('CDC','Công ty Cổ phần Chương Dương','CDC Home Design Center expands retail footprint',False),
 ('CDC','Công ty Cổ phần Chương Dương','Cổ phiếu CDC của Chương Dương tăng sau thông tin dự án mới',True),
 ('GTA','Công ty Cổ phần Chế biến Gỗ Thuận An','GTA 6 hé lộ trailer mới của Grand Theft Auto',False),
 ('GTA','Công ty Cổ phần Chế biến Gỗ Thuận An','Mã cổ phiếu GTA công bố kết quả kinh doanh',True),
 ('FPT','Công ty Cổ phần FPT','FPT báo lợi nhuận tăng trưởng hai chữ số',True),
 ('VCB','Ngân hàng TMCP Ngoại thương Việt Nam','VCB được khối ngoại mua ròng mạnh trong phiên',True),
]
failed=[]
for symbol,name,title,expected in CASES:
    got,conf,method=entity_relevance(symbol,name,title)
    print(symbol,got,conf,method,title)
    if got!=expected:failed.append((symbol,title,expected,got,method))
if failed:raise SystemExit('ENTITY TEST FAIL '+repr(failed))
print('V12 ENTITY RELEVANCE TEST PASS',len(CASES))
