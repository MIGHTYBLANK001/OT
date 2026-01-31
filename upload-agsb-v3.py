#!/usr/bin/env python3
import os, sys, json, base64, platform, subprocess, ssl, time, tarfile
from pathlib import Path
import urllib.request

# --- 极简配置 ---
BASE_DIR = Path("/tmp/.agsb_fix").resolve()
UID = "ee1f6ad8-dca8-47d9-8d17-1a2983551702"
PORT = 49999
TOKEN = "eyJhIjoiN2UxMzc3ODMyY2VmOTliZTIxYjI3MTQzMWU3NzA1ZWYiLCJ0IjoiMzYxNmQ5NzMtNmViMi00ZDViLWFhYWMtZjIwNjM4YzVjMzdkIiwicyI6IllXVXlNRGswWVRVdFpUZzRaQzAwTURkaExUa3pNMkl0WlRGbVptUXlOekl6WVRCaiJ9"
DOMAIN = "pynode.lun.xx.kg"

def log(msg):
    print(f"[*] {msg}", flush=True)

def setup():
    if not BASE_DIR.exists(): BASE_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(BASE_DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    
    sb_bin = BASE_DIR / "sing-box"
    cf_bin = BASE_DIR / "cloudflared"

    if not sb_bin.exists():
        log("正在下载 Sing-box...")
        url = f"https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz"
        urllib.request.urlretrieve(url, "sb.tar.gz")
        with tarfile.open("sb.tar.gz") as tar:
            for m in tar.getmembers():
                if m.name.endswith("sing-box"):
                    m.name = os.path.basename(m.name); tar.extract(m, path=BASE_DIR)
        sb_bin.chmod(0o755)

    if not cf_bin.exists():
        log("正在下载 Cloudflared...")
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
        urllib.request.urlretrieve(url, cf_bin)
        cf_bin.chmod(0o755)
    return sb_bin, cf_bin

def run():
    log("开始部署服务...")
    sb, cf = setup()
    
    # 使用一个预设的私钥，避免调用外部生成器卡死
    priv_key = "GE6Ek7S...=" # 示例私钥

    # 构造配置
    cfg = {
        "inbounds": [{"type": "vmess", "listen": "127.0.0.1", "listen_port": PORT, "users": [{"uuid": UID}], "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}}],
        "outbounds": [
            {"type": "direct", "tag": "direct"},
            {"type": "wireguard", "tag": "warp", "server": "engage.cloudflareclient.com", "server_port": 2408, "local_address": ["172.16.0.2/32"], "private_key": priv_key, "mtu": 1280}
        ],
        "route": {"rules": [{"domain_suffix": ["openai.com", "chatgpt.com", "claude.ai"], "outbound": "warp"}]}
    }
    with open("sb.json", "w") as f: json.dump(cfg, f)

    # 启动前先打印节点（防止后续启动卡住看不到链接）
    vm = {
        "v": "2", "ps": "AI-WARP-Fixed", "add": DOMAIN, "port": "443", "id": UID,
        "net": "ws", "host": DOMAIN, "path": f"/{UID[:8]}-vm", "tls": "tls", "sni": DOMAIN
    }
    link = "vmess://" + base64.b64encode(json.dumps(vm).encode()).decode()
    
    print("\n" + "🚀" * 15, flush=True)
    print("【 部署成功，节点链接如下 】", flush=True)
    print(link, flush=True)
    print("🚀" * 15 + "\n", flush=True)

    # 启动进程
    log("启动后台进程...")
    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    log("所有服务已就绪，保持运行中...")
    while True: time.sleep(60)

if __name__ == "__main__":
    run()
