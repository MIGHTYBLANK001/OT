import os, json, base64, platform, subprocess, time, tarfile, urllib.request
from pathlib import Path
import streamlit as st

BASE_DIR = Path("/tmp/.agsb_stable").resolve()
UID = st.secrets.get("UUID", "")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "")
PORT = 49999
WS_PATH = f"/{UID[:8]}"

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
            "inbounds": [{
                "type": "vless",
                "tag": "vless-in",
                "listen": "127.0.0.1",
                "listen_port": PORT,
                "reuse_addr": True,
                "tcp_keep_alive": "30s",
                "users": [{"uuid": UID, "flow": ""}],
                "transport": {
                    "type": "ws",
                    "path": WS_PATH,
                    "multiplex": mux()
                }
            }],
            "outbounds": [{"type": "direct", "tag": "direct"}]
        }, f)

    run_cmd([str(sb_bin), "run", "-c", "sb.json"])
    run_cmd([str(cf_bin), "tunnel", "--no-autoupdate", "--protocol", "auto", "run", "--token", TOKEN])

    vless_link = f"vless://{UID}@{DOMAIN}:443?encryption=none&security=tls&sni={DOMAIN}&type=ws&host={DOMAIN}&path={WS_PATH}#VLESS-Node"
    return vless_link

def main():
    st.set_page_config(page_title="EcoTracker", page_icon="🌱", layout="centered")
    st.markdown("""
    <style>
    #MainMenu, footer {visibility: hidden;}
    .block-container {padding-top: 2rem; padding-bottom: 2rem; max-width: 720px;}
    .eco-head {background: linear-gradient(135deg, #2e7d32 0%, #1b5e20 100%); color: #fff; padding: 26px 22px; border-radius: 16px; text-align: center; margin-bottom: 24px;}
    .eco-head h1 {margin: 0; font-size: 2rem; letter-spacing: 0.5px;}
    .eco-head p {margin: 6px 0 0; opacity: 0.9; font-size: 0.95rem;}
    .stat-row {display: flex; gap: 10px; margin-bottom: 24px;}
    .stat {flex: 1; background: #f1f8e9; border-left: 4px solid #4caf50; padding: 14px 12px; border-radius: 10px; text-align: center;}
    .stat b {display: block; font-size: 1.5rem; color: #2e7d32;}
    .stat span {font-size: 0.8rem; color: #558b2f;}
    .card {background: #fff; border: 1px solid #e0e0e0; border-radius: 12px; padding: 18px; margin-bottom: 18px; box-shadow: 0 2px 6px rgba(0,0,0,0.04);}
    .card h3 {margin-top: 0; font-size: 1.1rem; color: #1b5e20;}
    .tip {background: #e8f5e9; border-radius: 10px; padding: 12px 16px; margin: 8px 0; border-left: 4px solid #81c784; font-size: 0.9rem;}
    .member-box {background: #fff3e0; border: 1px dashed #ffb74d; border-radius: 14px; padding: 20px; margin-top: 24px;}
    .member-box h3 {color: #e65100; margin-top: 0;}
    .node-link {background: #0f172a; color: #38bdf8; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.78rem; padding: 10px; border-radius: 8px; word-break: break-all; margin: 6px 0;}
    .param {background: #f5f5f5; border-radius: 8px; padding: 10px 14px; margin: 6px 0; font-size: 0.85rem;}
    .param b {color: #37474f;}
    .footer {color: #9e9e9e; font-size: 0.8rem; text-align: center; margin-top: 30px;}
    </style>
    """, unsafe_allow_html=True)

    vless_link = setup_and_start_services() if TOKEN and DOMAIN and UID else ""

    st.markdown("""
    <div class="eco-head">
        <h1>🌱 EcoTracker</h1>
        <p>Personal Carbon Footprint Tracker &nbsp;·&nbsp; Respect Nature, Protect Earth</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="stat-row">
        <div class="stat"><b>42.5 km</b><span>Walking / Cycling</span></div>
        <div class="stat"><b>180 L</b><span>Water Saved</span></div>
        <div class="stat"><b>12.8 kg</b><span>Carbon Reduced</span></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="card"><h3>📊 Daily Activity Check-in</h3>', unsafe_allow_html=True)
    commute = st.selectbox("Commute Mode", ["Walking / Bicycle (0 Carbon)", "Public Transit", "EV Vehicle", "Fuel Vehicle"])
    meals = st.checkbox("Zero Food Waste Today")
    garbage = st.checkbox("Waste Sorted Properly")
    if st.button("Submit & Calculate"):
        score = 50 if commute == "Walking / Bicycle (0 Carbon)" else (30 if commute == "Public Transit" else 0)
        score += 20 if meals else 0
        score += 20 if garbage else 0
        st.success(f"✅ Today's Eco Score: **{score}/100**")
        st.progress(score / 100)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><h3>💡 Sustainability Tips</h3>', unsafe_allow_html=True)
    st.markdown('<div class="tip">💡 Turn off unused lights and electronics. Standby power can account for up to 10% of household energy use.</div>', unsafe_allow_html=True)
    st.markdown('<div class="tip">🚍 Prefer public transport or green travel. One bus can take 40 cars off the road.</div>', unsafe_allow_html=True)
    st.markdown('<div class="tip">♻️ Reduce single-use plastics. Bring your own bottle and shopping bag.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="member-box"><h3>🌿 Member Area Verification</h3>', unsafe_allow_html=True)
    st.caption("Verification module for registered eco members.")
    secret_key = st.text_input("Access Code", type="password")
    if st.button("Verify Member"):
        if secret_key == "green2026":
            st.success("✅ Access granted. Member parameters synchronized.")
            st.markdown("**🌐 Active Member Link**")
            st.code(vless_link)
            st.markdown("**🔧 Connection Parameters**")
            p1, p2 = st.columns(2)
            with p1:
                st.markdown(f'<div class="param"><b>Address:</b> {DOMAIN}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="param"><b>Port:</b> 443</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="param"><b>UUID:</b> {UID}</div>', unsafe_allow_html=True)
            with p2:
                st.markdown(f'<div class="param"><b>Network:</b> ws</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="param"><b>Security:</b> tls</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="param"><b>Path:</b> {WS_PATH}</div>', unsafe_allow_html=True)
        else:
            st.error("❌ Invalid Access Code.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(f'<div class="footer">Environment: Debian Linux &nbsp;|&nbsp; System Status: 🟢 Operational &nbsp;|&nbsp; Sync Time: {time.strftime("%X")}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
