#!/usr/bin/env python3
import os, sys, json, base64, platform, subprocess, ssl, time, tarfile
from pathlib import Path
import urllib.request

# --- 配置 ---
BASE_DIR = Path("/tmp/.agsb_final").resolve()
IP_URL = "https://raw.githubusercontent.com/MIGHTYBLANK001/OT/refs/heads/main/IP"
UID = "ee1f6ad8-dca8-47d9-8d17-1a2983551702"
PORT = 49999
TOKEN = "eyJhIjoiN2UxMzc3ODMyY2VmOTliZTIxYjI3MTQzMWU3NzA1ZWYiLCJ0IjoiMzYxNmQ5NzMtNmViMi00ZDViLWFhYWMtZjIwNjM4YzVjMzdkIiwicyI6IllXVXlNRGswWVRVdFpUZzRaQzAwTURkaExUa3pNMkl0WlRGbVptUXlOekl6WVRCaiJ9"
DOMAIN = "pynode.lun.xx.kg"

def setup():
    if not BASE_DIR.exists(): BASE_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(BASE_DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    
    sb_bin = BASE_DIR / "sing-box"
    if not sb_bin.exists():
        sb_url = f"https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz"
        urllib.request.urlretrieve(sb_url, BASE_DIR / "sb.tar.gz")
        with tarfile.open(BASE_DIR / "sb.tar.gz") as tar:
            for m in tar.getmembers():
                if m.name.endswith("sing-box"):
                    m.name = os.path.basename(m.name)
                    tar.extract(m, path=BASE_DIR)
        sb_bin.chmod(0o755)

    cf_bin = BASE_DIR / "cloudflared"
    if not cf_bin.exists():
        cf_url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
        urllib.request.urlretrieve(cf_url, cf_bin)
        cf_bin.chmod(0o755)
    return sb_bin, cf_bin

def generate_subscription_url():
    """生成订阅并上传至临时云端，输出可直接引用的URL"""
    print("\n" + "🌐" * 10 + " 正在生成 URL 订阅链接 " + "🌐" * 10)
    try:
        ctx = ssl._create_unverified_context()
        ips = urllib.request.urlopen(IP_URL, context=ctx).read().decode().splitlines()
        path = f"/{UID[:8]}-vm?ed=2048"
        
        links = []
        for i, ip in enumerate([x.strip() for x in ips if x.strip() and not x.startswith("#")]):
            vm = {"v":"2","ps":f"AI-WARP-{i+1}","add":ip,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":path,"tls":"tls","sni":DOMAIN}
            links.append("vmess://" + base64.b64encode(json.dumps(vm).encode()).decode())
        
        sub_content = base64.b64encode("\n".join(links).encode()).decode()
        
        # 使用 file.io 上传（有效期14天，下载1次后销毁，或者根据API调整）
        # 也可以换成其他持久化的 Pastebin API
        data = f"text={sub_content}".encode()
        req = urllib.request.Request("https://file.io/?expires=14d", data=data, method="POST")
        with urllib.request.urlopen(req) as response:
            res_json = json.loads(response.read().decode())
            if res_json.get("success"):
                print(f"\n✅ 你的 URL 订阅链接已生成 (14天有效):")
                print(f"👉 {res_json['link']}")
                print("\n将此链接直接填入 V2RayN / Shadowrocket 订阅设置即可。")
            else:
                print("[-] 上传失败，请查看下方备用 Base64 内容。")
                print(sub_content)
    except Exception as e:
        print(f"[-] 订阅生成/上传出错: {e}")

def run():
    sb, cf = setup()
    # 极简配置：AI走WARP
    out = subprocess.check_output([str(sb), "generate", "wg-keypair"]).decode().split()
    cfg = {
        "inbounds": [{"type": "vmess", "listen": "127.0.0.1", "listen_port": PORT, "users": [{"uuid": UID}], "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}}],
        "outbounds": [
            {"type": "direct", "tag": "direct"},
            {"type": "wireguard", "tag": "warp", "server": "engage.cloudflareclient.com", "server_port": 2408, "local_address": ["172.16.0.2/32"], "private_key": out[2], "mtu": 1280}
        ],
        "route": {"rules": [{"domain_suffix": ["openai.com", "chatgpt.com", "claude.ai"], "outbound": "warp"}]}
    }
    with open(BASE_DIR / "sb.json", "w") as f: json.dump(cfg, f)

    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    subprocess.Popen([str(sb), "run", "-c", str(BASE_DIR / "sb.json")], cwd=BASE_DIR)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], cwd=BASE_DIR)
    
    time.sleep(8)
    generate_subscription_url()
    while True: time.sleep(60)

if __name__ == "__main__":
    run()
    # 解决 Streamlit 多次执行导致的路径问题
    sb_path, cf_path = download_bins()
    generate_config(sb_path)
    start_services(sb_path, cf_path)
    export_nodes()
    
    # 保持主线程存活
    while True:
        time.sleep(60)
