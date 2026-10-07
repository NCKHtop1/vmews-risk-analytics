(function(){
'use strict';

var PROFILE_KEY='finquery-google-profile';
var AUTH_ENDPOINT=String(window.FINQUERY_AUTH_ENDPOINT||'https://vmews-risk-analytics-sojd.vercel.app/api/finquery-auth');
var LEGACY_WATCH_KEY='finquery-watchlist';
var GUEST_ID='guest';
var DATA_REFRESH_MS=60000;
var SYMBOL_POLL_MS=900;
var WATCH_POLL_MS=1200;
var state={
  profile:null,
  currentData:null,
  previousSnapshot:null,
  currentSnapshot:null,
  lastSymbol:'',
  watchSignature:'',
  refreshTimer:null
};

function byId(id){return document.getElementById(id);}
function nowIso(){return new Date().toISOString();}
function loadJson(key,fallback){
  try{
    var raw=localStorage.getItem(key);
    if(!raw)return fallback;
    return JSON.parse(raw);
  }catch(_){return fallback;}
}
function saveJson(key,value){
  try{localStorage.setItem(key,JSON.stringify(value));}catch(_){}
}
function removeKey(key){try{localStorage.removeItem(key);}catch(_){}}
function cleanSymbol(value){
  var s=String(value||'').trim().toUpperCase();
  return /^[A-Z]{3}$/.test(s)?s:'';
}
function cleanWatch(value){
  if(!Array.isArray(value))return[];
  var out=[];
  value.forEach(function(item){
    var s=cleanSymbol(item);
    if(s&&out.indexOf(s)<0)out.push(s);
  });
  return out;
}
function readLegacyWatch(){return cleanWatch(loadJson(LEGACY_WATCH_KEY,[]));}
function writeLegacyWatch(list){saveJson(LEGACY_WATCH_KEY,cleanWatch(list));}
function identityId(profile){return profile&&profile.sub?String(profile.sub):GUEST_ID;}
function userKey(name,profile){return 'finquery-user:'+identityId(profile===undefined?state.profile:profile)+':'+name;}
function activeWatch(){
  var owned=cleanWatch(loadJson(userKey('watchlist'),[]));
  return owned.length?owned:readLegacyWatch();
}
function setOwnedWatch(list){saveJson(userKey('watchlist'),cleanWatch(list));}
function safeImage(url){
  try{
    var u=new URL(String(url||''),location.href);
    return u.protocol==='https:'?u.href:'';
  }catch(_){return'';}
}
function firstName(profile){
  if(!profile)return'';
  var given=String(profile.givenName||'').trim();
  if(given)return given;
  return String(profile.name||profile.email||'').trim();
}
function decodeJwtPayload(token){
  try{
    var part=String(token||'').split('.')[1]||'';
    part=part.replace(/-/g,'+').replace(/_/g,'/');
    while(part.length%4)part+='=';
    var binary=atob(part);
    var bytes=new Uint8Array(binary.length);
    for(var i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
    return JSON.parse(new TextDecoder('utf-8').decode(bytes));
  }catch(_){return null;}
}
function normalizedProfile(payload){
  if(!payload||!payload.sub)return null;
  return{
    sub:String(payload.sub),
    name:String(payload.name||payload.email||'').trim(),
    givenName:String(payload.given_name||'').trim(),
    email:String(payload.email||'').trim(),
    picture:safeImage(payload.picture),
    provider:'google',
    signedAt:nowIso()
  };
}
function localProfile(name){
  var display=String(name||'').trim().replace(/\s+/g,' ');
  if(!display)return null;
  var parts=display.split(' ');
  return{
    sub:GUEST_ID,
    name:display,
    givenName:parts[parts.length-1]||display,
    email:'',
    picture:'',
    provider:'local',
    signedAt:nowIso()
  };
}
function currentClientId(){return String(window.FINQUERY_GOOGLE_CLIENT_ID||'').trim();}
function currentSymbol(){
  try{
    var c=window.FinancialMarket&&window.FinancialMarket.context?window.FinancialMarket.context():null;
    var s=cleanSymbol(c&&c.symbol);
    if(s)return s;
  }catch(_){}
  var input=byId('ticker');
  var fromInput=cleanSymbol(input&&input.value);
  if(fromInput)return fromInput;
  try{return cleanSymbol(new URLSearchParams(location.search).get('symbol'));}catch(_){return'';}
}
function currentView(){
  var h=String(location.hash||'');
  if(h==='#overview')return'Tổng quan';
  if(h==='#report-detail')return'Bảng số liệu';
  if(h==='#market')return'Thị trường';
  return'Báo cáo tài chính';
}
function symbolHref(symbol,hash){
  var u=new URL(location.href);
  u.searchParams.set('symbol',symbol);
  u.hash=hash||'#market';
  return u.pathname+u.search+u.hash;
}
function recordRecent(symbol){
  symbol=cleanSymbol(symbol);
  if(!symbol)return;
  var list=loadJson(userKey('recent'),[]);
  if(!Array.isArray(list))list=[];
  list=list.filter(function(item){return cleanSymbol(item&&item.symbol)!==symbol;});
  list.unshift({symbol:symbol,visitedAt:nowIso(),view:currentView(),href:symbolHref(symbol,location.hash||'#market')});
  saveJson(userKey('recent'),list.slice(0,8));
}
function migrateGuestData(profile){
  if(!profile||!profile.sub)return false;
  var guestWatch=cleanWatch(loadJson(userKey('watchlist',null),readLegacyWatch()));
  saveJson(userKey('watchlist',null),guestWatch);
  var accountWatch=cleanWatch(loadJson(userKey('watchlist',profile),[]));
  if(!accountWatch.length){
    accountWatch=guestWatch;
    saveJson(userKey('watchlist',profile),accountWatch);
  }
  var accountRecent=loadJson(userKey('recent',profile),[]);
  if(!Array.isArray(accountRecent)||!accountRecent.length){
    var guestRecent=loadJson(userKey('recent',null),[]);
    if(Array.isArray(guestRecent)&&guestRecent.length)saveJson(userKey('recent',profile),guestRecent.slice(0,8));
  }
  var legacy=readLegacyWatch();
  var changed=JSON.stringify(legacy)!==JSON.stringify(accountWatch);
  writeLegacyWatch(accountWatch);
  return changed;
}
function persistActiveWatch(){
  var list=readLegacyWatch();
  var sig=JSON.stringify(list);
  if(sig===state.watchSignature)return;
  state.watchSignature=sig;
  setOwnedWatch(list);
}
function greetingLabel(date){
  var h=date.getHours();
  if(h>=5&&h<11)return'Chào buổi sáng';
  if(h>=11&&h<14)return'Chào buổi trưa';
  if(h>=14&&h<18)return'Chào buổi chiều';
  return'Chào buổi tối';
}
function marketState(date){
  var day=date.getDay();
  if(day===0||day===6)return'Ngoài giờ giao dịch';
  var minutes=date.getHours()*60+date.getMinutes();
  if(minutes<540)return'Trước giờ mở cửa';
  if(minutes<=690)return'Thị trường đang giao dịch';
  if(minutes<780)return'Nghỉ giữa phiên';
  if(minutes<=885)return'Thị trường đang giao dịch';
  return'Phiên đã kết thúc';
}
function formatClock(value){
  if(!value||!Number.isFinite(Date.parse(value)))return'';
  try{
    return new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'}).format(new Date(value));
  }catch(_){return'';}
}
function fmtPct(value){
  var n=Number(value);
  if(!Number.isFinite(n))return'';
  return(n>0?'+':'')+new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2}).format(n)+'%';
}
function fmtX(value){
  var n=Number(value);
  if(!Number.isFinite(n))return'';
  return new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2}).format(n)+'x TB20';
}
function biasLabel(value){
  if(value==='bullish')return'Tích cực';
  if(value==='bearish')return'Tiêu cực';
  if(value==='neutral')return'Trung tính';
  return'';
}
function toneForNumber(value){
  var n=Number(value);
  if(!Number.isFinite(n)||n===0)return'';
  return n>0?'positive':'negative';
}
function relativeTime(value){
  var t=Date.parse(value||'');
  if(!Number.isFinite(t))return'';
  var mins=Math.max(0,Math.round((Date.now()-t)/60000));
  if(mins<1)return'Vừa xem';
  if(mins<60)return mins+' phút trước';
  var hours=Math.round(mins/60);
  if(hours<24)return hours+' giờ trước';
  var days=Math.round(hours/24);
  return days+' ngày trước';
}
function ensureMounts(){
  var header=document.querySelector('.header');
  if(header&&!byId('finquery-account')){
    var account=document.createElement('div');
    account.id='finquery-account';
    account.className='finquery-account';
    account.hidden=true;
    header.appendChild(account);
  }
  var main=document.querySelector('main');
  if(main&&!byId('finquery-personal-home')){
    var section=document.createElement('section');
    section.id='finquery-personal-home';
    section.className='finquery-personal-home';
    section.hidden=true;
    section.setAttribute('aria-label','Tổng quan cá nhân');
    main.insertBefore(section,main.firstChild);
  }
}
function makeRow(item){
  var a=document.createElement('a');
  a.className='finquery-personal-row';
  a.href=item.href||symbolHref(item.symbol,'#market');
  var left=document.createElement('span');
  left.className='finquery-personal-main';
  var symbol=document.createElement('span');
  symbol.className='finquery-personal-symbol';
  symbol.textContent=item.symbol||item.title||'';
  var detail=document.createElement('span');
  detail.className='finquery-personal-detail';
  detail.textContent=item.detail||'';
  left.appendChild(symbol);
  left.appendChild(detail);
  var value=document.createElement('span');
  value.className='finquery-personal-value'+(item.tone?' '+item.tone:'');
  value.textContent=item.value||'';
  a.appendChild(left);
  a.appendChild(value);
  return a;
}
function makeCard(title,items,id){
  var card=document.createElement('section');
  card.className='finquery-personal-card';
  card.id=id;
  if(!items||!items.length)card.hidden=true;
  var h=document.createElement('h3');
  h.textContent=title;
  var list=document.createElement('div');
  list.className='finquery-personal-list';
  (items||[]).forEach(function(item){list.appendChild(makeRow(item));});
  card.appendChild(h);
  card.appendChild(list);
  return card;
}
function renderHome(){
  var root=byId('finquery-personal-home');
  if(!root)return;
  root.replaceChildren();
  if(!state.profile){
    root.hidden=true;
    return;
  }
  root.hidden=false;
  var head=document.createElement('div');
  head.className='finquery-personal-head';
  var titleBox=document.createElement('div');
  var h=document.createElement('h2');
  h.textContent=greetingLabel(new Date())+', '+firstName(state.profile);
  var status=document.createElement('div');
  status.className='finquery-personal-status';
  var source=state.currentData&&state.currentData.sourceTime;
  status.textContent=marketState(new Date())+(source?' · Cập nhật '+formatClock(source):'');
  titleBox.appendChild(h);
  titleBox.appendChild(status);
  head.appendChild(titleBox);
  root.appendChild(head);

  var grid=document.createElement('div');
  grid.className='finquery-personal-grid';
  var content=personalContent();
  grid.appendChild(makeCard('Cần chú ý',content.attention,'finquery-attention'));
  grid.appendChild(makeCard('Từ lần bạn xem trước',content.changes,'finquery-changes'));
  grid.appendChild(makeCard('Gần đây',content.recent,'finquery-recent'));
  root.appendChild(grid);
  if(!content.attention.length&&!content.changes.length&&!content.recent.length)grid.hidden=true;
}
function accountMenu(profile){
  var menu=document.createElement('div');
  menu.className='finquery-account-menu';
  menu.hidden=true;

  var watch=document.createElement('button');
  watch.type='button';
  watch.textContent='Danh sách theo dõi';
  watch.addEventListener('click',function(){
    menu.hidden=true;
    var checkbox=byId('watch-only');
    if(checkbox&&!checkbox.checked){
      checkbox.checked=true;
      checkbox.dispatchEvent(new Event('change',{bubbles:true}));
    }
    var board=document.querySelector('.market-board');
    if(board)board.scrollIntoView({behavior:'smooth',block:'start'});
  });

  var recent=document.createElement('button');
  recent.type='button';
  recent.textContent='Gần đây';
  recent.addEventListener('click',function(){
    menu.hidden=true;
    var home=byId('finquery-personal-home');
    if(home)home.scrollIntoView({behavior:'smooth',block:'start'});
  });

  var logout=document.createElement('button');
  logout.type='button';
  logout.textContent=profile&&profile.provider==='local'?'Xóa hồ sơ':'Đăng xuất';
  logout.addEventListener('click',function(){signOut();});

  menu.appendChild(watch);
  menu.appendChild(recent);
  menu.appendChild(logout);
  return menu;
}
function renderAccount(){
  var root=byId('finquery-account');
  if(!root)return;
  root.replaceChildren();
  var clientId=currentClientId();
  if(state.profile){
    root.hidden=false;
    var button=document.createElement('button');
    button.type='button';
    button.className='finquery-account-profile';
    button.setAttribute('aria-haspopup','menu');
    button.setAttribute('aria-expanded','false');
    var image=safeImage(state.profile.picture);
    if(image){
      var img=document.createElement('img');
      img.src=image;
      img.alt='';
      img.referrerPolicy='no-referrer';
      button.appendChild(img);
    }
    var label=document.createElement('span');
    label.textContent=firstName(state.profile);
    button.appendChild(label);
    var menu=accountMenu(state.profile);
    button.addEventListener('click',function(event){
      event.stopPropagation();
      menu.hidden=!menu.hidden;
      button.setAttribute('aria-expanded',menu.hidden?'false':'true');
    });
    root.appendChild(button);
    root.appendChild(menu);
    document.addEventListener('click',function(){menu.hidden=true;button.setAttribute('aria-expanded','false');},{once:true});
    return;
  }
  root.hidden=false;
  if(!clientId){
    var localButton=document.createElement('button');
    localButton.type='button';
    localButton.className='finquery-account-profile finquery-local-trigger';
    localButton.textContent='Cá nhân hóa';
    var panel=document.createElement('form');
    panel.className='finquery-local-panel';
    panel.hidden=true;
    panel.autocomplete='off';
    var input=document.createElement('input');
    input.type='text';
    input.maxLength=60;
    input.placeholder='Tên hiển thị';
    input.setAttribute('aria-label','Tên hiển thị');
    var save=document.createElement('button');
    save.type='submit';
    save.textContent='Lưu';
    panel.appendChild(input);
    panel.appendChild(save);
    localButton.addEventListener('click',function(event){
      event.stopPropagation();
      panel.hidden=!panel.hidden;
      if(!panel.hidden)setTimeout(function(){input.focus();},0);
    });
    panel.addEventListener('click',function(event){event.stopPropagation();});
    panel.addEventListener('submit',function(event){
      event.preventDefault();
      var profile=localProfile(input.value);
      if(!profile)return;
      state.profile=profile;
      saveJson(PROFILE_KEY,profile);
      state.previousSnapshot=loadJson(userKey('snapshot'),null);
      state.watchSignature=JSON.stringify(readLegacyWatch());
      recordRecent(currentSymbol());
      renderAccount();
      refreshData();
    });
    root.appendChild(localButton);
    root.appendChild(panel);
    document.addEventListener('click',function(){panel.hidden=true;},{once:true});
    return;
  }
  var slot=document.createElement('div');
  slot.id='finquery-google-slot';
  slot.className='finquery-google-slot';
  root.appendChild(slot);
  loadGoogleIdentity().then(function(){
    if(!window.google||!window.google.accounts||!window.google.accounts.id)return;
    window.google.accounts.id.initialize({
      client_id:clientId,
      callback:handleGoogleCredential,
      auto_select:false,
      cancel_on_tap_outside:true
    });
    window.google.accounts.id.renderButton(slot,{
      type:'standard',
      theme:'outline',
      size:'medium',
      text:'signin_with',
      shape:'rectangular',
      logo_alignment:'left',
      width:190
    });
  }).catch(function(){
    root.replaceChildren();
    var fallback=document.createElement('button');
    fallback.type='button';
    fallback.className='finquery-account-profile';
    fallback.textContent='Cá nhân hóa';
    fallback.addEventListener('click',function(){renderAccount();});
    root.appendChild(fallback);
  });
}
var googlePromise=null;
function loadGoogleIdentity(){
  if(window.google&&window.google.accounts&&window.google.accounts.id)return Promise.resolve();
  if(googlePromise)return googlePromise;
  googlePromise=new Promise(function(resolve,reject){
    var existing=document.querySelector('script[data-finquery-google-identity]');
    if(existing){
      existing.addEventListener('load',resolve,{once:true});
      existing.addEventListener('error',reject,{once:true});
      return;
    }
    var script=document.createElement('script');
    script.src='https://accounts.google.com/gsi/client';
    script.async=true;
    script.defer=true;
    script.dataset.finqueryGoogleIdentity='1';
    script.onload=resolve;
    script.onerror=reject;
    document.head.appendChild(script);
  });
  return googlePromise;
}
function locallyValidatedGoogleProfile(credential){
  var payload=decodeJwtPayload(credential);
  var now=Math.floor(Date.now()/1000);
  var issuer=String(payload&&payload.iss||'');
  if(!payload||String(payload.aud||'')!==currentClientId())return null;
  if(Number(payload.exp||0)<=now)return null;
  if(payload.email_verified!==true&&String(payload.email_verified||'').toLowerCase()!=='true')return null;
  if(issuer!=='accounts.google.com'&&issuer!=='https://accounts.google.com')return null;
  return normalizedProfile(payload);
}
async function verifyGoogleCredential(credential){
  try{
    var verified=await fetch(AUTH_ENDPOINT,{
      method:'POST',
      mode:'cors',
      cache:'no-store',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({credential:credential,clientId:currentClientId()}),
      signal:AbortSignal.timeout(5000)
    });
    var body=await verified.json().catch(function(){return{};});
    if(verified.ok&&body.ok&&body.profile){
      return normalizedProfile({
        sub:body.profile.sub,
        name:body.profile.name,
        given_name:body.profile.givenName,
        email:body.profile.email,
        picture:body.profile.picture
      });
    }
  }catch(_){}
  return locallyValidatedGoogleProfile(credential);
}
async function handleGoogleCredential(response){
  var credential=String(response&&response.credential||'').trim();
  if(!credential)return;
  var profile=await verifyGoogleCredential(credential);
  if(!profile){
    try{
      if(window.google&&window.google.accounts&&window.google.accounts.id)window.google.accounts.id.disableAutoSelect();
    }catch(_){}
    return;
  }
  saveJson(userKey('watchlist',null),readLegacyWatch());
  var changed=migrateGuestData(profile);
  state.profile=profile;
  saveJson(PROFILE_KEY,profile);
  state.previousSnapshot=loadJson(userKey('snapshot'),null);
  state.watchSignature=JSON.stringify(readLegacyWatch());
  recordRecent(currentSymbol());
  renderAccount();
  refreshData();
  if(changed)setTimeout(function(){location.reload();},80);
}
function signOut(){
  persistActiveWatch();
  var accountWatch=readLegacyWatch();
  saveJson(userKey('watchlist'),accountWatch);
  var guest=cleanWatch(loadJson(userKey('watchlist',null),[]));
  state.profile=null;
  removeKey(PROFILE_KEY);
  writeLegacyWatch(guest);
  try{
    if(window.google&&window.google.accounts&&window.google.accounts.id)window.google.accounts.id.disableAutoSelect();
  }catch(_){}
  location.reload();
}
function fetchJson(path){
  var url=new URL('market/'+path,location.href);
  url.searchParams.set('v',String(Math.floor(Date.now()/60000)));
  return fetch(url.toString(),{cache:'no-store'}).then(function(r){
    if(!r.ok)throw new Error('HTTP '+r.status);
    return r.json();
  });
}
function snapshotFromData(data){
  if(!data)return null;
  var watch=activeWatch();
  var recent=loadJson(userKey('recent'),[]);
  if(!Array.isArray(recent))recent=[];
  var symbols=[];
  watch.concat(recent.map(function(x){return cleanSymbol(x&&x.symbol);})).forEach(function(s){
    s=cleanSymbol(s);
    if(s&&symbols.indexOf(s)<0&&symbols.length<12)symbols.push(s);
  });
  var itemsBySymbol={};
  (data.watch&&Array.isArray(data.watch.items)?data.watch.items:[]).forEach(function(item){
    var s=cleanSymbol(item&&item.symbol);
    if(s)itemsBySymbol[s]=item;
  });
  var result={capturedAt:nowIso(),sourceTime:data.sourceTime||'',risk:null,symbols:{}};
  if(data.risk&&data.risk.overall){
    result.risk={
      score:Number(data.risk.overall.score),
      label:String(data.risk.overall.level&&data.risk.overall.level.label||'')
    };
  }
  symbols.forEach(function(symbol){
    var q=data.quotes&&data.quotes.quotes&&data.quotes.quotes[symbol]||{};
    var t=data.scanner&&data.scanner.symbols&&data.scanner.symbols[symbol]||{};
    var w=itemsBySymbol[symbol]||{};
    result.symbols[symbol]={
      price:Number(q.price),
      changePct:Number(q.changePct),
      volumeRatio20:Number(t.volumeRatio20),
      bias:String(t.bias||''),
      signals:Array.isArray(t.signals)?t.signals.map(function(x){return String(x&&x.id||'');}).filter(Boolean):[],
      watchScore:Number(w.score),
      watchRank:Number(w.rank),
      inWatchToday:Boolean(itemsBySymbol[symbol])
    };
  });
  return result;
}
function attentionRows(){
  if(!state.currentSnapshot)return[];
  var watch=activeWatch();
  var symbols=watch.length?watch:loadJson(userKey('recent'),[]).map(function(x){return cleanSymbol(x&&x.symbol);});
  var scored=[];
  symbols.forEach(function(symbol){
    symbol=cleanSymbol(symbol);
    var x=state.currentSnapshot.symbols[symbol];
    if(!symbol||!x)return;
    var score=0;
    if(x.inWatchToday)score+=50;
    if(Number.isFinite(x.changePct)&&Math.abs(x.changePct)>=2)score+=22;
    if(Number.isFinite(x.volumeRatio20)&&x.volumeRatio20>=1.5)score+=18;
    if(x.bias==='bullish'||x.bias==='bearish')score+=10;
    if(!score)return;
    var bits=[];
    if(Number.isFinite(x.changePct))bits.push(fmtPct(x.changePct));
    if(Number.isFinite(x.volumeRatio20)&&x.volumeRatio20>=1.2)bits.push('Khối lượng '+fmtX(x.volumeRatio20));
    if(x.inWatchToday&&Number.isFinite(x.watchRank))bits.push('Đáng xem #'+x.watchRank);
    var value=biasLabel(x.bias);
    scored.push({
      score:score,
      symbol:symbol,
      detail:bits.slice(0,2).join(' · '),
      value:value,
      tone:toneForNumber(x.changePct),
      href:symbolHref(symbol,'#market')
    });
  });
  return scored.sort(function(a,b){return b.score-a.score;}).slice(0,4);
}
function changeRows(){
  var prev=state.previousSnapshot;
  var cur=state.currentSnapshot;
  if(!prev||!cur)return[];
  var rows=[];
  if(prev.risk&&cur.risk&&Number.isFinite(prev.risk.score)&&Number.isFinite(cur.risk.score)){
    var d=cur.risk.score-prev.risk.score;
    if(Math.abs(d)>=4){
      rows.push({
        score:Math.abs(d)+30,
        symbol:'Thị trường',
        detail:'Rủi ro '+new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(prev.risk.score)+' → '+new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(cur.risk.score),
        value:cur.risk.label||'',
        tone:d>0?'negative':'positive',
        href:'#market'
      });
    }
  }
  Object.keys(cur.symbols||{}).forEach(function(symbol){
    var a=prev.symbols&&prev.symbols[symbol];
    var b=cur.symbols[symbol];
    if(!a||!b)return;
    var oldBias=biasLabel(a.bias);
    var newBias=biasLabel(b.bias);
    if(oldBias&&newBias&&oldBias!==newBias){
      rows.push({score:80,symbol:symbol,detail:oldBias+' → '+newBias,value:newBias,tone:b.bias==='bullish'?'positive':b.bias==='bearish'?'negative':'',href:symbolHref(symbol,'#market')});
      return;
    }
    if(!a.inWatchToday&&b.inWatchToday){
      rows.push({score:70,symbol:symbol,detail:'Vào Đáng xem hôm nay',value:Number.isFinite(b.watchRank)?'#'+b.watchRank:'',tone:'positive',href:symbolHref(symbol,'#market')});
      return;
    }
    if(a.inWatchToday&&b.inWatchToday&&Number.isFinite(a.watchRank)&&Number.isFinite(b.watchRank)&&Math.abs(a.watchRank-b.watchRank)>=2){
      rows.push({score:55+Math.abs(a.watchRank-b.watchRank),symbol:symbol,detail:'Hạng '+a.watchRank+' → '+b.watchRank,value:'#'+b.watchRank,tone:b.watchRank<a.watchRank?'positive':'negative',href:symbolHref(symbol,'#market')});
      return;
    }
    if(Number.isFinite(a.volumeRatio20)&&Number.isFinite(b.volumeRatio20)&&a.volumeRatio20<1.5&&b.volumeRatio20>=1.5){
      rows.push({score:50,symbol:symbol,detail:'Khối lượng '+fmtX(a.volumeRatio20)+' → '+fmtX(b.volumeRatio20),value:fmtX(b.volumeRatio20),tone:'',href:symbolHref(symbol,'#market')});
      return;
    }
    if(Number.isFinite(a.changePct)&&Number.isFinite(b.changePct)&&Math.abs(b.changePct-a.changePct)>=1){
      rows.push({score:35+Math.abs(b.changePct-a.changePct),symbol:symbol,detail:'Biến động '+fmtPct(a.changePct)+' → '+fmtPct(b.changePct),value:fmtPct(b.changePct),tone:toneForNumber(b.changePct),href:symbolHref(symbol,'#market')});
    }
  });
  return rows.sort(function(a,b){return b.score-a.score;}).slice(0,5);
}
function recentRows(){
  var list=loadJson(userKey('recent'),[]);
  if(!Array.isArray(list))return[];
  return list.slice(0,5).map(function(item){
    var symbol=cleanSymbol(item&&item.symbol);
    return{
      symbol:symbol,
      detail:String(item&&item.view||'Báo cáo tài chính'),
      value:relativeTime(item&&item.visitedAt),
      href:item&&item.href?String(item.href):symbolHref(symbol,'#market')
    };
  }).filter(function(x){return x.symbol;});
}
function personalContent(){
  return{attention:attentionRows(),changes:changeRows(),recent:recentRows()};
}
function refreshData(){
  if(!state.profile){
    renderHome();
    return Promise.resolve();
  }
  return Promise.all([
    fetchJson('quotes.json'),
    fetchJson('technical-signals.json'),
    fetchJson('watch-today.json'),
    fetchJson('risk-monitor.json')
  ]).then(function(values){
    var quotes=values[0],scanner=values[1],watch=values[2],risk=values[3];
    state.currentData={
      quotes:quotes,
      scanner:scanner,
      watch:watch,
      risk:risk,
      sourceTime:quotes.latestSourceTime||scanner.sourceTime||watch.sourceTime||risk.sourceTime||''
    };
    state.currentSnapshot=snapshotFromData(state.currentData);
    renderHome();
  }).catch(function(){renderHome();});
}
function commitSnapshot(){
  if(state.profile&&state.currentSnapshot)saveJson(userKey('snapshot'),state.currentSnapshot);
}
function initProfile(){
  var stored=loadJson(PROFILE_KEY,null);
  if(stored&&stored.sub){
    state.profile={
      sub:String(stored.sub),
      name:String(stored.name||stored.email||'').trim(),
      givenName:String(stored.givenName||'').trim(),
      email:String(stored.email||'').trim(),
      picture:safeImage(stored.picture),
      provider:String(stored.provider||((stored.email||stored.picture)?'google':'local')),
      signedAt:String(stored.signedAt||'')
    };
  }
  if(state.profile){
    var accountWatch=cleanWatch(loadJson(userKey('watchlist'),[]));
    if(accountWatch.length)writeLegacyWatch(accountWatch);
    else saveJson(userKey('watchlist'),readLegacyWatch());
    state.previousSnapshot=loadJson(userKey('snapshot'),null);
  }else{
    var guestWatch=cleanWatch(loadJson(userKey('watchlist',null),readLegacyWatch()));
    saveJson(userKey('watchlist',null),guestWatch);
  }
  state.watchSignature=JSON.stringify(readLegacyWatch());
}
function observeSymbol(){
  var symbol=currentSymbol();
  if(symbol&&symbol!==state.lastSymbol){
    state.lastSymbol=symbol;
    recordRecent(symbol);
    if(state.profile)renderHome();
  }
}
function init(){
  ensureMounts();
  initProfile();
  renderAccount();
  observeSymbol();
  refreshData();
  setInterval(observeSymbol,SYMBOL_POLL_MS);
  setInterval(persistActiveWatch,WATCH_POLL_MS);
  state.refreshTimer=setInterval(refreshData,DATA_REFRESH_MS);
  window.addEventListener('hashchange',function(){observeSymbol();if(state.profile)renderHome();});
  window.addEventListener('pagehide',function(){persistActiveWatch();commitSnapshot();});
  document.addEventListener('visibilitychange',function(){
    if(document.visibilityState==='hidden'){persistActiveWatch();commitSnapshot();}
    else if(document.visibilityState==='visible'){observeSymbol();refreshData();}
  });
}

window.FinQueryPersonalization={
  refresh:function(){observeSymbol();return refreshData();},
  profile:function(){return state.profile?Object.assign({},state.profile):null;}
};

if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
else init();
})();