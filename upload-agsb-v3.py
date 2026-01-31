#!/usr/bin/env python3
import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

# --- 配置 ---
BASE_DIR = Path("/tmp/.agsb_ultimate_fix").resolve()
UID = st.secrets.get("UUID", "ee1f6ad8-dca8-47d9-8d17-1a2983551702")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "pynode.lun.xx.kg")
PORT = 49999

def setup():
    if not BASE_DIR.exists(): BASE_DIR.mkdir(parents=True)
    os.chdir(BASE_DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    sb_bin, cf_bin = BASE_DIR / "sing-box", BASE_DIR / "cloudflared"
    
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

    # --- 极致防回环：手动分流配置 ---
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
            "sniff": True,
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
                "mtu": 1120,
                "udp_fragment": True,
                "system_interface": False  # 关键：不创建虚拟网卡，只作为代理出站
            },
            {"type": "direct", "tag": "direct-out"}
        ],
        "route": {
            "rules": [
                # 排除 Cloudflare 隧道和管理流量（绝对直连）
                {"domain_suffix": ["cloudflare.com", "argotunnel.com", "cloudflareclient.com"], "outbound": "direct-out"},
                {"ip_is_private": True, "outbound": "direct-out"},
                # 剩下的所有从 vmess 进来的请求，强制丢给 warp-out
                {"inbound": ["vmess-in"], "outbound": "warp-out"}
            ],
            "final": "direct-out" # 兜底策略改为直连（防止隧道程序本身卡死）
        }
    }
    # 给入站起个名字以便匹配
    cfg["inbounds"][0]["tag"] = "vmess-in"
    
    with open("sb.json", "w") as f: json.dump(cfg, f)
    
    link = "vmess://" + base64.b64encode(json.dumps({
        "v":"2","ps":"WARP-FINAL-V4","add":DOMAIN,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm","tls":"tls","sni":DOMAIN
    }).encode()).decode()

    print(f"\n🚀 已部署：逻辑分流模式（彻底解决 -1 延迟）\n{link}\n", flush=True)

    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    while True: time.sleep(600)

if __name__ == "__main__":
    run()
