import os, json, base64, platform, subprocess, time, tarfile, urllib.request
from pathlib import Path
import streamlit as st

BASE_DIR = Path("/tmp/.agsb_stable").resolve()
UID = st.secrets.get("UUID", "")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "")
PORT = 49999
WS_PATH = f"/{UID[:8]}-vm"
VLESS_PATH = f"/{UID[:8]}-vl"

def latest(owner, repo):
    with urllib.request.urlopen(f"https://api.github.com/repos/{owner}/{repo}/releases/latest", timeout=10) as r:
        return json.load(r)["tag_name"].lstrip("v")

def download(url, dst):
    tmp = str(dst) + ".part"
    urllib.request.urlretrieve(url, tmp)
    if os.path.getsize(tmp) < 1000000:
        os.remove(tmp)
        raise RuntimeError("download too small")
    os.replace(tmp, dst)

def extract_tar(tgz, base, name):
    with tarfile.open(tgz) as tar:
        for m in tar.getmembers():
            if m.name.endswith(name):
                m.name = os.path.basename(m.name)
                tar.extract(m, path=base, filter="data" if hasattr(tarfile, "data_filter") else None)

def run_cmd(cmd):
    return subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def mux():
    return {
        "enabled": True,
        "protocol": "mux",
        "max_connections": 16,
        "min_streams": 16,
        "max_streams": 1024,
        "padding": True,
        "brutal": True
    }

@st.cache_resource
def setup_and_start_services():
    if not BASE_DIR.exists():
        BASE_DIR.mkdir(parents=True)
    os.chdir(BASE_DIR)

    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    sb_bin, cf_bin = BASE_DIR / "sing-box", BASE_DIR / "cloudflared"

    if not sb_bin.exists() or sb_bin.stat().st_size < 1000000:
        sb_ver = latest("SagerNet", "sing-box")
        download(f"https://github.com/SagerNet/sing-box/releases/download/v{sb_ver}/sing-box-{sb_ver}-linux-{arch}.tar.gz", BASE_DIR / "sb.tgz")
        extract_tar(BASE_DIR / "sb.tgz", BASE_DIR, "sing-box")
        sb_bin.chmod(0o755)

    if not cf_bin.exists() or cf_bin.stat().st_size < 1000000:
        cf_ver = latest("cloudflare", "cloudflared")
        download(f"https://github.com/cloudflare/cloudflared/releases/download/{cf_ver}/cloudflared-linux-{arch}", cf_bin)
        cf_bin.chmod(0o755)

    os.system("pkill -9 sing-box >/dev/null 2>&1")
    os.system("pkill -9 cloudflared >/dev/null 2>&1")
    time.sleep(0.2)

    with open("sb.json", "w") as f:
        json.dump({
            "log": {"level": "error"},
            "inbounds": [
                {
                    "type": "vmess",
                    "tag": "vmess-in",
                    "listen": "127.0.0.1",
                    "listen_port": PORT,
                    "reuse_addr": True,
                    "tcp_keep_alive": "30s",
                    "users": [{"uuid": UID}],
                    "transport": {
                        "type": "ws",
                        "path": WS_PATH,
                        "multiplex": mux()
                    }
                },
                {
                    "type": "vless",
                    "tag": "vless-in",
                    "listen": "127.0.0.1",
                    "listen_port": PORT + 1,
                    "reuse_addr": True,
                    "tcp_keep_alive": "30s",
                    "users": [{"uuid": UID, "flow": ""}],
                    "transport": {
                        "type": "ws",
                        "path": VLESS_PATH,
                        "multiplex": mux()
                    }
                }
            ],
            "outbounds": [{"type": "direct", "tag": "direct"}]
        }, f)

    run_cmd([str(sb_bin), "run", "-c", "sb.json"])
    run_cmd([str(cf_bin), "tunnel", "--no-autoupdate", "--protocol", "auto", "run", "--token", TOKEN])

    vmess_config = {
        "v": "2",
        "ps": "Streamlit-Node",
        "add": DOMAIN,
        "port": "443",
        "id": UID,
        "aid": "0",
        "scy": "auto",
        "net": "ws",
        "type": "none",
        "host": DOMAIN,
        "path": WS_PATH,
        "tls": "tls",
        "sni": DOMAIN,
        "alpn": ""
    }
    vmess_link = "vmess://" + base64.b64encode(json.dumps(vmess_config).encode()).decode()

    vless_link = f"vless://{UID}@{DOMAIN}:443?encryption=none&security=tls&sni={DOMAIN}&type=ws&host={DOMAIN}&path={VLESS_PATH}#VLESS-Node"

    return vmess_link, vless_link

def main():
    st.set_page_config(page_title="Node Dashboard", page_icon="📊", layout="centered")
    st.markdown("""
    <style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container {padding-top: 1rem; padding-bottom: 1rem;}
    .node-box {background: #f1f5f9; padding: 14px; border-radius: 8px; border-left: 4px solid #3b82f6; margin: 8px 0;}
    .label {font-size: 0.85rem; color: #64748b; margin-bottom: 4px;}
    .code {font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.82rem; background: #0f172a; color: #38bdf8; padding: 10px; border-radius: 6px; overflow-x: auto;}
    </style>
    """, unsafe_allow_html=True)

    vmess_link, vless_link = setup_and_start_services() if TOKEN and DOMAIN and UID else ("", "")

    st.title("📊 Node Status Dashboard")
    st.caption("Real-time connection monitor")

    c1, c2, c3 = st.columns(3)
    c1.metric("Uptime", "99.9%", "🟢")
    c2.metric("Traffic", "0 B/s", "—")
    c3.metric("Region", "Auto", "🌍")

    st.write("---")
    st.subheader("🔐 Access Node Configuration")
    secret_key = st.text_input("Access Code", type="password")

    if secret_key == "green2026":
        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="label">VMess Link</div>', unsafe_allow_html=True)
            st.code(vmess_link, language=None)
        with col2:
            st.markdown('<div class="label">VLESS Link</div>', unsafe_allow_html=True)
            st.code(vless_link, language=None)
        st.write("---")
        st.subheader("🔧 Connection Parameters")
        t1, t2 = st.columns(2)
        with t1:
            st.markdown('<div class="label">Address</div>', unsafe_allow_html=True)
            st.code(DOMAIN)
            st.markdown('<div class="label">Port</div>', unsafe_allow_html=True)
            st.code("443")
            st.markdown('<div class="label">UUID</div>', unsafe_allow_html=True)
            st.code(UID)
        with t2:
            st.markdown('<div class="label">Network</div>', unsafe_allow_html=True)
            st.code("ws")
            st.markdown('<div class="label">Security</div>', unsafe_allow_html=True)
            st.code("tls")
            st.markdown('<div class="label">Path</div>', unsafe_allow_html=True)
            st.code(f"{WS_PATH} / {VLESS_PATH}")
    elif secret_key != "":
        st.error("Invalid Access Code.")

    st.write("---")
    st.caption(f"System Status: 🟢 Operational | Sync Time: {time.strftime('%X')}")

if __name__ == "__main__":
    main()
