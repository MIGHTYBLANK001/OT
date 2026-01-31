#!/usr/bin/env python3
import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

# --- 环境配置 ---
BASE_DIR = Path("/tmp/.agsb_base_test").resolve()
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
    
    sb_bin = BASE_DIR / "sing-box"
    cf_bin = BASE_DIR / "cloudflared"

    if not sb_bin.exists():
        log("正在获取 Sing-box 内核...")
        url = f"https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz"
        urllib.request.urlretrieve(url, "sb.tar.gz")
        with tarfile.open("sb.tar.gz") as tar:
            for m in tar.getmembers():
                if m.name.endswith("sing-box"):
                    m.name = os.path.basename(m.name); tar.extract(m, path=BASE_DIR)
        sb_bin.chmod(0o755)

    if not cf_bin.exists():
        log("正在获取 Cloudflared...")
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
        urllib.request.urlretrieve(url, cf_bin)
        cf_bin.chmod(0o755)
    return sb_bin, cf_bin

def run():
    sb, cf = setup()
    
    # --- 极致简化的基础配置：无 WARP，全直连 ---
    cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess", 
            "listen": "0.0.0.0", 
            "listen_port": PORT,
            "users": [{"uuid": UID}],
            "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}
        }],
        "outbounds": [
            {"type": "direct", "tag": "direct"}
        ],
        "route": {
            "final": "direct"
        }
    }
    with open("sb.json", "w") as f: json.dump(cfg, f)

    # 构造节点链接
    vm = {
        "v": "2", "ps": "BASE-TEST-NODE", "add": DOMAIN, "port": "443", "id": UID,
        "net": "ws", "host": DOMAIN, "path": f"/{UID[:8]}-vm", "tls": "tls", "sni": DOMAIN
    }
    link = "vmess://" + base64.b64encode(json.dumps(vm).encode()).decode()
    
    print("\n" + "⚠️" * 15, flush=True)
    print("【 基础模式启动：已移除 WARP 功能 】", flush=True)
    print(f"测试节点: {link}", flush=True)
    print("⚠️" * 15 + "\n", flush=True)

    # 启动进程
    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    
    # 启动 sing-box
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # 启动 cloudflared
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    log("服务已就绪。如果此节点依然 -1，请检查 Cloudflare Tunnel 的域名解析是否指向了正确的隧道。")
    while True: time.sleep(60)

if __name__ == "__main__":
    run()
