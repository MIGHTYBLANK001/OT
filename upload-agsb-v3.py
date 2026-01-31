#!/usr/bin/env python3
import os, sys, json, base64, platform, subprocess, ssl, argparse
from pathlib import Path
import urllib.request

# --- 核心配置 ---
DIR = Path.home() / ".agsb"
IP_URL = "https://raw.githubusercontent.com/MIGHTYBLANK001/OT/refs/heads/main/IP"
UNAME, UID, PORT = "mightyblank001", "ee1f6ad8-dca8-47d9-8d17-1a2983551702", 49999
TOKEN = "eyJhIjoiN2UxMzc3ODMyY2VmOTliZTIxYjI3MTQzMWU3NzA1ZWYiLCJ0IjoiMzYxNmQ5NzMtNmViMi00ZDViLWFhYWMtZjIwNjM4YzVjMzdkIiwicyI6IllXVXlNRGswWVRVdFpUZzRaQzAwTURkaExUa3pNMkl0WlRGbVptUXlOekl6WVRCaiJ9"
DOMAIN = "pynode.lun.xx.kg"

def http_get(url):
    ctx = ssl._create_unverified_context()
    return urllib.request.urlopen(urllib.request.Request(url), context=ctx).read().decode().strip()

def setup_bin():
    DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    # 下载核心组件 (精简版下载逻辑)
    os.system(f"curl -L https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz | tar -xz --strip-components=1 && chmod +x sing-box")
    os.system(f"curl -L -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch} && chmod +x cloudflared")

def create_config():
    # 自动生成 WireGuard 密钥
    key_pair = subprocess.check_output(["./sing-box", "generate", "wg-keypair"]).decode().split()
    priv_key = key_pair[2] 
    
    ws_path = f"/{UID[:8]}-vm"
    cfg = {
        "log": {"level": "error"},
        "inbounds": [{"type": "vmess", "listen": "127.0.0.1", "listen_port": PORT, "users": [{"uuid": UID}], "transport": {"type": "ws", "path": ws_path}}],
        "outbounds": [
            {"type": "direct", "tag": "direct"},
            {
                "type": "wireguard", 
                "tag": "warp", 
                "server": "engage.cloudflareclient.com", 
                "server_port": 2408, 
                "local_address": ["172.16.0.2/32", "2606:4700:110:8285:343b:d165:10a4:6443/128"], 
                "private_key": priv_key, 
                "mtu": 1280
            }
        ],
        "route": {
            "rules": [
                # AI 相关服务 & 常用流媒体 强制走 WARP
                {
                    "geosite": ["openai", "anthropic", "google-fuchia", "netflix", "disney", "facebook", "instagram"], 
                    "outbound": "warp"
                },
                # 显式添加一些 AI 域名以防 geosite 不全
                {
                    "domain_suffix": ["openai.com", "chatgpt.com", "anthropic.com", "claude.ai", "gemini.google.com"],
                    "outbound": "warp"
                }
            ],
            "final": "direct"
        }
    }
    with open("sb.json", "w") as f: json.dump(cfg, f, indent=2)

def run():
    # 清理旧进程并启动
    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    subprocess.Popen(f"nohup ./sing-box run -c sb.json >/dev/null 2>&1 &", shell=True)
    subprocess.Popen(f"nohup ./cloudflared tunnel run --token {TOKEN} >/dev/null 2>&1 &", shell=True)
    
    # 导出节点
    try:
        ips = http_get(IP_URL).splitlines()
        nodes = []
        for ip in [i.strip() for i in ips if i.strip() and not i.startswith("#")]:
            vm = {"v":"2","ps":f"AI-WARP-{ip}","add":ip,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm?ed=2048","tls":"tls","sni":DOMAIN}
            nodes.append("vmess://" + base64.b64encode(json.dumps(vm).encode()).decode())
        
        with open("allnodes.txt", "w") as f: f.write("\n".join(nodes))
        print(f"\n✅ 部署成功！\n🚀 已自动分流：OpenAI/ChatGPT, Claude, Gemini, Netflix 均走 WARP 出站。")
        print(f"🔗 订阅文件: {DIR}/allnodes.txt")
    except:
        print("❌ 节点生成失败，请检查网络或 IP URL")

if __name__ == "__main__":
    setup_bin()
    create_config()
    run()
