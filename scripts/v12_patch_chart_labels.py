from pathlib import Path

p=Path('forecast-final-v12.js')
s=p.read_text(encoding='utf-8')
old='c.fillStyle=q.price>=cur?"#78c89b":"#e77b7b";c.fillText(price(q.price),xx-27,yy+(q.price>=cur?-13:19));c.font="10px Inter,Arial";c.fillText(`${delta>=0?"+":""}${pct(delta)}`,xx-20,yy+(q.price>=cur?-25:31));hoverPoints.push({kind:"forecast",x:xx,y:yy,data:q})'
new='const labelAbove=hi-P.t>38,labelY=labelAbove?hi-12:Math.min(H-P.b-12,lo+22);c.save();c.font="600 10px Inter,Arial";c.textAlign="center";c.fillStyle=q.price>=cur?"#78c89b":"#e77b7b";if(W>900)c.fillText(`${price(q.price)} · ${delta>=0?"+":""}${pct(delta)}`,xx,labelY);else c.fillText(`${delta>=0?"+":""}${pct(delta)}`,xx,labelY);c.restore();hoverPoints.push({kind:"forecast",x:xx,y:yy,data:q})'
if old not in s:
    raise SystemExit('forecast label block not found; refusing fuzzy patch')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
print('V12 FORECAST LABEL PATCH PASS',len(s))
