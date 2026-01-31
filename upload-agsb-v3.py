import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

# --- 配置 ---
BASE_DIR = Path("/tmp/.agsb_optimized").resolve()
UID = st.secrets.get("UUID", "")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "")
PORT = 49999

def log(msg):
    print(f"[*] {msg}", flush=True)

def setup():
    if not BASE_DIR.exists(): BASE_DIR.mkdir(parents=True)
    os.chdir(BASE_DIR)
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    sb_bin, cf_bin = BASE_DIR / "sing-box", BASE_DIR / "cloudflared"

    if not sb_bin.exists():
        log("下载 sing-box...")
        url = f"https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz"
        urllib.request.urlretrieve(url, "sb.tar.gz")
        with tarfile.open("sb.tar.gz") as tar:
            for m in tar.getmembers():
                if m.name.endswith("sing-box"):
                    m.name = os.path.basename(m.name); tar.extract(m, path=BASE_DIR)
        sb_bin.chmod(0o755)

    if not cf_bin.exists():
        log("下载 cloudflared...")
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
        urllib.request.urlretrieve(url, cf_bin)
        cf_bin.chmod(0o755)
    return sb_bin, cf_bin

def run():
    sb, cf = setup()

    # --- 性能优化版 Sing-box 配置 ---
    cfg = {
        "log": {"level": "warn"}, # 减少日志写入 IO
        "inbounds": [{
            "type": "vmess",
            "tag": "vmess-in",
            "listen": "127.0.0.1",
            "listen_port": PORT,
            "users": [{"uuid": UID}],
            "set_system_proxy": False,
            "sniff": True,
            "transport": {
                "type": "ws",
                "path": f"/{UID[:8]}-vm",
                "max_early_data": 2048, # 提升 WS 握手速度
                "early_data_header_name": "Sec-WebSocket-Protocol"
            }
        }],
        "outbounds": [{
            "type": "direct",
            "tag": "direct-out"
        }],
        "experimental": {
            "cache_file": {"enabled": True, "path": "cache.db"} # 开启缓存提升解析速度
        }
    }

    with open("sb.json", "w") as f: json.dump(cfg, f)

    # --- 强制清理占用端口的残留进程 ---
    log("清理旧进程...")
    os.system(f"fuser -k {PORT}/tcp >/dev/null 2>&1") # 杀掉占用端口的进程
    os.system("pkill -9 sing-box cloudflared >/dev/null 2>&1")
    time.sleep(1)

    # --- 启动服务 ---
    log("启动 Sing-box...")
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    log("启动 Cloudflared...")
    # 使用参数优化隧道性能
    subprocess.Popen([
        str(cf), "tunnel", "--no-autoupdate", "run", 
        "--protocol", "http2", # 强制 http2 模式在某些受限容器表现更稳
        "--token", TOKEN
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    link = "vmess://" + base64.b64encode(json.dumps({
        "v":"2","ps":"BRIDGE-NODE-OPT","add":DOMAIN,"port":"443","id":UID,
        "net":"ws","host":DOMAIN,"path":f"/{UID[:8]}-vm","tls":"tls","sni":DOMAIN
    }).encode()).decode()

    st.code(link)
    log(f"✅ 节点已就绪！端口 {PORT} 监听正常。")
    
    while True: time.sleep(600)

if __name__ == "__main__":
    run()
