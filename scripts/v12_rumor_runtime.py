import re
import unicodedata
import v12_evidence as evidence

def _ascii_norm(s):
    x=str(s or '').replace('đ','d').replace('Đ','D')
    x=unicodedata.normalize('NFKD',x).encode('ascii','ignore').decode().lower()
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',x)).strip()

evidence._normalize_text=_ascii_norm
evidence.DENIAL_TERMS=(
    'phu nhan','bac bo','khong co chuyen','khong chinh xac','sai su that','tin gia',
    'deny','denies','denied','false rumor','not true','incorrect information'
)

def apply():
    return evidence
