#!/usr/bin/env python3
import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

# --- 从 Secrets 读取变量 ---
BASE_DIR = Path("/tmp/.agsb_warp_final").resolve()
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
    try:
        out = subprocess.check_output([str(sb), "generate", "wg-keypair"]).decode().split()
        priv_key = out[2]
    except: priv_key = "GE6Ek7S...="

    # --- 增强型强制 WARP 配置 ---
    cfg = {
        "log": {"level": "error"},
        "dns": {
            "servers": [{"tag": "google", "address": "8.8.8.8", "detour": "warp-out"}]
        },
        "inbounds": [{
            "type": "vmess", "listen": "0.0.0.0", "listen_port": PORT,
            "users": [{"uuid": UID}],
            "sniff": True,  # 开启流量嗅探，强制识别域名进行路由
            "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}
        }],
        "outbounds": [
            {
                "type": "wireguard", "tag": "warp-out",
                "server": "engage.cloudflareclient.com", "server_port": 2408,
                "local_address": ["172.16.0.2/32", "2606:4700:110:8285:343b:d165:10a4:6443/128"],
                "private_key": priv_key, "mtu": 1280
            },
            {"type": "direct", "tag": "direct-out"}
        ],
        "route": {
            "rules": [
                # 必须直连以维持隧道心跳
                {"domain_suffix": ["cloudflare.com", "cloudflareclient.com", "argotunnel.com"], "outbound": "direct-out"},
                {"ip_is_private": True, "outbound": "direct-out"},
                {"protocol": "dns", "outbound": "direct-out"}
            ],
            "final": "warp-out",
            "auto_detect_interface": True
        }
    }
    with open("sb.json", "w") as f: json.dump(cfg, f)

    vm = {"v":"2","ps":"WARP-Global-Strong","add":DOMAIN,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm","tls":"tls","sni":DOMAIN}
    link = "vmess://" + base64.b64encode(json.dumps(vm).encode()).decode()
    
    print("\n" + "🛡️" * 15, flush=True)
    print("【 部署成功：全局 WARP 模式已强化 】", flush=True)
    print(f"节点链接: {link}", flush=True)
    print("🛡️" * 15 + "\n", flush=True)

    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    log("服务运行中，监测周期已改为 10 分钟。")
    # --- 修改监测为 10 分钟 ---
    while True:
        time.sleep(600) # 600秒 = 10分钟

if __name__ == "__main__":
    run()
