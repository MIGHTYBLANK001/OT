#!/usr/bin/env python3
import os, sys, json, base64, platform, subprocess, ssl, time, tarfile
from pathlib import Path
import urllib.request

# --- 环境配置 ---
BASE_DIR = Path("/tmp/.agsb_lite").resolve()
# 核心参数
UID = "ee1f6ad8-dca8-47d9-8d17-1a2983551702"
PORT = 49999
TOKEN = "eyJhIjoiN2UxMzc3ODMyY2VmOTliZTIxYjI3MTQzMWU3NzA1ZWYiLCJ0IjoiMzYxNmQ5NzMtNmViMi00ZDViLWFhYWMtZjIwNjM4YzVjMzdkIiwicyI6IllXVXlNRGswWVRVdFpUZzRaQzAwTURkaExUa3pNMkl0WlRGbVptUXlOekl6WVRCaiJ9"
DOMAIN = "pynode.lun.xx.kg"

def setup():
    if not BASE_DIR.exists(): BASE_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(BASE_DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    
    # 下载核心组件
    sb_bin = BASE_DIR / "sing-box"
    if not sb_bin.exists():
        url = f"https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz"
        urllib.request.urlretrieve(url, "sb.tar.gz")
        with tarfile.open("sb.tar.gz") as tar:
            for m in tar.getmembers():
                if m.name.endswith("sing-box"):
                    m.name = os.path.basename(m.name); tar.extract(m, path=BASE_DIR)
        sb_bin.chmod(0o755)

    cf_bin = BASE_DIR / "cloudflared"
    if not cf_bin.exists():
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
        urllib.request.urlretrieve(url, cf_bin)
        cf_bin.chmod(0o755)
    return sb_bin, cf_bin

def run():
    sb, cf = setup()
    
    # 1. 生成 WARP 密钥
    try:
        out = subprocess.check_output([str(sb), "generate", "wg-keypair"]).decode().split()
        priv_key = out[2]
    except: priv_key = "GE6Ek7S...="

    # 2. 极简配置：AI 走 WARP
    cfg = {
        "inbounds": [{"type": "vmess", "listen": "127.0.0.1", "listen_port": PORT, "users": [{"uuid": UID}], "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}}],
        "outbounds": [
            {"type": "direct", "tag": "direct"},
            {"type": "wireguard", "tag": "warp", "server": "engage.cloudflareclient.com", "server_port": 2408, "local_address": ["172.16.0.2/32"], "private_key": priv_key, "mtu": 1280}
        ],
        "route": {"rules": [{"domain_suffix": ["openai.com", "chatgpt.com", "claude.ai", "gemini.google.com"], "outbound": "warp"}]}
    }
    with open("sb.json", "w") as f: json.dump(cfg, f)

    # 3. 启动进程
    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 4. 立即输出节点分享链接 (直接使用域名，不依赖优选IP列表)
    vm = {
        "v": "2", "ps": "AI-WARP-Main", "add": DOMAIN, "port": "443", "id": UID,
        "net": "ws", "host": DOMAIN, "path": f"/{UID[:8]}-vm", "tls": "tls", "sni": DOMAIN
    }
    link = "vmess://" + base64.b64encode(json.dumps(vm).encode()).decode()
    
    print("\n" + "⭐" * 20)
    print("✅ 服务已成功启动！")
    print("🚀 AI 分流已开启：ChatGPT/Claude 自动走 WARP 出站")
    print("\n[ 节点分享链接 ]:")
    print(link)
    print("⭐" * 20 + "\n")

    # 保活
    while True: time.sleep(60)

if __name__ == "__main__":
    run()
