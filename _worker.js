import { connect } from 'cloudflare:sockets';

const C = {
  sub: '123123',
  uuid: '26687cd8-fcb8-4189-974c-7513f08fe875',
  fallback: 'sjc.o00o.ooo',
  hdrs: { 'cache-control': 'public,max-age=14400', 'content-type': 'text/plain' }
};

const uuidBytes = Uint8Array.from(C.uuid.replace(/-/g,''), (c,i,a)=>parseInt(a[i]+a[i+1],16));
const decoder = new TextDecoder();
let urlCache = {}, cacheSize = 0, nodeList = ['www.visa.cn:443'], stmt;

const validateProtocol = buf => buf.slice(1,17).every((v,i)=>v===uuidBytes[i]);

const parseTarget = (buf,o)=>{
  const port=(buf[o]<<8)|buf[o+1],t=buf[o+2],s=o+3;
  if(t&1)return {host:`${buf[s]}.${buf[s+1]}.${buf[s+2]}.${buf[s+3]}`,port,end:s+4};
  if(t&4){let a='[';for(let i=0;i<8;i++)a+=(i?':':'')+((buf[s+i*2]<<8)|buf[s+i*2+1]).toString(16);return {host:a+']',port,end:s+16}}
  const l=buf[s];return {host:decoder.decode(buf.subarray(s+1,s+1+l)),port,end:s+1+l};
};

const buildVless=(ip,name,host)=>{
  const sep=ip.indexOf('#'),endp=sep>-1?ip.slice(0,sep):ip,tag=sep>-1?ip.slice(sep+1):name||'';
  let h,p='443';
  if(endp[0]==='['){const b=endp.indexOf(']');h=endp.slice(0,b+1);const m=endp.slice(b+1).match(/^:(\d+)/);if(m)p=m[1]}
  else{const c=endp.indexOf(':');h=c>-1?endp.slice(0,c):endp;if(c>-1)p=endp.slice(c+1)}
  return `vless://${C.uuid}@${h}:${p}?encryption=none&security=tls&type=ws&host=${host}&path=%2F%3Fed%3D2560&sni=${host}#${encodeURIComponent(tag||h.replace(/\./g,'-')+'-'+p)}`;
};

const createQueue=()=>{let q=Promise.resolve();return fn=>q=q.then(fn).catch(()=>{})};
const ERR4=new Response(null,{status:400}), ERR5=new Response(null,{status:502});
const redirect=Response.redirect('https://github.com/Meibidi/kuangbao',302);

export default {
  async fetch(req, env){
    let url=urlCache[req.url];
    if(!url){if(cacheSize>=64){urlCache={};cacheSize=0} url=new URL(req.url); urlCache[req.url]=url; cacheSize++}
    const {host,pathname}=url;

    if(req.headers.get('upgrade')==='websocket'){
      const proto=req.headers.get('sec-websocket-protocol'); if(!proto) return ERR4;
      const bin=atob(proto.replace(/[-_]/g,c=>c<'.'?'+':'/')); if(bin.length<18) return ERR4;

      const buf=Uint8Array.from(bin,c=>c.charCodeAt(0));
      if(!validateProtocol(buf)) return ERR4;

      const {host:th,tp:end} = parseTarget(buf,19+buf[17]);
      let socket;
      try { socket=connect({hostname:th,port:tp}); await socket.opened; } 
      catch{ try { socket=connect({hostname:C.fallback,port:443}); await socket.opened; } catch{return ERR5;} }

      const [client,server]=Object.values(new WebSocketPair()); server.accept(); server.send(new Uint8Array(2));
      const q=createQueue(); if(buf.length>end){const p=buf.subarray(end); q(async()=>{const w=socket.writable.getWriter();await w.write(p);w.releaseLock();})}

      server.addEventListener('message',e=>q(async()=>{const w=socket.writable.getWriter();await w.write(e.data); w.releaseLock()}));
      socket.readable.pipeTo(new WritableStream({write(c){server.send(c)}})).catch(()=>{});
      return new Response(null,{status:101,webSocket:client});
    }

    if(pathname===`/${C.sub}/vless`){
      try{
        stmt??=env.DB.prepare('SELECT ip,name FROM ips WHERE active=1 ORDER BY id ASC');
        const {results}=await stmt.all();
        if(results.length) nodeList=results.map(r=>r.ip+(r.name?'#'+r.name:''));
      } catch{}
      return new Response(nodeList.map(ip=>buildVless(ip,'',host)).join('\n'),{headers:C.hdrs});
    }

    if(pathname===`/${C.sub}`) return new Response(`sub: https://${host}/${C.sub}`,{headers:C.hdrs});

    return redirect;
  }
};
