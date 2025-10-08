import { connect } from 'cloudflare:sockets';

let config = {};

const getEnv = (key, defaultValue, env) => {
  const value = env[key] ?? defaultValue;
  if (typeof value !== 'string') return value;
  const trimmed = value.trim();
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;
  const num = Number(trimmed);
  return isNaN(num) ? trimmed : num;
};

const initConfig = (env) => {
  if (config.done) return config;
  config = {
    ID: getEnv('ID', '123321', env),
    UUID: getEnv('UUID', '26687cd8-fcb8-4189-974c-7513f08fe875', env),
    IP: getEnv('IP', ['1.1.1.1'], env),
    ProxyIP: getEnv('PROXYIP', 'sjc.o00o.ooo', env),
    NAT64: getEnv('NAT64', true, env),
    NodeName: getEnv('NODE_NAME', 'Fury', env),
    done: true,
  };
  return config;
};

const toNAT64 = (ipv4) =>
  `2001:67c:2960:6464::${ipv4
    .split('.')
    .map(x => (+x).toString(16).padStart(2, '0'))
    .join('')}`;

const tryConnection = async (host, port, cfg) => {
  // 1️⃣ Try direct connection
  try {
    const socket = await connect({ hostname: host, port });
    await socket.opened;
    return socket;
  } catch {}

  // 2️⃣ Try NAT64 if enabled
  if (cfg.NAT64 && /^\d+\.\d+\.\d+\.\d+$/.test(host)) {
    try {
      const ipv6 = toNAT64(host);
      const socket = await connect({ hostname: ipv6, port });
      await socket.opened;
      return socket;
    } catch {}
  }

  // 3️⃣ Fallback to ProxyIP
  if (cfg.ProxyIP) {
    const [proxyHost, proxyPort = port] = cfg.ProxyIP.split(':');
    const socket = await connect({ hostname: proxyHost, port: Number(proxyPort) });
    await socket.opened;
    return socket;
  }

  throw new Error('All connection attempts failed');
};

const generateConfig = (host, cfg) =>
  cfg.IP.concat([`${host}:443`])
    .map(entry => {
      const [raw, name = cfg.NodeName] = entry.split('#');
      const [addr, port = 443] = raw.split(':');
      return `vless://${cfg.UUID}@${addr}:${port}?encryption=none&security=tls&type=ws&host=${host}&sni=${host}&path=%2F%3Fed%3D2560#${name}`;
    })
    .join('\n');

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const host = req.headers.get('Host');
    const upgrade = req.headers.get('Upgrade');
    const proto = req.headers.get('sec-websocket-protocol');
    const cfg = initConfig(env);

    if (upgrade !== 'websocket') {
      if (url.pathname === `/${cfg.ID}`)
        return new Response(`Subscription URL: https://${host}/${cfg.ID}/vless`, { status: 200 });
      if (url.pathname === `/${cfg.ID}/vless`)
        return new Response(generateConfig(host, cfg), { status: 200 });
      return new Response('Hello Worker (Dual-mode NAT64 + ProxyIP)', { status: 200 });
    }

    try {
      const decoded = atob(proto);
      const id = new TextDecoder().decode(decoded);
      if (!id.includes(cfg.UUID))
        return new Response('Invalid UUID', { status: 403 });

      const tcpSocket = await tryConnection('1.1.1.1', 443, cfg);
      const [client, server] = new WebSocketPair();
      server.accept();

      tcpSocket.readable.pipeTo(
        new WritableStream({
          write: data => client.send(data),
          close: () => client.close(),
          abort: () => client.close(),
        })
      );

      return new Response(null, { status: 101, webSocket: client });
    } catch (e) {
      return new Response(`Connection failed: ${e.message}`, { status: 502 });
    }
  },
};
