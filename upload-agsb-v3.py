import os, json, base64, platform, subprocess, time, tarfile, threading
from pathlib import Path
import urllib.request
import streamlit as st

# --- 基础配置 ---
BASE_DIR = Path("/tmp/.agsb_stable").resolve()
UID = st.secrets.get("UUID", "")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "")
PORT = 49999

def keep_alive():
    """保活逻辑：每 20 分钟访问一次自己的域名，防止休眠"""
    if not DOMAIN:
        return
    while True:
        try:
            # 访问自己的 HTTPS 地址，触发 Cloudflare 流量
            url = f"https://{DOMAIN}"
            urllib.request.urlopen(url, timeout=10)
            print(f"[*] Keep-alive ping sent to {url}", flush=True)
        except Exception as e:
            print(f"[!] Keep-alive failed: {e}", flush=True)
        # 每 20 分钟执行一次 (1200秒)，确保在 30 分钟阈值内
        time.sleep(1200)

def setup_binaries():
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

@st.cache_resource(show_spinner="启动核心服务中...")
def start_services():
    sb, cf = setup_binaries()

    # 清理旧进程
    os.system("pkill -9 sing-box >/dev/null 2>&1")
    os.system("pkill -9 cloudflared >/dev/null 2>&1")
    time.sleep(1)

    # 生成配置 (直接代理)
    cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess", "listen": "127.0.0.1", "listen_port": PORT,
            "users": [{"uuid": UID}], "sniff": True,
            "transport": {"type": "ws", "path": f"/{UID[:8]}-vm"}
        }],
        "outbounds": [{"type": "direct", "domain_strategy": "ipv4_only"}]
    }
    with open(BASE_DIR / "sb.json", "w") as f: json.dump(cfg, f)

    # 启动子进程
    subprocess.Popen([str(sb), "run", "-c", str(BASE_DIR / "sb.json")], start_new_session=True)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], start_new_session=True)
    
    # --- 启动保活线程 ---
    threading.Thread(target=keep_alive, daemon=True).start()
    
    return True

def main():
    st.set_page_config(page_title="Direct Proxy", page_icon="🌐")
    st.title("🌐 Stable Direct Gateway")

    if not TOKEN or not DOMAIN:
        st.error("请在 Secrets 中配置 TOKEN 和 DOMAIN (不带 https://)")
        return

    start_services()

    # 节点连接信息
    vmess_cfg = {
        "v": "2", "ps": "Direct-Stable", "add": DOMAIN, "port": "443", "id": UID,
        "net": "ws", "host": DOMAIN, "path": f"/{UID[:8]}-vm", "tls": "tls", "sni": DOMAIN
    }
    link = "vmess://" + base64.b64encode(json.dumps(vmess_cfg).encode()).decode()

    st.success("✅ 服务运行中且已开启 30 分钟防休眠保护")
    st.markdown("---")
    st.code(link, language="text")
    
    st.info(f"保活域名: {DOMAIN} | 端口: {PORT}")

if __name__ == "__main__":
    main()
