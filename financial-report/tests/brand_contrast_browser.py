#!/usr/bin/env python3
"""Browser-computed FinQuery contrast audit using real source HTML/CSS and static fixtures.

Does NOT authenticate, call an API, or alter application logic.
The gradient estimate below chooses a dominant solid gradient stop and prints
diagnostics. Every critical contrast failure blocks the visual-only PR.
"""
import json
import re
import shutil
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "financial-report" / "frontend"
CSS = ("style.css", "market.css", "risk-monitor.css",
       "portfolio-intelligence.css", "responsive-system.css", "fonts.css")

JS_AUDIT = r"""
const pick = (x) => document.querySelector(x);
const parse = s => {
 if(!s) return null;
 const m = String(s).match(/rgba?\(\s*(\d+(?:\.\d+)?)\D+(\d+(?:\.\d+)?)\D+(\d+(?:\.\d+)?)(?:\D+([\d.]+))?\s*\)/);
 if(!m) return null;
 return [Number(m[1]),Number(m[2]),Number(m[3]),m[4]===undefined?1:Number(m[4])];
};
const dominant = el => {
 for(let node=el;node;node=node.parentElement){
   const c=getComputedStyle(node);
   if(c.backgroundImage!=='none'){
     // Read high-opacity gradient colors; avoid treating transparent glow as surface.
     const g=[...c.backgroundImage.matchAll(/rgba?\([^)]+\)/g)]
       .map(m=>parse(m[0])).filter(v=>v&&v[3]>=.85);
     if(g.length) return {rgba:g[g.length-1],selector:node.tagName.toLowerCase()+
       (node.id?'#'+node.id:node.className&&typeof node.className==='string'?'.'+node.className.trim().split(/\s+/).slice(0,2).join('.'):''),
       gradient:true};
   }
   const bg=parse(c.backgroundColor);
   if(bg&&bg[3]>=.97)return {rgba:bg,selector:node.tagName,gradient:false};
 }
 return {rgba:[255,255,255,1],selector:'canvas',gradient:false};
};
const lin=v=>{v/=255;return v<=.04045?v/12.92:Math.pow((v+.055)/1.055,2.4);};
const light=v=>.2126*lin(v[0])+.7152*lin(v[1])+.0722*lin(v[2]);
const contrast=(a,b)=>{let x=light(a),y=light(b);return Number(((Math.max(x,y)+.05)/(Math.min(x,y)+.05)).toFixed(2));};
return arguments[0].map(sel=>{
 const el=pick(sel);
 if(!el)return {sel,missing:true};
 const st=getComputedStyle(el);
 const fg=parse(st.color),bg=dominant(el);
 const r=el.getBoundingClientRect();
 return {sel,text:(el.innerText||el.textContent||'').trim().slice(0,45),
  fontSize:st.fontSize,weight:st.fontWeight,color:st.color,
  background:bg.rgba.map(x=>Math.round(x*100)/100),
  backgroundFrom:bg.selector,gradient:bg.gradient,
  ratio:fg?contrast(fg,bg.rgba):0,
  display:st.display,box:{width:Math.round(r.width),height:Math.round(r.height)}};
});
"""
TESTS={
  "index.html":[
   ".header .finquery-brand .brand-copy strong",
   ".header nav[aria-label='Điều hướng nền tảng'] a",
   ".header nav[aria-label='Điều hướng nền tảng'] a.active",
   ".intro h1",
   ".market-top h2",
   ".market-section .finquery-workspace-tabs button.active",
   ".portfolio-head h1",
   ".portfolio-tabs button.active",
   ".risk-page-head h1",
   ".risk-panel h3",
   ".strategy-builder-head h2",
   ".macro-head h2",
   "#market .market-subtitle",
   "#chart-terminal .market-controls label",
   "#finquery-nav-toggle",
   ".research-ai .research-ai-head h3",
  ],
  "forecast-final.html":[
   ".top .fq-forecast-name",
   ".top .fq-forecast-descriptor",
   ".sectionNav a",
   ".sectionNav a.active",
   ".marketCommand .leadersHeader h2",
   ".marketCommand .commandIndex",
   ".marketCommand .snapshotBadge",
   ".marketCommand .filterChip.active",
   ".panel h2",
   ".forecastCard span",
   ".badge",
   ".heroIndex",
   ".hero h1",
   ".search input",
  ],
  "login.html":["h1",".subtitle","main p","#status","#switch-account"],
  "admin.html":["header h1","header small","header a","main h2","main th","#message"],
}

