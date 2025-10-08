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
    ProxyIP: getEnv('PROXY_IP', 'sjc.o00o.ooo:443', env),
    ReverseProxyEnabled: getEnv('REVERSE_PROXY', true, env),
    NAT64: getEnv('NAT64', false, env),
    NodeName: getEnv('NODE_NAME', 'Fury', env),
    done: true,
  };
  return config;
};

const tryConnection = async (host, port, cfg) => {
  try {
    const socket = await connect({ hostname: host, port });
    await socket.opened;
    return socket;
  } catch {
    if (cfg.NAT64 && /^\d+\.\d+\.\d+\.\d+$/.test(host)) {
      const ipv6 = `2001:67c:2960:6464::${host
        .split('.')
        .map(x => (+x).toString(16).padStart(2, '0'))
        .join('')}`;
      return await tryConnection(ipv6, port, { ...cfg, NAT64: false });
    }
    if (cfg.ReverseProxyEnabled && cfg.ProxyIP) {
      const [proxyHost, proxyPort] = cfg.ProxyIP.split(':');
      return await tryConnection(proxyHost, Number(proxyPort || port), { ...cfg, ReverseProxyEnabled: false });
    }
    throw new Error('Connection failed');
  }
};

const generateConfig = (host, cfg) =>
  cfg.IP.concat([`${host}:443`])
    .map(entry => {
      const [raw, name = cfg.NodeName] = entry.split('#');
      const [addr, port = 443] = raw.split(':');
      return `vless://${cfg.UUID}@${addr}:${port}?encryption=none&security=tls&type=ws&host=${host}&sni=${host}&path=%2F%3Fed%3D2560#${name}`;
    })
    .join('\n');

const base64ToBytes = s =>
  Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));

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
      return new Response('Hello Worker!', { status: 200 });
    }

    try {
      if (!proto || !proto.includes(cfg.UUID))
        return new Response('Invalid UUID', { status: 403 });

      const tcpSocket = await tryConnection(host, 443, cfg);
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
