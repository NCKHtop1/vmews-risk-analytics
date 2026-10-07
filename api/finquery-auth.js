const MAX_CREDENTIAL_LENGTH=8192;

function allowOrigin(request){
  const origin=String(request.headers?.origin||'');
  const configured=String(process.env.FINQUERY_ALLOWED_ORIGINS||'')
    .split(',').map(x=>x.trim()).filter(Boolean);
  const allowed=new Set([
    'https://nckhtop1.github.io',
    'https://vmews-risk-analytics-sojd.vercel.app',
    ...configured,
  ]);
  return allowed.has(origin)?origin:'https://nckhtop1.github.io';
}

function reply(response,status,body,origin){
  response.setHeader('Access-Control-Allow-Origin',origin);
  response.setHeader('Vary','Origin');
  response.setHeader('Access-Control-Allow-Methods','POST,OPTIONS');
  response.setHeader('Access-Control-Allow-Headers','Content-Type');
  response.setHeader('Cache-Control','no-store');
  return response.status(status).json(body);
}

export default async function handler(request,response){
  const origin=allowOrigin(request);
  if(request.method==='OPTIONS')return reply(response,204,{},origin);
  if(request.method!=='POST')return reply(response,405,{ok:false,error:'METHOD_NOT_ALLOWED'},origin);

  const credential=String(request.body?.credential||'').trim();
  const requestedClientId=String(request.body?.clientId||'').trim();
  const expectedClientId=String(process.env.FINQUERY_GOOGLE_CLIENT_ID||requestedClientId).trim();

  if(!credential||credential.length>MAX_CREDENTIAL_LENGTH||!expectedClientId){
    return reply(response,400,{ok:false,error:'INVALID_REQUEST'},origin);
  }

  try{
    const upstream=await fetch(
      'https://oauth2.googleapis.com/tokeninfo?id_token='+encodeURIComponent(credential),
      {headers:{Accept:'application/json'},signal:AbortSignal.timeout(8000)}
    );
    const token=await upstream.json().catch(()=>({}));
    if(!upstream.ok)return reply(response,401,{ok:false,error:'GOOGLE_TOKEN_INVALID'},origin);

    const now=Math.floor(Date.now()/1000);
    if(String(token.aud||'')!==expectedClientId)return reply(response,401,{ok:false,error:'AUDIENCE_MISMATCH'},origin);
    if(Number(token.exp||0)<=now)return reply(response,401,{ok:false,error:'TOKEN_EXPIRED'},origin);
    if(String(token.email_verified||'').toLowerCase()!=='true')return reply(response,401,{ok:false,error:'EMAIL_NOT_VERIFIED'},origin);
    if(!token.sub)return reply(response,401,{ok:false,error:'SUBJECT_MISSING'},origin);

    return reply(response,200,{
      ok:true,
      profile:{
        sub:String(token.sub),
        name:String(token.name||token.email||'').trim(),
        givenName:String(token.given_name||'').trim(),
        email:String(token.email||'').trim(),
        picture:String(token.picture||'').trim(),
      }
    },origin);
  }catch(_){
    return reply(response,503,{ok:false,error:'GOOGLE_VERIFY_UNAVAILABLE'},origin);
  }
}
