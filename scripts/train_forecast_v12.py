import pathlib
ROOT=pathlib.Path(__file__).resolve().parent
parts=[]
for p in sorted((ROOT/'v12_train_parts').glob('*.pyinc')):
    parts.append(p.read_text(encoding='utf-8'))
code='\n'.join(parts)
exec(compile(code,str(ROOT/'v12_train_parts'/'assembled.py'),'exec'),globals(),globals())
