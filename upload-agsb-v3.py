#!/usr/bin/env python3
import os, sys, json, base64, platform, subprocess, ssl, time, tarfile
from pathlib import Path
import urllib.request

# --- 环境自适应配置 ---
# 强制使用 /tmp 确保在 Streamlit Cloud 有写入和执行权限
DIR = Path("/tmp/.agsb_final")
IP_URL = "https://raw.githubusercontent.com/MIGHTYBLANK001/OT/refs/heads/main/IP"

# 默认参数
UID = "ee1f6ad8-dca8-47d9-8d17-1a2983551702"
PORT = 49999
TOKEN = "eyJhIjoiN2UxMzc3ODMyY2VmOTliZTIxYjI3MTQzMWU3NzA1ZWYiLCJ0IjoiMzYxNmQ5NzMtNmViMi00ZDViLWFhYWMtZjIwNjM4YzVjMzdkIiwicyI6IllXVXlNRGswWVRVdFpUZzRaQzAwTURkaExUa3pNMkl0WlRGbVptUXlOekl6WVRCaiJ9"
DOMAIN = "pynode.lun.xx.kg"

def download_and_extract():
    if not DIR.exists(): DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(DIR)
    ctx = ssl._create_unverified_context()
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    
    # 1. 下载并解压 Sing-box (原生 Python 处理)
    sb_url = f"https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz"
    print(f"[*] 正在下载 Sing-box...")
    sb_tar = "sb.tar.gz"
    urllib.request.urlretrieve(sb_url, sb_tar)
    with tarfile.open(sb_tar) as tar:
        tar.extractall()
        # 寻找解压后的 sing-box 二进制文件位置并移动到当前目录
        for p in Path(".").rglob("sing-box"):
            if p.is_file():
                os.rename(p, "sing-box")
                break
    os.chmod("sing-box", 0o755)

    # 2. 下载 Cloudflared
    print(f"[*] 正在下载 Cloudflared...")
    cf_url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
    urllib.request.urlretrieve(cf_url, "cloudflared")
    os.chmod("cloudflared", 0o755)

def create_config():
    # 自动生成 WARP 密钥
    try:
        res = subprocess.check_output(["./sing-box", "generate", "wg-keypair"]).decode().split()
        priv_key = res[2]
    except:
        priv_key = "GE6Ek7S..." # 兜底

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
                {
                    "domain_suffix": [
                        "openai.com", "chatgpt.com", "oaistatic.com", "oaiusercontent.com",
                        "anthropic.com", "claude.ai", "gemini.google.com", "bing.com"
                    ],
                    "outbound": "warp"
                },
                {"geosite": ["netflix", "disney", "google"], "outbound": "warp"}
            ],
            "final": "direct"
        }
    }
    with open("sb.json", "w") as f: json.dump(cfg, f, indent=2)

def run_services():
    print("[*] 启动双隧道服务...")
    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    
    # 显式使用绝对路径启动，防止 FileNotFoundError
    sb_bin = str(DIR / "sing-box")
    cf_bin = str(DIR / "cloudflared")
    
    subprocess.Popen([sb_bin, "run", "-c", "sb.json"], cwd=DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([cf_bin, "tunnel", "--no-autoupdate", "run", "--token", TOKEN], cwd=DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 获取优选IP并输出节点
    try:
        ctx = ssl._create_unverified_context()
        ips = urllib.request.urlopen(IP_URL, context=ctx).read().decode().splitlines()
        nodes = []
        for ip in [i.strip() for i in ips if i.strip() and not i.startswith("#")]:
            v = {"v":"2","ps":f"AI-WARP-{ip}","add":ip,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm?ed=2048","tls":"tls","sni":DOMAIN}
            nodes.append("vmess://" + base64.b64encode(json.dumps(v).encode()).decode())
        
        print(f"\n✅ 部署完成！\n🚀 AI 服务（ChatGPT/Claude）已强制走 WARP 出站。")
        print(f"🔗 首选节点:\n{nodes[0] if nodes else '获取失败'}")
    except:
        print("[-] 节点生成异常")

if __name__ == "__main__":
    download_and_extract()
    create_config()
    run_services()
    # 保持主线程运行，防止容器关闭
    while True: time.sleep(60)
