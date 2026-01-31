import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

# --- 核心配置 (请确保 Secrets 中已配置 UID 和 TOKEN) ---
BASE_DIR = Path("/tmp/.agsb_minimal").resolve()
UID = st.secrets.get("UUID", "")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "")
PORT = 49999

def setup():
    if not BASE_DIR.exists(): BASE_DIR.mkdir(parents=True)
    os.chdir(BASE_DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    sb_bin, cf_bin = BASE_DIR / "sing-box", BASE_DIR / "cloudflared"

    # 下载二进制文件
    if not sb_bin.exists():
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

    # --- 最简 Sing-box 配置：只做 VMess 桥接 ---
    cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess",
            "listen": "127.0.0.1",
            "listen_port": PORT,
            "users": [{"uuid": UID}],
            "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}
        }],
        "outbounds": [{"type": "direct"}]
    }

    with open("sb.json", "w") as f: json.dump(cfg, f)

    # --- 彻底清理旧进程，防止 bind 报错 ---
    os.system(f"kill -9 $(lsof -t -i:{PORT}) >/dev/null 2>&1")
    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    time.sleep(1)

    # --- 后台启动服务 ---
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 生成节点链接
    vmess_cfg = {
        "v":"2", "ps":"Streamlit-Bridge", "add":DOMAIN, "port":"443", "id":UID,
        "net":"ws", "host":DOMAIN, "path":f"/{UID[:8]}-vm", "tls":"tls", "sni":DOMAIN
    }
    link = "vmess://" + base64.b64encode(json.dumps(vmess_cfg).encode()).decode()
    
    print(f"\n✅ 极简节点已启动\n{link}\n", flush=True)
    st.code(link)

    while True: time.sleep(600)

if __name__ == "__main__":
    run()
