import { connect as connectSocket } from 'cloudflare:sockets'

// === 基本常量 ===
const socketMap = new Map()

// 使用标准 UUID 格式
const UUID_STRING = '26687cd8-fcb8-4189-974c-7513f08fe875'
const UUID_BYTES = new Uint8Array(
  UUID_STRING.replace(/-/g, '').match(/.{2}/g).map(x => parseInt(x, 16))
)

const BUFFER_POOL = new Uint8Array(32768)
const TEMP_POOL = new Array(12)
const RESPONSES = [
  new Response(null, { status: 400 }),
  new Response(null, { status: 502 })
]

let bufferOffset = 0
let poolIndex = 0

// === 地址与端口解析 ===
const parseTarget = buffer => {
  const offset = 19 + buffer[17]
  const port = (buffer[offset] << 8) | buffer[offset + 1]
  const isIPv4 = buffer[offset + 2] & 1
  const base = offset + 3
  const host = isIPv4
    ? `${buffer[base]}.${buffer[base + 1]}.${buffer[base + 2]}.${buffer[base + 3]}`
    : new TextDecoder().decode(buffer.subarray(base + 1, base + 1 + buffer[base]))
  return [host, port, isIPv4 ? base + 4 : base + 1 + buffer[base], buffer[0]]
}

// === 打开远程 TCP 连接 ===
const openRemoteSocket = (host, port) => {
  try {
    const socket = connectSocket({ hostname: host, port })
    return socket.opened.then(() => socket, () => 0).catch(() => 0)
  } catch {
    return Promise.resolve(0)
  }
}

// === Worker 主逻辑 ===
export default {
  async fetch(request) {
    if (request.headers.get('upgrade') !== 'websocket') return RESPONSES[1]

    const protocolHeader = request.headers.get('sec-websocket-protocol')
    if (!protocolHeader) return RESPONSES[0]

    const decoded = atob(protocolHeader.replace(/[-_]/g, x => (x < '.' ? '+' : '/')))
    const length = decoded.length
    if (length < 18) return RESPONSES[0]

    // 使用预分配内存池
    const fits = bufferOffset + length < 32768
    const buffer = fits
      ? new Uint8Array(BUFFER_POOL.buffer, bufferOffset, (bufferOffset += length))
      : poolIndex
        ? TEMP_POOL[--poolIndex] || new Uint8Array(length)
        : new Uint8Array(length)

    const recycle = () => {
      if (fits) {
        if (bufferOffset > 24576) bufferOffset = 0
        else bufferOffset -= length
      } else if (poolIndex < 12 && !TEMP_POOL[poolIndex]) {
        TEMP_POOL[poolIndex++] = buffer
      }
    }

    // 将协议头解码填充入缓冲区
    for (let i = length; i--;) buffer[i] = decoded.charCodeAt(i)

    // 校验协议版本
    if (buffer[0]) {
      recycle()
      return RESPONSES[0]
    }

    // 校验 UUID 字节序列
    for (let i = 0; i < 16; i++) {
      if (buffer[i + 1] ^ UUID_BYTES[i]) {
        recycle()
        return RESPONSES[0]
      }
    }

    // 解析目标地址与端口
    const [targetHost, targetPort, dataOffset, versionFlag] = parseTarget(buffer)

    // 建立远程连接
    const remote =
      (await openRemoteSocket(targetHost, targetPort)) ||
      (await openRemoteSocket('proxy.xxxxxxxx.tk', 50001))
    if (!remote) {
      recycle()
      return RESPONSES[1]
    }

    // === WebSocket 双向绑定 ===
    const { 0: client, 1: ws } = new WebSocketPair()
    const writer = remote.writable.getWriter()
    const state = [1, 0]
    const header = new Uint8Array([versionFlag, 0])
    let pendingHeader = header

    ws.accept()
    socketMap.set(ws, state)
    if (length > dataOffset)
      writer.write(buffer.subarray(dataOffset)).catch(() => (state[0] = 0))
    recycle()

    // === 清理与关闭函数 ===
    const cleanup = () => {
      try { ws.close(state[1]) } catch {}
      try { remote.close() } catch {}
      socketMap.delete(ws)
      if (socketMap.size > 999) socketMap.clear()
    }

    const closeAll = () => {
      if (state[0]) {
        state[0] = 0
        writer.releaseLock()
        cleanup()
      }
    }

    // === 双向数据流 ===
    ws.addEventListener('message', e =>
      state[0] && writer.write(e.data).catch(() => (state[0] = 0))
    )
    ws.addEventListener('close', () => { state[1] = 1000; closeAll() })
    ws.addEventListener('error', () => { state[1] = 1006; closeAll() })

    remote.readable.pipeTo(new WritableStream({
      async write(chunk) {
        if (state[0]) {
          if (pendingHeader) {
            ws.send(await new Blob([pendingHeader, chunk]).arrayBuffer())
            pendingHeader = null
          } else ws.send(chunk)
        }
      },
      close() { state[1] = 1000; closeAll() },
      abort() { state[1] = 1006; closeAll() }
    })).catch(() => {})

    return new Response(null, { status: 101, webSocket: client })
  }
}const chk = b => U.every((x, i) => b[i] === x);

