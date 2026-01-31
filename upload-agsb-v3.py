#!/usr/bin/env python3
import os, sys, json, base64, platform, subprocess, ssl, time, tarfile
from pathlib import Path
import urllib.request

# --- 环境适配 ---
# Streamlit 环境下 /tmp 是唯一可靠的可执行写入路径
BASE_DIR = Path("/tmp/.agsb_deploy").resolve()
IP_URL = "https://raw.githubusercontent.com/MIGHTYBLANK001/OT/refs/heads/main/IP"

# 默认参数
UID = "ee1f6ad8-dca8-47d9-8d17-1a2983551702"
PORT = 49999
TOKEN = "eyJhIjoiN2UxMzc3ODMyY2VmOTliZTIxYjI3MTQzMWU3NzA1ZWYiLCJ0IjoiMzYxNmQ5NzMtNmViMi00ZDViLWFhYWMtZjIwNjM4YzVjMzdkIiwicyI6IllXVXlNRGswWVRVdFpUZzRaQzAwTURkaExUa3pNMkl0WlRGbVptUXlOekl6WVRCaiJ9"
DOMAIN = "pynode.lun.xx.kg"

def download_bins():
    if not BASE_DIR.exists(): BASE_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(BASE_DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    
    # 下载 sing-box
    sb_bin = BASE_DIR / "sing-box"
    if not sb_bin.exists():
        print("[*] 正在下载并解压 Sing-box...")
        sb_url = f"https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz"
        tmp_tar = BASE_DIR / "sb.tar.gz"
        urllib.request.urlretrieve(sb_url, tmp_tar)
        with tarfile.open(tmp_tar) as tar:
            # 自动寻找 tar 包深层目录里的二进制文件并提取
            for member in tar.getmembers():
                if member.name.endswith("sing-box"):
                    member.name = os.path.basename(member.name)
                    tar.extract(member, path=BASE_DIR)
        sb_bin.chmod(0o755)

    # 下载 cloudflared
    cf_bin = BASE_DIR / "cloudflared"
    if not cf_bin.exists():
        print("[*] 正在下载 Cloudflared...")
        cf_url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
        urllib.request.urlretrieve(cf_url, cf_bin)
        cf_bin.chmod(0o755)
    
    return sb_bin, cf_bin

def generate_config(sb_bin):
    # 利用 sing-box 自身生成 WARP 密钥
    try:
        out = subprocess.check_output([str(sb_bin), "generate", "wg-keypair"]).decode().split()
        priv_key = out[2]
    except:
        priv_key = "GE6Ek7S...="

    config = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess", "listen": "127.0.0.1", "listen_port": PORT,
            "users": [{"uuid": UID}],
            "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}
        }],
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
                # AI 相关域名强制走 WARP
                {"domain_suffix": ["openai.com", "chatgpt.com", "anthropic.com", "claude.ai", "gemini.google.com"], "outbound": "warp"},
                {"geosite": ["netflix", "disney"], "outbound": "warp"}
            ],
            "final": "direct"
        }
    }
    with open(BASE_DIR / "sb.json", "w") as f:
        json.dump(config, f, indent=2)

def start_services(sb_bin, cf_bin):
    # 检查进程是否已在运行
    try:
        subprocess.check_output(["pkill", "-0", "-f", "sing-box"])
        print("[!] 服务已在运行中，跳过启动。")
    except:
        print("[*] 启动双隧道服务...")
        subprocess.Popen([str(sb_bin), "run", "-c", str(BASE_DIR / "sb.json")], cwd=BASE_DIR)
        subprocess.Popen([str(cf_bin), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], cwd=BASE_DIR)

def export_nodes():
    try:
        ctx = ssl._create_unverified_context()
        ips = urllib.request.urlopen(IP_URL, context=ctx).read().decode().splitlines()
        nodes = []
        for ip in [i.strip() for i in ips if i.strip() and not i.startswith("#")]:
            v = {"v":"2","ps":f"AI-WARP-{ip}","add":ip,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm?ed=2048","tls":"tls","sni":DOMAIN}
            nodes.append("vmess://" + base64.b64encode(json.dumps(v).encode()).decode())
        
        print("\n" + "="*50)
        print("✅ 部署成功！AI 服务已分流至 WARP。")
        print(f"🔗 首选节点链接:\n{nodes[0] if nodes else '获取失败'}")
        print("="*50)
    except:
        print("[-] 无法从远程拉取优选IP。")

if __name__ == "__main__":
    # 解决 Streamlit 多次执行导致的路径问题
    sb_path, cf_path = download_bins()
    generate_config(sb_path)
    start_services(sb_path, cf_path)
    export_nodes()
    
    # 保持主线程存活
    while True:
        time.sleep(60)
