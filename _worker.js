import{connect}from'cloudflare:sockets'
const C={sub:'123123',uuid:'26687cd8-fcb8-4189-974c-7513f08fe875',fallback:'sjc.o00o.ooo',hdrs:{'cache-control':'public,max-age=14400','content-type':'text/plain'}},
uuidBytes=new Uint8Array(16),decoder=new TextDecoder(),bufferPool=[],urlCache=Object.create(null)
for(let i=0,hex=C.uuid.replace(/-/g,'');i<32;i+=2)uuidBytes[i>>1]=parseInt(hex.substr(i,2),16)
let ERR4,ERR5,redirect,nodeList=['www.visa.cn:443'],stmt,cacheSize=0
const acquireBuffer=len=>{const buf=bufferPool.pop();return buf?.length>=len?buf:new Uint8Array(len)},
releaseBuffer=buf=>{if(bufferPool.length<8)bufferPool.push(buf)},
validateProtocol=buf=>{for(let i=16;i--;)if(buf[i+1]!==uuidBytes[i])return false;return true},
parseTarget=(buf,offset)=>{
const port=buf[offset]<<8|buf[offset+1],type=buf[offset+2],start=offset+3
if(type&1)return{host:`${buf[start]}.${buf[start+1]}.${buf[start+2]}.${buf[start+3]}`,port,end:start+4}
if(type&4){let addr='[';for(let i=0;i<8;i++)addr+=(i?':':'')+((buf[start+i*2]<<8)|buf[start+i*2+1]).toString(16);return{host:addr+']',port,end:start+16}}
const len=buf[start];return{host:decoder.decode(buf.subarray(start+1,start+1+len)),port,end:start+1+len}
},
buildVless=(ip,name,host)=>{
const sepIdx=ip.indexOf('#'),endpoint=sepIdx>-1?ip.substring(0,sepIdx):ip,tag=sepIdx>-1?ip.substring(sepIdx+1):name||''
let displayIp,port='443'
if(endpoint[0]==='['){const bracket=endpoint.indexOf(']');displayIp=endpoint.substring(0,bracket+1);const match=endpoint.substring(bracket+1).match(/^:(\d+)/);if(match)port=match[1]}
else{const colon=endpoint.indexOf(':');displayIp=colon>-1?endpoint.substring(0,colon):endpoint;if(colon>-1)port=endpoint.substring(colon+1)}
return`vless://${C.uuid}@${displayIp}:${port}?encryption=none&security=tls&type=ws&host=${host}&path=%2F%3Fed%3D2560&sni=${host}#${encodeURIComponent(tag||displayIp.replace(/\./g,'-')+'-'+port)}`
},
createQueue=()=>{let queue=Promise.resolve();return fn=>queue=queue.then(fn).catch(()=>{})}
export default{
async fetch(req,env,ctx){
if(!ERR4){ERR4=new Response(null,{status:400});ERR5=new Response(null,{status:502});redirect=Response.redirect('https://github.com/Meibidi/kuangbao',302)}
let url=urlCache[req.url];if(!url){if(cacheSize>=64){for(const k in urlCache){delete urlCache[k];cacheSize--;break}}url=new URL(req.url);urlCache[req.url]=url;cacheSize++}
const{host,pathname}=url
if(req.headers.get('upgrade')==='websocket'){
const proto=req.headers.get('sec-websocket-protocol');if(!proto)return ERR4
const bin=atob(proto.replace(/[-_]/g,c=>c<'.'?'+':'/')),len=bin.length,buf=acquireBuffer(len)
for(let i=0;i<len;i++)buf[i]=bin.charCodeAt(i)
if(len<18||!validateProtocol(buf)){releaseBuffer(buf);return ERR4}
const{host:targetHost,port:targetPort,end}=parseTarget(buf,19+buf[17])
let socket;try{socket=connect({hostname:targetHost,port:targetPort});await socket.opened}catch{try{socket=connect({hostname:C.fallback,port:443});await socket.opened}catch{releaseBuffer(buf);return ERR5}}
const[client,server]=Object.values(new WebSocketPair());server.accept();server.send(new Uint8Array(2))
const writeQueue=createQueue()
if(len>end){const payload=buf.subarray(end,len);writeQueue(async()=>{const w=socket.writable.getWriter();await w.write(payload);w.releaseLock()})}
releaseBuffer(buf)
server.addEventListener('message',e=>writeQueue(async()=>{const w=socket.writable.getWriter();await w.write(e.data);w.releaseLock()}))
socket.readable.pipeTo(new WritableStream({write(chunk){server.send(chunk)}})).catch(()=>{})
return new Response(null,{status:101,webSocket:client})
}
if(pathname===`/${C.sub}/vless`){
try{stmt??=env.DB.prepare('SELECT ip,name FROM ips WHERE active=1 ORDER BY id ASC');const{results}=await stmt.all();if(results[0])nodeList=results.map(r=>r.ip+(r.name?'#'+r.name:''))}catch{}
return new Response(nodeList.map(ip=>buildVless(ip,'',host)).join('\n'),{headers:C.hdrs})
}
return pathname===`/${C.sub}`?new Response(`订阅: https://${host}/${C.sub}/vless`,{headers:C.hdrs}):redirect
}}