const to64 = ip => '2001:67c:2960:6464::' + ip.split('.').map(x => (+x).toString(16).padStart(2, '0')).join('').match(/.{4}/g).join(':');

const dns6 = async d => {
  const r = await fetch(`https://1.1.1.1/dns-query?name=${d}&type=A`, { headers: { Accept: 'application/dns-json' } });
  const j = await r.json(), ip = j.Answer?.find(x => x.type === 1)?.data;
  return ip ? to64(ip) : null;
};

const base64 = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0)).buffer;

const tryConn = async (h, p, cfg, init) => {
  try {
    const s = await connect({ hostname: h, port: p });
    await s.opened;
    return { tcpSocket: s, initialData: init };
  } catch {}

  if (cfg.N && /^\d+\.\d+\.\d+\.\d+$/.test(h)) {
    try {
      return await tryConn(to64(h), p, { ...cfg, N: 0 }, init);
    } catch {}
  }

  if (cfg.F && cfg.R) {
    const [h2, p2] = cfg.R.split(':');
    return await tryConn(h2, Number(p2 || p), { ...cfg, F: 0 }, init);
  }

  throw new Error('连接失败');
};

const parseVless = async (buf, cfg) => {
  const c = new Uint8Array(buf), t = c[17], p = (c[18 + t + 1] << 8) | c[18 + t + 2];
  let o = 18 + t + 4, h = '';
  switch (c[o - 1]) {
    case 1: h = `${c[o++]}.${c[o++]}.${c[o++]}.${c[o++]}`; break;
    case 2: { const l = c[o++]; h = d.decode(c.subarray(o, o + l)); o += l; break; }
    case 3: h = Array.from({ length: 8 }, (_, i) => ((c[o + 2*i] << 8) | c[o + 2*i + 1]).toString(16)).join(':'); o += 16; break;
  }
  return await tryConn(h, p, cfg, buf.slice(o));
};

const tunnel = (ws, tcp, init) => {
  const w = tcp.writable.getWriter();
  ws.send(new Uint8Array([0, 0]));
  if (init) w.write(init);
  let b = [], t;
  ws.addEventListener('message', ({ data }) => {
    const c = data instanceof ArrayBuffer ? new Uint8Array(data)
      : typeof data === 'string' ? e.encode(data)
      : data;
    b.push(c);
    if (!t) t = setTimeout(() => {
      w.write(b.length === 1 ? b[0] : b.reduce((a, b) => {
        const o = new Uint8Array(a.length + b.length);
        o.set(a); o.set(b, a.length); return o;
      }));
      b = []; t = null;
    }, 5);
  });

  tcp.readable.pipeTo(new WritableStream({
    write: c => ws.send(c),
    close: () => ws.close(),
    abort: () => ws.close()
  })).catch(() => ws.close());

  ws.addEventListener('close', () => {
    try { w.releaseLock(); tcp.close(); } catch {}
  });
};

const genConf = (h, cfg) =>
  cfg.P.concat([`${h}:443`]).map(x => {
    const [raw, name = cfg.N2] = x.split('#');
    const [addr, port = 443] = raw.split(':');
    return `vless://${cfg.U}@${addr}:${port}?encryption=none&security=tls&type=ws&host=${h}&sni=${h}&path=%2F%3Fed%3D2560#${name}`;
  }).join('\n');

export default {
  async fetch(req, env) {
    const cfg = init(env), url = new URL(req.url);
    const up = req.headers.get('Upgrade'), proto = req.headers.get('sec-websocket-protocol');
    const host = req.headers.get('Host');

    if (up !== 'websocket') {
      if (url.pathname === `/${cfg.I}`)
        return new Response(`订阅地址: https://${host}/${cfg.I}/vless`, { status: 200 });
      if (url.pathname === `/${cfg.I}/vless`)
        return new Response(genConf(host, cfg), { status: 200 });
      return new Response('Hello Worker!', { status: 200 });
    }

    try {
      const d = base64(proto), id = new Uint8Array(d, 1, 16);
      if (!chk(id)) return new Response('无效UUID', { status: 403 });

      const { tcpSocket, initialData } = await parseVless(d, cfg);
      const [client, server] = new WebSocketPair();
      server.accept(); tunnel(server, tcpSocket, initialData);
      return new Response(null, { status: 101, webSocket: client });

    } catch (e) {
      return new Response(`连接失败: ${e.message}`, { status: 502 });
    }
  }
};