def setup_files(folder):
    html=(FRONT/"index.html").read_text(encoding="utf-8")
    html=re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
    html=html.replace('<body class="site-locked">','<body>')
    html=html.replace('<form id="site-unlock-form"', '<form id="site-unlock-form" hidden')
    (folder/"index.html").write_text(html,encoding="utf-8")
    for item in CSS:
        shutil.copy2(FRONT/item,folder/item)
    forecast=(ROOT/"forecast-final.html").read_text(encoding="utf-8")
    forecast=re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", forecast, flags=re.I)
    forecast=forecast.replace('./forecast-portfolio-v14.css','./forecast-portfolio-v14.css')
    (folder/"forecast-final.html").write_text(forecast,encoding="utf-8")
    shutil.copy2(ROOT/"forecast-portfolio-v14.css",folder/"forecast-portfolio-v14.css")
    for page in ("login.html","admin.html"):
        content=(ROOT/"finquery-access"/page).read_text(encoding="utf-8")
        content=re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", content,flags=re.I)
        (folder/page).write_text(content,encoding="utf-8")
    shutil.copy2(FRONT/"favicon.svg",folder/"favicon.svg")

def run():
    failures=[]
    with tempfile.TemporaryDirectory(prefix="finquery-contrast-") as tmp:
        folder=Path(tmp)
        setup_files(folder)
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,directory=tmp,**kwargs)
            def log_message(self,*args):
                pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        opt=Options()
        for flag in ("--headless=new","--no-sandbox","--disable-dev-shm-usage","--hide-scrollbars"):
            opt.add_argument(flag)
        driver=webdriver.Chrome(options=opt)
        try:
            for width,height in [(390,850),(1440,900)]:
                driver.set_window_size(width,height)
                driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",{
                    "width":width,"height":height,"deviceScaleFactor":1,"mobile":width<=768})
                for page,selectors in TESTS.items():
                    driver.get(f"http://127.0.0.1:{server.server_port}/{page}")
                    if page=="index.html":
                        driver.execute_script("""
                          document.querySelectorAll(
                            '#market,#portfolio,#risk-monitor,#strategy-builder,#overview'
                          ).forEach(el=>el.hidden=false);
                          const s=document.createElement('style');
                          s.textContent='#risk-monitor,#portfolio,#strategy-builder,#macro,#overview{display:block!important}';
                          document.head.appendChild(s);
                          document.querySelector('#macro')?.classList.remove('is-collapsed');
                          document.querySelector('.header')?.classList.add('finquery-nav-open');
                        """)
                    measurements=driver.execute_script(JS_AUDIT,selectors)
                    print("FINQUERY_CONTRAST",page,width,json.dumps(measurements,ensure_ascii=False),flush=True)
                    for item in measurements:
                        if item.get("missing"):
                            # Some components are generated by JS, so report but don't fabricate.
                            continue
                        if item["display"]=="none" or not item["text"]:
                            continue
                        if item["ratio"]<4.5:
                            failures.append({"page":page,"width":width,"sel":item["sel"],
                                             "ratio":item["ratio"],"text":item["text"],
                                             "colors":[item["color"],item["background"]]})
                    if page in ("index.html","forecast-final.html"):
                        image=f"finquery-{page.split('.')[0]}-{width}.png"
                        driver.save_screenshot(str(folder/image))
            print("FINQUERY_CONTRAST_FAILURES",json.dumps(failures,ensure_ascii=False),flush=True)
            if failures:
                raise AssertionError(f"{len(failures)} computed contrast violations (WCAG AA 4.5:1)")
            print("FINQUERY_Q_DATA_CONTRAST_BROWSER_PASS",flush=True)
        finally:
            driver.quit()
            server.shutdown()

if __name__=="__main__":
    run()
