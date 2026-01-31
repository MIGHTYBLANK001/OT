import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

# --- 极简桥接版 ---
BASE_DIR = Path("/tmp/.agsb_zt_final").resolve()
UID = st.secrets.get("UUID", "")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "")
PORT = 49999

def setup():
    if not BASE_DIR.exists(): BASE_DIR.mkdir(parents=True)
    os.chdir(BASE_DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    sb_bin, cf_bin = BASE_DIR / "sing-box", BASE_DIR / "cloudflared"

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
    
    # 纯净 VMess 转发配置
    cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess",
            "listen": "127.0.0.1",
            "listen_port": PORT,
            "users": [{"uuid": UID}],
            "sniff": True,
            "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}
        }],
        "outbounds": [{"type": "direct"}]
    }

    with open("sb.json", "w") as f: json.dump(cfg, f)

    # 清理并启动
    os.system(f"kill -9 $(lsof -t -i:{PORT}) >/dev/null 2>&1")
    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    time.sleep(1)

    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    link = "vmess://" + base64.b64encode(json.dumps({
        "v":"2","ps":"Cloudflare-ZeroTrust","add":DOMAIN,"port":"443","id":UID,"net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm","tls":"tls","sni":DOMAIN
    }).encode()).decode()
    
    st.success("✅ 服务已运行！")
    st.code(link)
    while True: time.sleep(600)

if __name__ == "__main__":
    run()
