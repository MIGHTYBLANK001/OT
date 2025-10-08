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
    UUID: getEnv('UUID', '26687cd8-fcb8-4189-974c-7513f08fe875', env),
    ProxyIP: getEnv('PROXYIP', 'sjc.o00o.ooo:443', env),
    NAT64: getEnv('NAT64', true, env),
    NodeName: getEnv('NODE_NAME', 'Fury', env),
    done: true,
  };
  return config;
};

// Convert IPv4 to IPv6 (NAT64)
const toNAT64 = (ipv4) => `2001:67c:2960:6464::${ipv4.split('.').map(x => (+x).toString(16).padStart(2, '0')).join('')}`;

// Check if host is related to Cloudflare
const isCloudflareDomain = (hostname) => hostname.includes('cloudflare.com') || hostname.endsWith('.cf') || hostname.endsWith('.workers.dev');

// Try connection logic: direct → NAT64 → ProxyIP
const tryConnection = async (host, port, cfg) => {
  // 1️⃣ Try direct connection (default fast path)
  try {
    const socket = await connect({ hostname: host, port });
    await socket.opened;
    return socket;
  } catch {}

  // 2️⃣ If Cloudflare-related domain, fallback to NAT64 or ProxyIP
  if (isCloudflareDomain(host)) {
    // If host is IPv4 and NAT64 is enabled, try NAT64 translation
    if (cfg.NAT64 && /^\d+\.\d+\.\d+\.\d+$/.test(host)) {
      const ipv6 = toNAT64(host);
      try {
        const socket = await connect({ hostname: ipv6, port });
        await socket.opened;
        return socket;
      } catch {}
    }

    // 3️⃣ Fallback to ProxyIP
    if (cfg.ProxyIP) {
      const [proxyHost, proxyPort] = cfg.ProxyIP.split(':');
      try {
        const socket = await connect({ hostname: proxyHost, port: Number(proxyPort || port) });
        await socket.opened;
        return socket;
      } catch {}
    }
  }

  // 4️⃣ If not a Cloudflare domain, fail fast and use direct connection (no ProxyIP)
  throw new Error('Connection failed: Non-Cloudflare domain');
};

const generateConfig = (host, cfg) =>
  cfg.ProxyIP ? `vless://${cfg.UUID}@${host}:443?encryption=none&security=tls&type=ws&host=${host}&sni=${host}&path=%2F%3Fed%3D2560#${cfg.NodeName}` : '';

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const host = req.headers.get('Host');
    const upgrade = req.headers.get('Upgrade');
    const proto = req.headers.get('sec-websocket-protocol');
    const cfg = initConfig(env);

    // WebSocket request handling
    if (upgrade === 'websocket') {
      try {
        const decoded = atob(proto);
        const id = new TextDecoder().decode(decoded);
        if (!id.includes(cfg.UUID)) return new Response('Invalid UUID', { status: 403 });

        const tcpSocket = await tryConnection(host, 443, cfg);
        const [client, server] = new WebSocketPair();
        server.accept();
        
        tcpSocket.readable.pipeTo(new WritableStream({
          write: data => client.send(data),
          close: () => client.close(),
          abort: () => client.close(),
        }));

        return new Response(null, { status: 101, webSocket: client });
      } catch (e) {
        return new Response(`Connection failed: ${e.message}`, { status: 502 });
      }
    }

    // Non-WebSocket requests (e.g., subscription URL)
    if (url.pathname === `/${cfg.UUID}`)
      return new Response(`Subscription URL: https://${host}/${cfg.UUID}/vless`, { status: 200 });

    if (url.pathname === `/${cfg.UUID}/vless`)
      return new Response(generateConfig(host, cfg), { status: 200 });

    return new Response('Hello Worker (Optimized Dual-mode NAT64 + ProxyIP)', { status: 200 });
  },
};
