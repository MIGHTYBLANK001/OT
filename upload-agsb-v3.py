import os, json, base64, platform, subprocess, time, tarfile, threading
from pathlib import Path
import urllib.request
import streamlit as st

# --- 配置区 ---
BASE_DIR = Path("/tmp/.agsb_final").resolve()
UID = st.secrets.get("UUID", "ee1f6ad8-dca8-47d9-8d17-1a2983551702")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "")
PORT = 49999

def keep_alive():
    """保活逻辑：模拟浏览器访问，防止 403 拦截"""
    if not DOMAIN: return
    # 延迟 1 分钟执行第一次保活，等待隧道完全建立
    time.sleep(60)
    while True:
        try:
            url = f"https://{DOMAIN}"
            # 模拟常用浏览器 User-Agent
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                print(f"[*] Keep-alive success: {response.getcode()}", flush=True)
        except Exception as e:
            print(f"[!] Keep-alive failed: {e}", flush=True)
        time.sleep(1200) # 每 20 分钟访问一次

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
                    m.name = os.path.basename(m.name)
                    tar.extract(m, path=BASE_DIR, filter='data' if hasattr(tarfile, 'data_filter') else None)
        sb_bin.chmod(0o755)

    if not cf_bin.exists():
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
        urllib.request.urlretrieve(url, cf_bin)
        cf_bin.chmod(0o755)
    return sb_bin, cf_bin

@st.cache_resource(show_spinner="Service starting...")
def start_node():
    sb, cf = setup()
    # 强制清理
    os.system("pkill -9 sing-box >/dev/null 2>&1")
    os.system("pkill -9 cloudflared >/dev/null 2>&1")
    time.sleep(2)

    # 简易直接代理配置
    cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess", "listen": "127.0.0.1", "listen_port": PORT,
            "users": [{"uuid": UID}], "sniff": True,
            "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}
        }],
        "outbounds": [{"type": "direct", "domain_strategy": "ipv4_only"}]
    }
    with open("sb.json", "w") as f: json.dump(cfg, f)

    # 启动
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], start_new_session=True)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], start_new_session=True)
    
    # 启动保活
    threading.Thread(target=keep_alive, daemon=True).start()
    return True

def main():
    st.set_page_config(page_title="Stable Node", page_icon="🛡️")
    st.title("🛡️ Single Instance Gateway")

    if not TOKEN or not DOMAIN:
        st.warning("Please set TOKEN and DOMAIN in Secrets.")
        return

    start_node()

    # 节点详情
    vmess = {"v":"2", "ps":"Direct-Stable", "add":DOMAIN, "port":"443", "id":UID, "net":"ws", "host":DOMAIN, "path":f"/{UID[:8]}-vm", "tls":"tls", "sni":DOMAIN}
    link = "vmess://" + base64.b64encode(json.dumps(vmess).encode()).decode()

    st.success("✅ Application is active with 30-min keep-alive.")
    st.code(link)
    
    if st.button("Reset Service"):
        st.cache_resource.clear()
        st.rerun()

if __name__ == "__main__":
    main()
