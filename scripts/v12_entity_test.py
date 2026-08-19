from v12_entity import entity_relevance
CASES=[
 ('HCM','Công ty Cổ phần Chứng khoán Thành phố Hồ Chí Minh','Cổ đông VIB thông qua chuyển Trụ sở ở Hà Nội vào Tp.HCM',False),
 ('HCM','Công ty Cổ phần Chứng khoán Thành phố Hồ Chí Minh','Cổ phiếu HCM tăng mạnh sau kết quả kinh doanh quý II',True),
 ('HCM','Công ty Cổ phần Chứng khoán Thành phố Hồ Chí Minh','HCM: lợi nhuận môi giới cải thiện trong quý II',True),
 ('CDC','Công ty Cổ phần Chương Dương','CDC Home Design Center expands retail footprint',False),
 ('CDC','Công ty Cổ phần Chương Dương','Giám đốc CDC Hà Giang bị bắt để điều tra',False),
 ('CDC','Công ty Cổ phần Chương Dương','Cổ phiếu CDC của Chương Dương tăng sau thông tin dự án mới',True),
 ('GTA','Công ty Cổ phần Chế biến Gỗ Thuận An','GTA 6 hé lộ trailer mới của Grand Theft Auto',False),
 ('GTA','Công ty Cổ phần Chế biến Gỗ Thuận An','Mã cổ phiếu GTA công bố kết quả kinh doanh',True),
 ('THG','Công ty Cổ phần Đầu tư và Xây dựng Tiền Giang','ASML giảm 3% ngày 15 thg 4: cổ phiếu phản ứng mạnh',False),
 ('THG','Công ty Cổ phần Đầu tư và Xây dựng Tiền Giang','THG: lợi nhuận quý II tăng trưởng',True),
 ('VIP','Công ty Cổ phần Vận tải Xăng dầu VIPCO','Mất tiền vào room VIP chứng khoán, nhà đầu tư vẫn thua lỗ',False),
 ('VIP','Công ty Cổ phần Vận tải Xăng dầu VIPCO','Cổ phiếu VIP chốt quyền trả cổ tức',True),
 ('FIT','Công ty Cổ phần Tập đoàn F.I.T','Dự án điện gió hưởng giá FIT cho đối tác ngoại',False),
 ('FIT','Công ty Cổ phần Tập đoàn F.I.T','Mã cổ phiếu FIT công bố kế hoạch năm mới',True),
 ('NHA','Tổng Công ty Đầu tư Phát triển Nhà và Đô thị Nam Hà Nội','Chủ đầu tư mở dự án nghỉ dưỡng tại Nha Trang',False),
 ('NHA','Tổng Công ty Đầu tư Phát triển Nhà và Đô thị Nam Hà Nội','NHA: doanh thu và lợi nhuận quý II tăng',True),
 ('FPT','Công ty Cổ phần FPT','FPT báo lợi nhuận tăng trưởng hai chữ số',True),
 ('FPT','Công ty Cổ phần FPT','Chủ tịch FPT Retail nói về Long Châu',False),
 ('FRT','Công ty Cổ phần Bán lẻ Kỹ thuật số FPT','FPT Retail (FRT) chính thức gia nhập thị trường viễn thông',True),
 ('VCB','Ngân hàng TMCP Ngoại thương Việt Nam','VCB được khối ngoại mua ròng mạnh trong phiên',True),
]
failed=[]
for symbol,name,title,expected in CASES:
    got,conf,method=entity_relevance(symbol,name,title)
    print(symbol,got,conf,method,title)
    if got!=expected:failed.append((symbol,title,expected,got,method))
if failed:raise SystemExit('ENTITY TEST FAIL '+repr(failed))
print('V12 ENTITY RELEVANCE TEST PASS',len(CASES))
