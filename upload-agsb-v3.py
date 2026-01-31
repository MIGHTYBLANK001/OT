import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

# --- 极简配置 ---
BASE_DIR = Path("/tmp/.agsb_final").resolve()
UID = st.secrets.get("UUID", "ee1f6ad8-dca8-47d9-8d17-1a2983551702")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "streamlit-cf-warp-py.aieo.eu.cc")
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
    st.title("Service Gateway")
    sb, cf = setup()

    # 1. 彻底杀掉旧进程 (不使用 lsof)
    os.system("pkill -9 sing-box >/dev/null 2>&1")
    os.system("pkill -9 cloudflared >/dev/null 2>&1")
    time.sleep(2)

    # 2. 生成 Sing-box 配置
    cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess", "listen": "127.0.0.1", "listen_port": PORT,
            "users": [{"uuid": UID}], "sniff": True,
            "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}
        }],
        "outbounds": [{"type": "direct"}]
    }
    with open("sb.json", "w") as f: json.dump(cfg, f)

    # 3. 启动服务
    subprocess.Popen([str(sb), "run", "-c", "sb.json"])
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN])

    # 4. 界面显示
    vmess_cfg = {"v":"2", "ps":"ZT-WARP-Node", "add":DOMAIN, "port":"443", "id":UID, "net":"ws", "host":DOMAIN, "path":f"/{UID[:8]}-vm", "tls":"tls", "sni":DOMAIN}
    link = "vmess://" + base64.b64encode(json.dumps(vmess_cfg).encode()).decode()
    
    st.success("✅ 隧道已重新握手，请检查 Zero Trust 状态。")
    st.code(link)
    
    # 5. 保持运行 (非阻塞方式)
    st.info("节点在线中...")
    # 不要使用 while True，Streamlit 运行完代码后会自动保持环境

if __name__ == "__main__":
    run()
