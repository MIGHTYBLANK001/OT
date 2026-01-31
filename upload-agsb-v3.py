#!/usr/bin/env python3
import os, sys, json, base64, platform, subprocess, ssl, time
from pathlib import Path
import urllib.request

# --- 环境适配：强制使用容器可写的 /tmp 路径 ---
DIR = Path("/tmp/.agsb_service")
IP_URL = "https://raw.githubusercontent.com/MIGHTYBLANK001/OT/refs/heads/main/IP"

# 默认参数
UID = "ee1f6ad8-dca8-47d9-8d17-1a2983551702"
PORT = 49999
TOKEN = "eyJhIjoiN2UxMzc3ODMyY2VmOTliZTIxYjI3MTQzMWU3NzA1ZWYiLCJ0IjoiMzYxNmQ5NzMtNmViMi00ZDViLWFhYWMtZjIwNjM4YzVjMzdkIiwicyI6IllXVXlNRGswWVRVdFpUZzRaQzAwTURkaExUa3pNMkl0WlRGbVptUXlOekl6WVRCaiJ9"
DOMAIN = "pynode.lun.xx.kg"

def download_file(url, filename):
    """原生 Python 下载，解决 curl (23) 权限报错"""
    print(f"[*] 正在下载: {filename}...")
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(url, context=ctx) as response, open(filename, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
        os.chmod(filename, 0o755)
        return True
    except Exception as e:
        print(f"[-] 下载失败 {filename}: {e}")
        return False

def setup():
    if not DIR.exists(): DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(DIR)
    
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    
    # 1. 下载核心 (改为直接从 GitHub 下载编译好的二进制或通过 URL)
    # 注意：此处建议使用您备份的可靠直连链接
    sb_url = f"https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz"
    cf_url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
    
    # 自动解压 sing-box (简化逻辑)
    if not (DIR / "sing-box").exists():
        os.system(f"wget -qO- {sb_url} | tar xz --strip-components=1")
    if not (DIR / "cloudflared").exists():
        download_file(cf_url, "cloudflared")

def create_config():
    # 自动生成 WARP 密钥
    try:
        res = subprocess.check_output(["./sing-box", "generate", "wg-keypair"]).decode().split()
        priv_key = res[2]
    except:
        priv_key = "GE6Ek7S...=" # 兜底

    ws_path = f"/{UID[:8]}-vm"
    cfg = {
        "log": {"level": "error"},
        "inbounds": [{"type": "vmess", "listen": "127.0.0.1", "listen_port": PORT, "users": [{"uuid": UID}], "transport": {"type": "ws", "path": ws_path}}],
        "outbounds": [
            {"type": "direct", "tag": "direct"},
            {
                "type": "wireguard", "tag": "warp",
                "server": "engage.cloudflareclient.com", "server_port": 2408,
                "local_address": ["172.16.0.2/32", "2606:4700:110:8285:343b:d165:10a4:6443/128"],
                "private_key": priv_key, "mtu": 1280
            }
        ],
        "route": {
            "rules": [
                # AI 服务分流：OpenAI, Claude, Gemini, Copilot
                {
                    "domain_suffix": [
                        "openai.com", "chatgpt.com", "oaistatic.com", "oaiusercontent.com",
                        "anthropic.com", "claude.ai", "gemini.google.com", "proactive.google.com",
                        "bing.com", "microsoftapp.net"
                    ],
                    "outbound": "warp"
                },
                {"geosite": ["netflix", "disney"], "outbound": "warp"}
            ],
            "final": "direct"
        }
    }
    with open("sb.json", "w") as f: json.dump(cfg, f, indent=2)

def run():
    print("[*] 启动双进程隧道...")
    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    
    # 使用 Popen 确保不会阻塞主进程
    subprocess.Popen(["./sing-box", "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["./cloudflared", "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 生成节点链接
    try:
        ctx = ssl._create_unverified_context()
        ips = urllib.request.urlopen(IP_URL, context=ctx).read().decode().splitlines()
        nodes = []
        for ip in [i.strip() for i in ips if i.strip() and not i.startswith("#")]:
            v = {"v":"2","ps":f"AI-WARP-{ip}","add":ip,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm?ed=2048","tls":"tls","sni":DOMAIN}
            nodes.append("vmess://" + base64.b64encode(json.dumps(v).encode()).decode())
        
        with open("allnodes.txt", "w") as f: f.write("\n".join(nodes))
        print(f"\n✅ 部署完成！\n节点已生成至: {DIR}/allnodes.txt\nAI 服务已强制分流至 WARP 节点。")
    except:
        print("[-] 节点获取失败，请确认 IP_URL 连通性。")

if __name__ == "__main__":
    setup()
    create_config()
    run()
    # 容器保活：防止脚本直接退出导致容器销毁进程
    while True: time.sleep(100)
