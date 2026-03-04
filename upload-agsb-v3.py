import os, json, base64, platform, subprocess, time, tarfile, threading
from pathlib import Path
import urllib.request
import streamlit as st

BASE_DIR = Path("/tmp/.agsb_final").resolve()
UID = st.secrets.get("UUID", "")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "")
PORT = 49999
WS_PATH = f"/{UID[:8]}-vm"

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

@st.cache_resource
def start_node():
    sb, cf = setup()
    os.system("pkill -9 sing-box >/dev/null 2>&1")
    os.system("pkill -9 cloudflared >/dev/null 2>&1")
    time.sleep(2)

    cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess", "listen": "127.0.0.1", "listen_port": PORT,
            "users": [{"uuid": UID}], "sniff": True,
            "transport": {"type": "ws", "path": WS_PATH}
        }],
        "outbounds": [{"type": "direct", "domain_strategy": "ipv4_only"}]
    }
    with open("sb.json", "w") as f: json.dump(cfg, f)

    subprocess.Popen([str(sb), "run", "-c", "sb.json"], start_new_session=True)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], start_new_session=True)
    
    # 将节点信息输出到控制台日志
    vmess = {"v":"2", "ps":"streamlit-app-VM", "add":DOMAIN, "port":"443", "id":UID, "net":"ws", "host":DOMAIN, "path":WS_PATH, "tls":"tls", "sni":DOMAIN}
    link = "vmess://" + base64.b64encode(json.dumps(vmess).encode()).decode()
    print(f"\n[NODE_LINK] {link}\n", flush=True)

    threading.Thread(target=keep_alive, daemon=True).start()
    return True

def main():
    st.set_page_config(page_title="System", page_icon="🟢")
    st.markdown("""<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;}</style>""", unsafe_allow_html=True)
    st.title("🟢 Service Online")
    
    if not TOKEN or not DOMAIN:
        st.error("Missing Secrets!")
        return

    start_node()
    st.success("Services are running. Connection info sent to console logs.")

if __name__ == "__main__":
    main()
