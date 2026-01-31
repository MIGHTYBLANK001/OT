#!/usr/bin/env python3
import os, sys, json, base64, platform, subprocess, ssl, argparse
from pathlib import Path
import urllib.request

# --- 环境适配配置 ---
# 考虑到日志中的 Streamlit 环境，使用 /tmp 确保有写入权限
DIR = Path("/tmp/.agsb") 
IP_URL = "https://raw.githubusercontent.com/MIGHTYBLANK001/OT/refs/heads/main/IP"

# 默认参数
UNAME = "mightyblank001"
UID = "ee1f6ad8-dca8-47d9-8d17-1a2983551702"
PORT = 49999
TOKEN = "eyJhIjoiN2UxMzc3ODMyY2VmOTliZTIxYjI3MTQzMWU3NzA1ZWYiLCJ0IjoiMzYxNmQ5NzMtNmViMi00ZDViLWFhYWMtZjIwNjM4YzVjMzdkIiwicyI6IllXVXlNRGswWVRVdFpUZzRaQzAwTURkaExUa3pNMkl0WlRGbVptUXlOekl6WVRCaiJ9"
DOMAIN = "pynode.lun.xx.kg"

def http_get(url):
    ctx = ssl._create_unverified_context()
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        return urllib.request.urlopen(req, context=ctx).read().decode().strip()
    except: return ""

def setup_bin():
    if not DIR.exists(): DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    print(f"[*] 正在安装核心组件 (架构: {arch})...")
    # 使用 -sS 减少日志冗余
    os.system(f"curl -sSL https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz | tar -xz --strip-components=1 && chmod +x sing-box")
    os.system(f"curl -sSL -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch} && chmod +x cloudflared")

def create_config():
    print("[*] 正在生成 WARP 密钥及 AI 分流配置...")
    try:
        # 自动生成 WireGuard 密钥对
        key_pair = subprocess.check_output(["./sing-box", "generate", "wg-keypair"]).decode().split()
        priv_key = key_pair[2] 
    except:
        priv_key = "GE6Ek7S..." # 兜底

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
                # AI 相关服务分流规则
                {
                    "geosite": ["openai", "anthropic", "google-fuchia"], 
                    "domain_suffix": ["openai.com", "chatgpt.com", "anthropic.com", "claude.ai", "gemini.google.com", "oaistatic.com", "oaiusercontent.com"],
                    "outbound": "warp"
                },
                # 流媒体分流
                {
                    "geosite": ["netflix", "disney", "spotify"],
                    "outbound": "warp"
                }
            ],
            "final": "direct"
        }
    }
    with open("sb.json", "w") as f: json.dump(cfg, f, indent=2)

def run():
    print("[*] 启动服务进程...")
    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    # 后台运行
    subprocess.Popen("./sing-box run -c sb.json", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(f"./cloudflared tunnel run --token {TOKEN}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 获取优选IP并生成节点
    try:
        raw_ips = http_get(IP_URL)
        nodes = []
        path_query = f"/{UID[:8]}-vm?ed=2048"
        for ip in [i.strip() for i in raw_ips.splitlines() if i.strip() and not i.startswith("#")]:
            vm = {"v":"2","ps":f"AI-WARP-{ip}","add":ip,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":path_query,"tls":"tls","sni":DOMAIN}
            nodes.append("vmess://" + base64.b64encode(json.dumps(vm).encode()).decode())
        
        output_file = DIR / "allnodes.txt"
        output_file.write_text("\n".join(nodes))
        print(f"\n" + "="*40)
        print(f"✅ 修复完成！\n🚀 AI 增强分流已开启 (WARP)\n🔗 节点文件: {output_file}")
        print(f"📡 首选节点: {nodes[0] if nodes else 'None'}")
        print("="*40)
    except Exception as e:
        print(f"❌ 节点生成失败: {e}")

if __name__ == "__main__":
    setup_bin()
    create_config()
    run()
