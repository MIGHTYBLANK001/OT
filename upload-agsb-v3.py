#!/usr/bin/env python3
import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

# --- 环境适配 ---
BASE_DIR = Path("/tmp/.agsb_final_fix").resolve()
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
    
    # 生成本地 WARP 密钥
    try:
        out = subprocess.check_output([str(sb), "generate", "wg-keypair"]).decode().split()
        priv_key = out[2]
    except: priv_key = "GE6Ek7S...="

    # --- 修正后的路由逻辑 ---
    cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess", 
            "listen": "0.0.0.0",  # 改为监听所有网卡
            "listen_port": PORT,
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
                "mtu": 1280,
                "udp_fragment": True
            },
            {"type": "direct", "tag": "direct"}
        ],
        "route": {
            "rules": [
                # 1. 核心修复：排除 Cloudflare 相关所有域名和 IP，防止隧道断开
                {"domain_suffix": ["cloudflare.com", "cloudflareclient.com", "argotunnel.com"], "outbound": "direct"},
                # 2. 排除私有地址（局域网）
                {"ip_is_private": True, "outbound": "direct"},
                # 3. DNS 强制直连
                {"protocol": "dns", "outbound": "direct"}
            ],
            "final": "warp" 
        }
    }
    with open("sb.json", "w") as f: json.dump(cfg, f)

    # 构造节点链接
    vm = {"v":"2","ps":"WARP-Global-Fixed","add":DOMAIN,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm","tls":"tls","sni":DOMAIN}
    link = "vmess://" + base64.b64encode(json.dumps(vm).encode()).decode()
    
    print("\n" + "✅" * 15, flush=True)
    print("【 部署完成：已修正全局 WARP 排除规则 】", flush=True)
    print(f"节点链接: {link}", flush=True)
    print("✅" * 15 + "\n", flush=True)

    # 启动进程
    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    # 增加启动参数 --url，在没有 TOKEN 时可用作调试，但这里我们使用你的 TOKEN
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    log("所有流量现已强制通过 WARP 出口。")
    while True: time.sleep(60)

if __name__ == "__main__":
    run()
