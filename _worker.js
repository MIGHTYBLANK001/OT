import { connect } from 'cloudflare:sockets';

const C = {
  sub: '123123',
  uuid: '26687cd8-fcb8-4189-974c-7513f08fe875',
  fallback: 'sjc.o00o.ooo',
  hdrs: { 'cache-control': 'public,max-age=14400', 'content-type': 'text/plain' }
};

const U = Uint8Array.from(C.uuid.replace(/-/g, ''), (c, i, a) => parseInt(a[i] + a[i + 1], 16));
const D = new TextDecoder();
let cache = {}, cacheSize = 0, nodeList = ['www.visa.cn:443'], stmt;

const validateProtocol = buf => buf.slice(1, 17).every((x, i) => x === U[i]);
const parseTarget = (buf, offset) => {
  const port = (buf[offset] << 8) | buf[offset + 1], type = buf[offset + 2], start = offset + 3;
  if (type & 1) return { host: `${buf[start]}.${buf[start + 1]}.${buf[start + 2]}.${buf[start + 3]}`, port, end: start + 4 };
  if (type & 4) {
    let addr = '[';
    for (let i = 0; i < 8; i++) addr += (i ? ':' : '') + ((buf[start + i * 2] << 8) | buf[start + i * 2 + 1]).toString(16);
    return { host: addr + ']', port, end: start + 16 };
  }
  const len = buf[start];
  return { host: D.decode(buf.subarray(start + 1, start + 1 + len)), port, end: start + 1 + len };
};

const buildVless = (ip, name, host) => {
  const sep = ip.indexOf('#'), endpoint = sep > -1 ? ip.slice(0, sep) : ip, tag = sep > -1 ? ip.slice(sep + 1) : name || '';
  let displayIp, port = '443';
  if (endpoint[0] === '[') {
    const bracket = endpoint.indexOf(']');
    displayIp = endpoint.slice(0, bracket + 1);
    const match = endpoint.slice(bracket + 1).match(/^:(\d+)/);
    if (match) port = match[1];
  } else {
    const colon = endpoint.indexOf(':');
    displayIp = colon > -1 ? endpoint.slice(0, colon) : endpoint;
    if (colon > -1) port = endpoint.slice(colon + 1);
  }
  return `vless://${C.uuid}@${displayIp}:${port}?encryption=none&security=tls&type=ws&host=${host}&path=%2F%3Fed%3D2560&sni=${host}#${encodeURIComponent(tag || displayIp.replace(/\./g, '-') + '-' + port)}`;
};

const createQueue = () => { let q = Promise.resolve(); return fn => q = q.then(fn).catch(() => {}); };
const ERR4 = new Response(null, { status: 400 }), ERR5 = new Response(null, { status: 502 });
const redirect = Response.redirect('https://github.com', 302);

export default {
  async fetch(req, env) {
    let url = cache[req.url];
    if (!url) {
      if (cacheSize >= 64) { cache = {}; cacheSize = 0; }
      url = new URL(req.url); cache[req.url] = url; cacheSize++;
    }

    const { host, pathname } = url;

    if (req.headers.get('upgrade') === 'websocket') {
      const proto = req.headers.get('sec-websocket-protocol');
      if (!proto) return ERR4;

      const bin = atob(proto.replace(/[-_]/g, c => c < '.' ? '+' : '/'));
      if (bin.length < 18) return ERR4;

      const buf = Uint8Array.from(bin, c => c.charCodeAt(0));
      if (!validateProtocol(buf)) return ERR4;

      const { host: targetHost, port: targetPort, end } = parseTarget(buf, 19 + buf[17]);
      let socket;
      try { socket = connect({ hostname: targetHost, port: targetPort }); await socket.opened; }
      catch { try { socket = connect({ hostname: C.fallback, port: 443 }); await socket.opened; } catch { return ERR5; } }

      const [client, server] = Object.values(new WebSocketPair()) || [];
      if (!client || !server) return ERR5;

      server.accept(); server.send(new Uint8Array(2));
      const queue = createQueue();
      if (buf.length > end) {
        const payload = buf.subarray(end);
        queue(async () => {
          const writer = socket.writable.getWriter();
          await writer.write(payload);
          writer.releaseLock();
        });
      }

      server.addEventListener('message', e => queue(async () => {
        const writer = socket.writable.getWriter();
        await writer.write(e.data);
        writer.releaseLock();
      }));
      socket.readable.pipeTo(new WritableStream({ write(chunk) { server.send(chunk); } })).catch(() => {});
      return new Response(null, { status: 101, webSocket: client });
    }

    if (pathname === `/${C.sub}` || pathname === `/${C.sub}/vless`) {
      try {
        stmt ??= env.DB.prepare('SELECT ip,name FROM ips WHERE active=1 ORDER BY id ASC');
        const { results } = await stmt.all();
        if (results && results.length) nodeList = results.map(r => r.ip + (r.name ? '#' + r.name : ''));
      } catch {}
      return new Response(`sub: https://${host}/${C.sub}`, { headers: C.hdrs });
    }

    return redirect;
  }
};
