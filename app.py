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
    st.set_page_config(page_title="EcoTracker", page_icon="🌱", layout="centered")
    st.markdown("""
    <style>
    #MainMenu, footer {visibility: hidden;}
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    .eco-header {background: linear-gradient(135deg, #2e7d32 0%, #1b5e20 100%); color: white; padding: 2rem; border-radius: 16px; text-align: center; margin-bottom: 2rem;}
    .eco-header h1 {margin: 0; font-size: 2.5rem;}
    .eco-header p {margin: 0.5rem 0 0; opacity: 0.9;}
    .stat-card {background: #f1f8e9; border-left: 5px solid #4caf50; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;}
    .stat-value {font-size: 1.8rem; font-weight: bold; color: #2e7d32;}
    .stat-label {font-size: 0.9rem; color: #558b2f;}
    .tip-card {background: #e8f5e9; border-radius: 10px; padding: 1.2rem; margin: 1rem 0; border: 1px solid #c8e6c9;}
    .auth-box {background: #fff3e0; border: 2px dashed #ffb74d; border-radius: 12px; padding: 1.5rem; margin-top: 2rem;}
    .node-card {background: #e3f2fd; border-radius: 10px; padding: 1.2rem; margin: 0.8rem 0; border: 1px solid #bbdefb;}
    .node-title {font-weight: bold; color: #1565c0; margin-bottom: 0.5rem;}
    </style>
    """, unsafe_allow_html=True)

    vmess_link, vless_link = setup_and_start_services() if TOKEN and DOMAIN and UID else ("", "")

    st.markdown("""
    <div class="eco-header">
        <h1>🌱 EcoTracker</h1>
        <p>Personal Carbon Footprint Tracker &nbsp;|&nbsp; Respect Nature, Protect Earth</p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="stat-card"><div class="stat-value">42.5 km</div><div class="stat-label">Walking / Cycling</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="stat-card"><div class="stat-value">180 L</div><div class="stat-label">Water Saved</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="stat-card"><div class="stat-value">12.8 kg</div><div class="stat-label">Carbon Reduced</div></div>', unsafe_allow_html=True)

    st.write("---")
    st.subheader("📊 Daily Activity Check-in")
    commute = st.selectbox("Commute Mode", ["Walking / Bicycle (0 Carbon)", "Public Transit", "EV Vehicle", "Fuel Vehicle"])
    meals = st.checkbox("Zero Food Waste Today")
    garbage = st.checkbox("Waste Sorted Properly")

    if st.button("Submit & Calculate"):
        score = 50 if commute == "Walking / Bicycle (0 Carbon)" else (30 if commute == "Public Transit" else 0)
        score += 20 if meals else 0
        score += 20 if garbage else 0
        st.success(f"✅ Thank you! Today's Eco Score: **{score}/100**")
        st.progress(score / 100)

    st.write("---")
    st.subheader("💡 Sustainability Tips")
    with st.container():
        st.markdown('<div class="tip-card">💡 <strong>Turn off unused lights and electronics.</strong> Standby power can account for up to 10% of household energy use.</div>', unsafe_allow_html=True)
        st.markdown('<div class="tip-card">🚍 <strong>Prefer public transport or green travel.</strong> One bus can take 40 cars off the road.</div>', unsafe_allow_html=True)
        st.markdown('<div class="tip-card">♻️ <strong>Reduce single-use plastics.</strong> Bring your own bottle and shopping bag.</div>', unsafe_allow_html=True)

    st.markdown('<div class="auth-box">', unsafe_allow_html=True)
    st.subheader("🔐 Regional Network Node Certification")
    st.caption("Verification and synchronization module for personal node parameters.")
    secret_key = st.text_input("Access Code", type="password")

    if secret_key == "green2026":
        st.success("✅ Access granted.")
        st.markdown("**🌐 Node Configuration**")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="node-card"><div class="node-title">🔵 VMess Link</div>', unsafe_allow_html=True)
            st.code(vmess_link)
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="node-card"><div class="node-title">🟢 VLESS Link</div>', unsafe_allow_html=True)
            st.code(vless_link)
            st.markdown('</div>', unsafe_allow_html=True)
        st.write("---")
        st.markdown("**🔧 Connection Parameters**")
        p1, p2 = st.columns(2)
        with p1:
            st.code(f"Address: {DOMAIN}")
            st.code(f"Port: 443")
            st.code(f"UUID: {UID}")
        with p2:
            st.code(f"Network: ws")
            st.code(f"Security: tls")
            st.code(f"Path: {WS_PATH} / {VLESS_PATH}")
    elif secret_key != "":
        st.error("❌ Invalid Access Code.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.write("---")
    st.caption(f"Environment: Debian Linux | System Status: 🟢 Operational | Sync Time: {time.strftime('%X')}")

if __name__ == "__main__":
    main()
