(function(){'use strict';
const CHEVRON='<span class="section-chevron-icon" aria-hidden="true"><svg viewBox="0 0 20 20" fill="none" focusable="false"><path d="M5.25 7.75 10 12.25l4.75-4.5"/></svg></span>';
const configs=[
 {section:'investment-ideas',body:'investment-ideas-body',toggle:'investment-ideas-toggle',chevron:'investment-ideas-chevron',openLabel:'Thu gọn Investment Ideas',closedLabel:'Mở Investment Ideas'},
 {section:'macro',body:'macro-body',toggle:'macro-toggle',chevron:'macro-chevron',openLabel:'Thu gọn Macro & ESG',closedLabel:'Mở Macro & ESG'}
];
function ensureIcon(button){if(button&&!button.querySelector('.section-chevron-icon'))button.innerHTML=CHEVRON;}
function setOpen(c,open){
 const section=document.getElementById(c.section),body=document.getElementById(c.body),toggle=document.getElementById(c.toggle),chevron=document.getElementById(c.chevron);
 if(!section||!body)return;
 ensureIcon(chevron);
 body.hidden=!open;
 section.classList.toggle('is-collapsed',!open);
 section.classList.toggle('is-expanded',open);
 toggle?.setAttribute('aria-expanded',String(open));
 chevron?.setAttribute('aria-expanded',String(open));
 if(chevron){
   chevron.classList.toggle('is-open',open);
   chevron.setAttribute('aria-label',open?c.openLabel:c.closedLabel);
 }
}
function bind(c){
 const toggle=document.getElementById(c.toggle),chevron=document.getElementById(c.chevron);
 ensureIcon(chevron);
 setOpen(c,false);
 toggle?.addEventListener('click',()=>setOpen(c,document.getElementById(c.body)?.hidden));
 chevron?.addEventListener('click',()=>setOpen(c,document.getElementById(c.body)?.hidden));
}
configs.forEach(bind);
window.FinSectionCollapse={
 open(id){const c=configs.find(x=>x.section===id);if(c)setOpen(c,true);},
 close(id){const c=configs.find(x=>x.section===id);if(c)setOpen(c,false);},
 toggle(id){const c=configs.find(x=>x.section===id);if(c)setOpen(c,document.getElementById(c.body)?.hidden);},
 isOpen(id){const c=configs.find(x=>x.section===id);return c?!document.getElementById(c.body)?.hidden:false;}
};
})();