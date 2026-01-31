#!/usr/bin/env python3
import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

# --- 环境适配 ---
BASE_DIR = Path("/tmp/.agsb_mihomo_final").resolve()
UID = st.secrets.get("UUID", "ee1f6ad8-dca8-47d9-8d17-1a2983551702")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "pynode.lun.xx.kg")
PORT = 49999

def log(msg):
    print(f"[*] {msg}", flush=True)

def setup():
    if not BASE_DIR.exists(): BASE_DIR.mkdir(parents=True)
    os.chdir(BASE_DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    sb_bin, cf_bin = BASE_DIR / "sing-box", BASE_DIR / "cloudflared"

    if not sb_bin.exists():
        log("下载 sing-box...")
        url = f"https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz"
        urllib.request.urlretrieve(url, "sb.tar.gz")
        with tarfile.open("sb.tar.gz") as tar:
            for m in tar.getmembers():
                if m.name.endswith("sing-box"):
                    m.name = os.path.basename(m.name); tar.extract(m, path=BASE_DIR)
        sb_bin.chmod(0o755)

    if not cf_bin.exists():
        log("下载 cloudflared...")
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
        urllib.request.urlretrieve(url, cf_bin)
        cf_bin.chmod(0o755)
    return sb_bin, cf_bin

def run():
    sb, cf = setup()
    
    # 生成 WARP 密钥
    try:
        out = subprocess.check_output([str(sb), "generate", "wg-keypair"]).decode().split()
        priv_key = out[2]
    except: priv_key = "GE6Ek7S...="

    # --- 专为 Fake-IP 设计的强制路由 ---
    cfg = {
        "log": {"level": "error"},
        "dns": {
            "servers": [
                {"tag": "dns-warp", "address": "https://1.1.1.1/dns-query", "detour": "warp-out"},
                {"tag": "dns-direct", "address": "8.8.8.8", "detour": "direct-out"}
            ],
            "rules": [
                {"domain_suffix": ["cloudflare.com", "argotunnel.com"], "server": "dns-direct"}
            ],
            "final": "dns-warp",
            "strategy": "ipv4_only"
        },
        "inbounds": [{
            "type": "vmess",
            "listen": "0.0.0.0",
            "listen_port": PORT,
            "users": [{"uuid": UID}],
            "sniff": True,                         # 核心：开启嗅探还原 Fake-IP 真实域名
            "sniff_override_destination": True,    # 核心：强制重写目标地址为域名
            "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}
        }],
        "outbounds": [
            {
                "type": "wireguard",
                "tag": "warp-out",
                "server": "engage.cloudflareclient.com",
                "server_port": 2408,
                "local_address": ["172.16.0.2/32"],
                "private_key": priv_key,
                "mtu": 1280,
                "udp_fragment": True
            },
            {"type": "direct", "tag": "direct-out"}
        ],
        "route": {
            "rules": [
                # 1. 绝对优先：隧道控制流必须直连，否则延迟立即变 -1
                {"domain_suffix": ["cloudflare.com", "cloudflareclient.com", "argotunnel.com"], "outbound": "direct-out"},
                # 2. 排除内网
                {"ip_is_private": True, "outbound": "direct-out"},
                # 3. DNS 劫持走 WARP 内部解析
                {"protocol": "dns", "outbound": "warp-out"}
            ],
            "final": "warp-out" # 其余所有流量(IP或域名)全部走 WARP
        }
    }
    
    with open("sb.json", "w") as f: json.dump(cfg, f)

    vm = {"v":"2","ps":"WARP-Global-FakeIP","add":DOMAIN,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm","tls":"tls","sni":DOMAIN}
    link = "vmess://" + base64.b64encode(json.dumps(vm).encode()).decode()
    
    print(f"\n✅ 适配完成！当前模式：全局 WARP 出口 (Fake-IP 优化版)\n节点链接: {link}\n", flush=True)

    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    while True: time.sleep(600) # 10分钟监测一次

if __name__ == "__main__":
    run()
