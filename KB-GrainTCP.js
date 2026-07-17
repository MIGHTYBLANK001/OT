import { connect as _c } from 'cloudflare:sockets';

const _C = {
  id: '55d9ec38-1b8a-454b-981a-6acfe8f56d8c',
  ph: 'sjc.o00o.ooo',
  pp: 443,
  cs: 65536,
  dp: 32768,
  dt: 512,
  dq: 4,
  up: 20480,
  cc: 1
};

const _TD = new TextDecoder();
const _E = new Uint8Array(0);
const _IB = new Uint8Array(16);
const _HV = c => (c > 64 ? c + 9 : c) & 0xF;

for (let i = 0, p = 0; i < 16; i++) {
  let c = _C.id.charCodeAt(p++);
  if (c === 45) c = _C.id.charCodeAt(p++);
  const h = _HV(c);
  c = _C.id.charCodeAt(p++);
  if (c === 45) c = _C.id.charCodeAt(p++);
  _IB[i] = (h << 4) | _HV(c);
}

function _chk(d, o) {
  for (let i = 0; i < 16; i++) {
    if (d[o + i] !== _IB[i]) return false;
  }
  return true;
}

function _parse(d) {
  const len = d.length;
  if (len < 22 || d[0] !== 0 || !_chk(d, 1)) return null;
  const al = d[17];
  const co = 18 + al;
  if (co + 3 > len || d[co] !== 1) return null;
  const port = (d[co + 1] << 8) | d[co + 2];
  const ao = co + 3;
  if (ao >= len) return null;
  const t = d[ao];
  let host = '';
  let end = 0;
  if (t === 1) {
    end = ao + 5;
    if (end > len) return null;
    host = `${d[ao + 1]}.${d[ao + 2]}.${d[ao + 3]}.${d[ao + 4]}`;
  } else if (t === 2) {
    if (ao + 2 > len) return null;
    const dl = d[ao + 1];
    end = ao + 2 + dl;
    if (end > len) return null;
    host = _TD.decode(d.subarray(ao + 2, end));
  } else if (t === 3) {
    end = ao + 17;
    if (end > len) return null;
    const v = new DataView(d.buffer, d.byteOffset + ao + 1, 16);
    host = Array.from({ length: 8 }, (_, i) => v.getUint16(i * 2).toString(16)).join(':');
  } else {
    return null;
  }
  return { h: host, p: port, o: end };
}

function _b64(s) {
  try {
    return Uint8Array.fromBase64(s, { alphabet: 'base64url' });
  } catch {
    return _E;
  }
}

async function _dial(h, p, f = false) {
  const th = f ? _C.ph : h;
  const tp = f ? _C.pp : p;
  const s = _c({ hostname: th, port: tp }, { allowHalfOpen: false });
  await s.opened;
  return s;
}

async function _conn(h, p) {
  if (_C.cc <= 1) return await _dial(h, p);
  const ts = Array.from({ length: _C.cc }, () => _dial(h, p));
  const w = await Promise.any(ts);
  ts.forEach(t => t.then(s => s !== w && s.close(), () => {}));
  return w;
}

function _mkQ(cap, cpy = false) {
  let q = [], head = 0, byteLen = 0, buf = null;
  const trim = () => {
    if (head > 32 && head * 2 >= q.length) {
      q = q.slice(head);
      head = 0;
    }
  };
  const take = () => {
    if (head >= q.length) return null;
    const d = q[head];
    q[head++] = undefined;
    byteLen -= d.byteLength;
    trim();
    return d;
  };
  return {
    get len() { return byteLen; },
    get empty() { return head >= q.length; },
    clear() { q = []; head = 0; byteLen = 0; },
    sow(d) {
      const l = d?.byteLength || 0;
      if (!l) return false;
      q.push(d);
      byteLen += l;
      return true;
    },
    pack(d) {
      d ||= take();
      if (!d || head >= q.length) return [d, 0];
      let tl = d.byteLength, j = head;
      while (j < q.length) {
        const nl = tl + q[j].byteLength;
        if (nl > cap) break;
        tl = nl;
        j++;
      }
      if (j === head) return [d, 0];
      const out = buf ||= new Uint8Array(cap);
      out.set(d);
      for (let o = d.byteLength; head < j;) {
        const n = q[head];
        q[head++] = undefined;
        byteLen -= n.byteLength;
        out.set(n, o);
        o += n.byteLength;
      }
      trim();
      const s = out.subarray(0, tl);
      return [cpy ? s.slice() : s, 1];
    }
  };
}

