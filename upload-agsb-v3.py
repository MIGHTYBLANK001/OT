#!/usr/bin/env python3
import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

# --- 环境适配 ---
BASE_DIR = Path("/tmp/.agsb_global_warp").resolve()
UID = st.secrets.get("UUID", "")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "")
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
        log("下载 sing-box 内核...")
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
    
    # 自动生成本地 WARP 密钥（确保出口唯一性）
    try:
        out = subprocess.check_output([str(sb), "generate", "wg-keypair"]).decode().split()
        priv_key = out[2]
    except: priv_key = "GE6Ek7S...="

    # --- 全局 WARP 路由配置 ---
    cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess", "listen": "127.0.0.1", "listen_port": PORT,
            "users": [{"uuid": UID}],
            "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}
        }],
        "outbounds": [
            {
                "type": "wireguard", 
                "tag": "warp", 
                "server": "engage.cloudflareclient.com", 
                "server_port": 2408, 
                "local_address": ["172.16.0.2/32", "2606:4700:110:8285:343b:d165:10a4:6443/128"], 
                "private_key": priv_key, 
                "mtu": 1280
            },
            {"type": "direct", "tag": "direct"}
        ],
        "route": {
            "rules": [
                # 排除针对 Cloudflare Tunnel 自身的控制流，防止死循环
                {"protocol": "dns", "outbound": "direct"},
                {"domain_suffix": ["cloudflare.com", "cloudflareclient.com"], "outbound": "direct"}
            ],
            "final": "warp"  # 核心修改：所有剩余流量强制走 WARP
        }
    }
    with open("sb.json", "w") as f: json.dump(cfg, f)

    # 构造并打印节点链接
    vm = {"v":"2","ps":"WARP-Global-Node","add":DOMAIN,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm","tls":"tls","sni":DOMAIN}
    link = "vmess://" + base64.b64encode(json.dumps(vm).encode()).decode()
    
    print("\n" + "🌍" * 15, flush=True)
    print("【 部署成功：已开启全局 WARP 出口 】", flush=True)
    print(f"节点链接: {link}", flush=True)
    print("🌍" * 15 + "\n", flush=True)

    # 启动进程
    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    log("服务正在后台运行，所有访问将通过 Cloudflare WARP 转发。")
    while True: time.sleep(60)

if __name__ == "__main__":
    run()
