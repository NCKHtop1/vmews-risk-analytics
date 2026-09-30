(function(root){'use strict';
const CATALOG=[
 {id:'price',label:'Giá',group:'Price',unit:'đ',decimals:0},
 {id:'changePct',label:'Thay đổi phiên',group:'Price',unit:'%',decimals:2},
 {id:'sma20',label:'SMA 20',group:'Trend',unit:'đ',decimals:0},
 {id:'sma50',label:'SMA 50',group:'Trend',unit:'đ',decimals:0},
 {id:'sma200',label:'SMA 200',group:'Trend',unit:'đ',decimals:0},
 {id:'ema9',label:'EMA 9',group:'Trend',unit:'đ',decimals:0},
 {id:'ema20',label:'EMA 20',group:'Trend',unit:'đ',decimals:0},
 {id:'ema50',label:'EMA 50',group:'Trend',unit:'đ',decimals:0},
 {id:'vwma20',label:'VWMA 20',group:'Trend',unit:'đ',decimals:0},
 {id:'supertrend',label:'Supertrend',group:'Trend',unit:'đ',decimals:0},
 {id:'supertrendDir',label:'Supertrend Direction',group:'Trend',unit:'',decimals:0},
 {id:'adx14',label:'ADX 14',group:'Trend',unit:'',decimals:1},
 {id:'rsi14',label:'RSI 14',group:'Momentum',unit:'',decimals:1},
 {id:'macd',label:'MACD',group:'Momentum',unit:'',decimals:2},
 {id:'macdSignal',label:'MACD Signal',group:'Momentum',unit:'',decimals:2},
 {id:'macdHistogram',label:'MACD Histogram',group:'Momentum',unit:'',decimals:2},
 {id:'stochK',label:'Stochastic %K',group:'Momentum',unit:'',decimals:1},
 {id:'stochD',label:'Stochastic %D',group:'Momentum',unit:'',decimals:1},
 {id:'cci20',label:'CCI 20',group:'Momentum',unit:'',decimals:1},
 {id:'roc10',label:'ROC 10',group:'Momentum',unit:'%',decimals:2},
 {id:'willr14',label:'Williams %R',group:'Momentum',unit:'',decimals:1},
 {id:'mfi14',label:'MFI 14',group:'Momentum',unit:'',decimals:1},
 {id:'bbUpper',label:'Bollinger Upper',group:'Volatility',unit:'đ',decimals:0},
 {id:'bbMiddle',label:'Bollinger Middle',group:'Volatility',unit:'đ',decimals:0},
 {id:'bbLower',label:'Bollinger Lower',group:'Volatility',unit:'đ',decimals:0},
 {id:'bbPctB',label:'Bollinger %B',group:'Volatility',unit:'',decimals:2},
 {id:'atr14',label:'ATR 14',group:'Volatility',unit:'đ',decimals:0},
 {id:'volume',label:'Khối lượng',group:'Volume',unit:'cp',decimals:0},
 {id:'volumeSma20',label:'Volume SMA 20',group:'Volume',unit:'cp',decimals:0},
 {id:'volumeRatio20',label:'Volume / SMA20',group:'Volume',unit:'x',decimals:2},
 {id:'obv',label:'OBV',group:'Volume',unit:'',decimals:0},
 {id:'obvSlope5',label:'OBV Δ5',group:'Volume',unit:'',decimals:0},
 {id:'cmf20',label:'CMF 20',group:'Volume',unit:'',decimals:3}
];
const MAP=Object.fromEntries(CATALOG.map(x=>[x.id,x]));
const OPS=[
 {id:'gt',label:'>'},{id:'gte',label:'≥'},{id:'lt',label:'<'},{id:'lte',label:'≤'},
 {id:'cross_up',label:'cắt lên'},{id:'cross_down',label:'cắt xuống'},
 {id:'rising',label:'đang tăng'},{id:'falling',label:'đang giảm'}
];
const DEFAULTS={
 rsi14:{op:'lte',rightType:'value',rightValue:30},
 macd:{op:'cross_up',rightType:'indicator',rightIndicator:'macdSignal'},
 macdHistogram:{op:'cross_up',rightType:'value',rightValue:0},
 ema9:{op:'cross_up',rightType:'indicator',rightIndicator:'ema20'},
 ema20:{op:'gt',rightType:'indicator',rightIndicator:'ema50'},
 sma20:{op:'gt',rightType:'indicator',rightIndicator:'sma50'},
 price:{op:'cross_up',rightType:'indicator',rightIndicator:'sma20'},
 adx14:{op:'gte',rightType:'value',rightValue:25},
 volumeRatio20:{op:'gte',rightType:'value',rightValue:1.5},
 stochK:{op:'cross_up',rightType:'indicator',rightIndicator:'stochD'},
 cci20:{op:'gt',rightType:'value',rightValue:100},
 roc10:{op:'gt',rightType:'value',rightValue:0},
 willr14:{op:'gt',rightType:'value',rightValue:-50},
 mfi14:{op:'lte',rightType:'value',rightValue:20},
 cmf20:{op:'gt',rightType:'value',rightValue:0},
 bbPctB:{op:'lte',rightType:'value',rightValue:0.05},
 supertrendDir:{op:'gte',rightType:'value',rightValue:1},
 changePct:{op:'gte',rightType:'value',rightValue:1}
};
const PRESETS={
 macd_rsi:{name:'MACD + RSI xác nhận',join:'AND',scope:'LIVE',conditions:[
  {left:'macd',op:'cross_up',rightType:'indicator',rightIndicator:'macdSignal'},
  {left:'rsi14',op:'gte',rightType:'value',rightValue:50}
 ]},
 ema_adx:{name:'EMA Trend + ADX',join:'AND',scope:'LIVE',conditions:[
  {left:'ema9',op:'gt',rightType:'indicator',rightIndicator:'ema20'},
  {left:'ema20',op:'gt',rightType:'indicator',rightIndicator:'ema50'},
  {left:'adx14',op:'gte',rightType:'value',rightValue:25}
 ]},
 bollinger_rebound:{name:'Bollinger Rebound',join:'AND',scope:'ALL',conditions:[
  {left:'bbPctB',op:'lte',rightType:'value',rightValue:0.05},
  {left:'rsi14',op:'lte',rightType:'value',rightValue:35}
 ]},
 breakout_volume:{name:'Breakout + Volume',join:'AND',scope:'LIVE',conditions:[
  {left:'price',op:'gt',rightType:'indicator',rightIndicator:'sma20'},
  {left:'volumeRatio20',op:'gte',rightType:'value',rightValue:1.5},
  {left:'roc10',op:'gt',rightType:'value',rightValue:0}
 ]},
 momentum_recovery:{name:'Momentum hồi phục',join:'AND',scope:'LIVE',conditions:[
  {left:'rsi14',op:'cross_up',rightType:'value',rightValue:30},
  {left:'macdHistogram',op:'cross_up',rightType:'value',rightValue:0}
 ]}
};
function finite(v){return Number.isFinite(Number(v))?Number(v):null;}
function condition(left){const d=DEFAULTS[left]||{op:'gt',rightType:'value',rightValue:0};return{id:'c'+Date.now().toString(36)+Math.random().toString(36).slice(2,7),left,...d};}
function normalizeCondition(c){return{...condition(c?.left||'rsi14'),...c,id:c?.id||('c'+Math.random().toString(36).slice(2))};}
function scopeMatches(row,scope){const tier=String(row?.tier||'').toUpperCase();return scope==='ALL'||!scope||(scope==='LIVE'&&tier!=='DISCOVERY')||tier===scope;}
function rightValue(row,c,which){if(c.rightType==='indicator')return finite(row?.[which]?.[c.rightIndicator]);return finite(c.rightValue);}
function evaluateCondition(row,c){
 const left=finite(row?.current?.[c.left]),prevLeft=finite(row?.previous?.[c.left]);
 if(left===null)return false;
 if(c.op==='rising')return prevLeft!==null&&left>prevLeft;
 if(c.op==='falling')return prevLeft!==null&&left<prevLeft;
 const right=rightValue(row,c,'current');if(right===null)return false;
 if(c.op==='gt')return left>right;if(c.op==='gte')return left>=right;if(c.op==='lt')return left<right;if(c.op==='lte')return left<=right;
 const prevRight=c.rightType==='indicator'?rightValue(row,c,'previous'):right;
 if(prevLeft===null||prevRight===null)return false;
 if(c.op==='cross_up')return prevLeft<=prevRight&&left>right;
 if(c.op==='cross_down')return prevLeft>=prevRight&&left<right;
 return false;
}
function evaluateStrategy(row,strategy){if(!scopeMatches(row,strategy?.scope||'ALL'))return false;const cs=(strategy?.conditions||[]).filter(c=>MAP[c.left]);if(!cs.length)return false;return String(strategy?.join||'AND').toUpperCase()==='OR'?cs.some(c=>evaluateCondition(row,c)):cs.every(c=>evaluateCondition(row,c));}
function scan(snapshot,strategy){const rows=Object.values(snapshot?.symbols||{}).filter(r=>evaluateStrategy(r,strategy));return rows.sort((a,b)=>{const ta={CORE:0,LIQUID:1,DISCOVERY:2},x=(ta[a.tier]??3)-(ta[b.tier]??3);return x||String(a.symbol).localeCompare(String(b.symbol));});}
function label(id){return MAP[id]?.label||id;}
function opLabel(id){return OPS.find(x=>x.id===id)?.label||id;}
function describe(c){if(!c)return'';const right=c.op==='rising'||c.op==='falling'?'':c.rightType==='indicator'?label(c.rightIndicator):String(c.rightValue);return(label(c.left)+' '+opLabel(c.op)+' '+right).trim();}
const api={CATALOG,MAP,OPS,PRESETS,condition,normalizeCondition,evaluateCondition,evaluateStrategy,scan,label,opLabel,describe,scopeMatches};
root.FinStrategyEngine=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
