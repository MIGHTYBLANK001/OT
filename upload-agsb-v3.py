#!/usr/bin/env python3
import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

# --- 配置从 Secrets 获取 ---
BASE_DIR = Path("/tmp/.agsb_mihomo_v3").resolve()
UID = st.secrets.get("UUID", "ee1f6ad8-dca8-47d9-8d17-1a2983551702")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "pynode.lun.xx.kg")
PORT = 49999

def setup():
    if not BASE_DIR.exists(): BASE_DIR.mkdir(parents=True)
    os.chdir(BASE_DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    sb_bin, cf_bin = BASE_DIR / "sing-box", BASE_DIR / "cloudflared"
    # 下载略... (保持之前的下载逻辑)
    if not sb_bin.exists():
        url = f"https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz"
        urllib.request.urlretrieve(url, "sb.tar.gz")
        with tarfile.open("sb.tar.gz") as tar:
            for m in tar.getmembers():
                if m.name.endswith("sing-box"):
                    m.name = os.path.basename(m.name); tar.extract(m, path=BASE_DIR)
        sb_bin.chmod(0o755)
    if not cf_bin.exists():
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
        urllib.request.urlretrieve(url, cf_bin)
        cf_bin.chmod(0o755)
    return sb_bin, cf_bin

def run():
    sb, cf = setup()
    try:
        out = subprocess.check_output([str(sb), "generate", "wg-keypair"]).decode().split()
        priv_key = out[2]
    except: priv_key = "GE6Ek7S...="

    # --- 专为 HTTP 转发 + FakeIP 设计的配置 ---
    cfg = {
        "log": {"level": "error"},
        "dns": {
            "servers": [{"tag": "dns-warp", "address": "8.8.8.8", "detour": "warp-out"}],
            "final": "dns-warp"
        },
        "inbounds": [{
            "type": "vmess",
            "listen": "127.0.0.1", 
            "listen_port": PORT,
            "users": [{"uuid": UID}],
            "sniff": True,                         # 识别嗅探，解决 Fake-IP 
            "sniff_override_destination": True,
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
                "mtu": 1100, # 极低 MTU，穿透 HTTP 代理层
                "udp_fragment": True
            },
            {"type": "direct", "tag": "direct-out"}
        ],
        "route": {
            "rules": [
                # 排除所有内网和隧道控制流，防止死循环
                {"ip_is_private": True, "outbound": "direct-out"},
                {"domain_suffix": ["cloudflare.com", "argotunnel.com"], "outbound": "direct-out"},
                {"protocol": "dns", "outbound": "direct-out"}
            ],
            "final": "warp-out" # 强制客户端流量进 WARP
        }
    }
    
    with open("sb.json", "w") as f: json.dump(cfg, f)
    
    link = "vmess://" + base64.b64encode(json.dumps({
        "v":"2","ps":"WARP-Final-Fixed","add":DOMAIN,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm","tls":"tls","sni":DOMAIN
    }).encode()).decode()

    print(f"\n✅ 节点已生成（已适配 Fake-IP 与 HTTP 转发）\n{link}\n", flush=True)

    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    while True: time.sleep(600)

if __name__ == "__main__":
    run()