function _pipeDn(rd, ws) {
  const cap = _C.dp;
  const tail = _C.dt;
  const low = Math.max(4096, tail * 12);
  const k = _mkQ(cap, true);
  let tm = 0, gen = 0, lg = 0, qr = 0;
  
  const flush = () => {
    if (tm) clearTimeout(tm);
    tm = 0; qr = 0;
    while (true) {
      const [u] = k.pack();
      if (!u) break;
      ws.send(u);
    }
  };
  
  const trigger = () => {
    if (k.empty || tm) return;
    if (k.len >= cap || cap - k.len < tail) return flush();
    tm = setTimeout(() => {
      tm = 0;
      if (k.empty) return;
      if (k.len >= cap || cap - k.len < tail) return flush();
      if (qr < _C.dq && (gen !== lg || k.len < low)) {
        qr++;
        lg = gen;
        return trigger();
      }
      flush();
    }, 1);
  };
  
  const tx = {
    send(chunk) {
      let o = 0;
      const l = chunk?.byteLength || 0;
      if (!l) return;
      while (o < l) {
        const s = Math.min(cap - k.len, l - o);
        if (!s) { flush(); continue; }
        k.sow(o || s !== l ? chunk.subarray(o, o + s) : chunk);
        gen++;
        o += s;
        if (k.len >= cap || cap - k.len < tail) flush();
        else trigger();
      }
    },
    flush
  };
  
  const r = rd.getReader({ mode: 'byob' });
  let b = new ArrayBuffer(_C.cs);
  
  (async () => {
    try {
      while (true) {
        const { done, value } = await r.read(new Uint8Array(b, 0, _C.cs));
        if (done) break;
        if (!value?.byteLength) continue;
        if (value.byteLength >= (_C.cs >> 1)) {
          tx.flush();
          ws.send(value);
          b = new ArrayBuffer(_C.cs);
        } else {
          tx.send(value.slice());
          b = value.buffer;
        }
      }
    } catch {} finally {
      try { tx.flush(); } catch {}
      try { r.releaseLock(); } catch {}
    }
  })();
}

async function _pipeUp(ws, tcp, init) {
  const uq = _mkQ(_C.up);
  let cw = null, closed = false, busy = false;
  
  const close = () => {
    if (closed) return;
    closed = true;
    uq.clear();
    try { cw?.releaseLock(); } catch {}
    try { tcp.close(); } catch {}
    try { ws.close(); } catch {}
  };
  
  const toU8 = d => d instanceof Uint8Array ? d : (ArrayBuffer.isView(d) ? new Uint8Array(d.buffer, d.byteOffset, d.byteLength) : new Uint8Array(d));
  
  const push = d => {
    const u = toU8(d);
    if (!u.byteLength) return true;
    if (uq.sow(u)) return true;
    close();
    return false;
  };
  
  const drain = async () => {
    if (busy || closed) return;
    busy = true;
    try {
      while (!closed) {
        if (!cw) {
          const [d] = uq.pack();
          if (!d) break;
          const vl = _parse(d);
          if (!vl) throw close();
          ws.send(new Uint8Array([d[0], 0]));
          const pay = d.subarray(vl.o);
          cw = tcp.writable.getWriter();
          const [f] = uq.pack(pay);
          if (f?.byteLength) await cw.write(f);
          _pipeDn(tcp.readable, ws);
          continue;
        }
        const [d] = uq.pack();
        if (!d) break;
        await cw.ready;
        await cw.write(d);
      }
    } catch {
      close();
    } finally {
      busy = false;
      if (!uq.empty && !closed) drain();
    }
  };
  
  if (init && push(init)) drain();
  
  ws.addEventListener('message', e => {
    if (!closed && push(e.data)) drain();
  });
  ws.addEventListener('close', close);
  ws.addEventListener('error', close);
}

export default {
  async fetch(req) {
    if (req.headers.get('Upgrade')?.toLowerCase() !== 'websocket') {
      return new Response('426', { status: 426, headers: { Upgrade: 'websocket' } });
    }
    const pr = req.headers.get('Sec-WebSocket-Protocol');
    if (!pr) return new Response('400', { status: 400 });
    const init = _b64(pr);
    if (init === _E) return new Response('400', { status: 400 });
    const vl = _parse(init);
    if (!vl) return new Response('403', { status: 403 });
    let tcp;
    try {
      tcp = await _conn(vl.h, vl.p);
    } catch {
      try {
        tcp = await _conn(vl.h, vl.p, true);
      } catch {
        return new Response('502', { status: 502 });
      }
    }
    const [c, s] = Object.values(new WebSocketPair());
    s.accept();
    s.binaryType = 'arraybuffer';
    _pipeUp(s, tcp, init);
    return new Response(null, {
      status: 101,
      webSocket: c,
      headers: { 'Sec-WebSocket-Extensions': '' }
    });
  }
};
