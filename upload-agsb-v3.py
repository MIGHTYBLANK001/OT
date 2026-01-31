#!/usr/bin/env python3
import os, json, base64, platform, subprocess, time, tarfile, socket
from pathlib import Path
import urllib.request
import streamlit as st

# --- 配置 ---
BASE_DIR = Path("/tmp/.agsb_port_scanner").resolve()
UID = st.secrets.get("UUID", "ee1f6ad8-dca8-47d9-8d17-1a2983551702")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "pynode.lun.xx.kg")
PORT = 49999

def log(msg):
    print(f"[*] {msg}", flush=True)

# UDP 端口检测函数
def check_udp_port(host, port, timeout=2):
    """检测 UDP 端口是否可能有响应（虽然 UDP 是无状态的，但可以排除物理拦截）"""
    try:
        # 注意：由于 UDP 协议特性，真正的握手在 sing-box 内部完成
        # 这里仅做简单的套接字尝试，更高级的检测在 sing-box 运行后观察
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            # 发送一个空的探测包
            s.sendto(b'', (host, port))
            return True
    except Exception:
        return False

def setup():
    if not BASE_DIR.exists(): BASE_DIR.mkdir(parents=True)
    os.chdir(BASE_DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    sb_bin, cf_bin = BASE_DIR / "sing-box", BASE_DIR / "cloudflared"
    
    if not sb_bin.exists():
        log("下载内核...")
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
    
    # 自动探测可用端口
    target_host = "engage.cloudflareclient.com"
    potential_ports = [2408, 500, 4500, 1701, 854]
    best_port = 2408 # 默认
    
    log("正在探测可用 WARP 端口...")
    for p in potential_ports:
        if check_udp_port(target_host, p):
            log(f"端口 {p} 探测通过，尝试使用该端口。")
            best_port = p
            break

    try:
        out = subprocess.check_output([str(sb), "generate", "wg-keypair"]).decode().split()
        priv_key = out[2]
    except: priv_key = "GE6Ek7S...="

    # --- 配置逻辑：分流中转 ---
    cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess", "tag": "vmess-in",
            "listen": "127.0.0.1", "listen_port": PORT,
            "users": [{"uuid": UID}],
            "sniff": True, "sniff_override_destination": True,
            "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}
        }],
        "outbounds": [
            {
                "type": "wireguard",
                "tag": "warp-out",
                "server": target_host,
                "server_port": best_port, # 使用探测出的端口
                "local_address": ["172.16.0.2/32"],
                "private_key": priv_key,
                "mtu": 1120,
                "system_interface": False
            },
            {"type": "direct", "tag": "direct-out"}
        ],
        "route": {
            "rules": [
                {"domain_suffix": ["cloudflare.com", "argotunnel.com"], "outbound": "direct-out"},
                {"ip_is_private": True, "outbound": "direct-out"},
                {"inbound": ["vmess-in"], "outbound": "warp-out"}
            ],
            "final": "direct-out"
        }
    }
    
    with open("sb.json", "w") as f: json.dump(cfg, f)
    
    vm = {"v":"2","ps":f"WARP-P{best_port}","add":DOMAIN,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm","tls":"tls","sni":DOMAIN}
    link = "vmess://" + base64.b64encode(json.dumps(vm).encode()).decode()

    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"\n✅ 已选择端口: {best_port}\n节点: {link}\n", flush=True)
    while True: time.sleep(600)

if __name__ == "__main__":
    run()
