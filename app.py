import os
import json
import time
import uuid
import shutil
import tarfile
import platform
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlencode
import streamlit as st

BASE = Path("/tmp/.agsb_stable")
PORT = 49999


def secret(key, default=""):
    return str(st.secrets.get(key, default)).strip()


UID = secret("UUID")
TOKEN = secret("TOKEN")
DOMAIN = secret("DOMAIN").removeprefix("https://").removeprefix("http://").rstrip("/")
MEMBER_CODE = secret("MEMBER_CODE", "green2026")
WS_PATH = "/" + UID[:8]


def download(url, dst, minimum=1_000_000):
    tmp = Path(str(dst) + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EcoTracker"})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        if tmp.stat().st_size < minimum:
            raise RuntimeError("Downloaded file is too small")
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def latest(owner, repo):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
        headers={"User-Agent": "EcoTracker"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)["tag_name"].lstrip("v")


def extract_binary(archive, destination):
    with tarfile.open(archive, "r:gz") as tar:
        member = next(
            (m for m in tar.getmembers()
             if Path(m.name).name == "sing-box" and m.isfile()),
            None,
        )
        if member is None:
            raise RuntimeError("sing-box binary not found in release archive")
        src = tar.extractfile(member)
        if src is None:
            raise RuntimeError("Unable to extract sing-box")
        with src, open(destination, "wb") as dst:
            shutil.copyfileobj(src, dst)
    destination.chmod(0o755)


def run_logged(cmd, log_name):
    with open(BASE / log_name, "ab", buffering=0) as log:
        return subprocess.Popen(
            cmd, cwd=BASE, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def log_tail(name):
    path = BASE / name
    return path.read_text(errors="replace")[-3000:] if path.exists() else "No log available"


def setup():
    if not UID or not TOKEN or not DOMAIN:
        raise RuntimeError("Configure UUID, TOKEN and DOMAIN in Streamlit Secrets")
    try:
        uuid.UUID(UID)
    except ValueError:
        raise RuntimeError("Invalid UUID")

    BASE.mkdir(parents=True, exist_ok=True)
    sb, cf = BASE / "sing-box", BASE / "cloudflared"
    arch = {
        "x86_64": "amd64", "amd64": "amd64",
        "aarch64": "arm64", "arm64": "arm64",
    }.get(platform.machine().lower())
    if not arch:
        raise RuntimeError("Unsupported CPU architecture")

    if not sb.exists() or sb.stat().st_size < 1_000_000:
        ver = latest("SagerNet", "sing-box")
        archive = BASE / "sing-box.tar.gz"
        download(
            f"https://github.com/SagerNet/sing-box/releases/download/"
            f"v{ver}/sing-box-{ver}-linux-{arch}.tar.gz",
            archive,
        )
        extract_binary(archive, sb)
        archive.unlink(missing_ok=True)

    if not cf.exists() or cf.stat().st_size < 1_000_000:
        ver = latest("cloudflare", "cloudflared")
        download(
            f"https://github.com/cloudflare/cloudflared/releases/download/"
            f"{ver}/cloudflared-linux-{arch}", cf,
        )
        cf.chmod(0o755)

    config = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vless",
            "tag": "vless-in",
            "listen": "127.0.0.1",
            "listen_port": PORT,
            "users": [{"uuid": UID}],
            "transport": {"type": "ws", "path": WS_PATH},
            "multiplex": {
                "enabled": True,
                "padding": False,
            },
        }],
        "outbounds": [{"type": "direct", "tag": "direct"}],
    }
    (BASE / "sb.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    result = subprocess.run(
        [str(sb), "check", "-c", "sb.json"],
        cwd=BASE, capture_output=True, text=True, timeout=15,
    )
    if result.returncode:
        raise RuntimeError(f"sing-box config error:\n{result.stdout}\n{result.stderr}")

    sb_proc = run_logged([str(sb), "run", "-c", "sb.json"], "sing-box.log")
    time.sleep(1)
    if sb_proc.poll() is not None:
        raise RuntimeError("sing-box failed:\n" + log_tail("sing-box.log"))

    cf_proc = run_logged([
        str(cf), "tunnel", "--no-autoupdate",
        "--protocol", "auto", "run", "--token", TOKEN,
    ], "cloudflared.log")
    time.sleep(2)
    if cf_proc.poll() is not None:
        raise RuntimeError("cloudflared failed:\n" + log_tail("cloudflared.log"))

    return sb_proc, cf_proc


@st.cache_resource
def services():
    return setup()


def node_link():
    params = urlencode({
        "encryption": "none",
        "security": "tls",
        "sni": DOMAIN,
        "type": "ws",
        "host": DOMAIN,
        "path": WS_PATH,
    })
    return f"vless://{UID}@{DOMAIN}:443?{params}#EcoTracker"


def main():
    st.set_page_config(page_title="EcoTracker", page_icon="🌱", layout="centered")
    st.markdown("""
    <style>
    #MainMenu,footer{visibility:hidden}
    .block-container{max-width:760px;padding-top:1.5rem;padding-bottom:2rem}
    .hero{background:linear-gradient(135deg,#2e7d32,#123b24);color:white;
    padding:26px 20px;border-radius:16px;text-align:center;margin-bottom:20px}
    .hero h1{margin:0;font-size:2.1rem}
    .hero p{margin:8px 0 0;color:#e8f5e9}
    .eco-tip{background:#edf7ed;padding:14px;border-radius:10px;margin:8px 0}
    </style>
    <div class="hero"><h1>🌱 EcoTracker</h1>
    <p>Small Actions. Lasting Impact.</p>
    <p>Track your habits, reduce waste and build a greener future.</p></div>
    """, unsafe_allow_html=True)

    try:
        sb_proc, cf_proc = services()
        if sb_proc.poll() is not None or cf_proc.poll() is not None:
            st.error("A service process has stopped.")
            with st.expander("View diagnostic logs"):
                st.code("=== sing-box ===\n" + log_tail("sing-box.log"))
                st.code("=== cloudflared ===\n" + log_tail("cloudflared.log"))
        else:
            st.caption("Service processes are running. End-to-end connectivity is not verified.")
    except Exception as e:
        st.error(f"Service startup failed: {e}")

    st.subheader("🌍 Your Sustainability Snapshot")
    a, b, c = st.columns(3)
    a.metric("Green Travel", "42.5 km")
    b.metric("Water Saved", "180 L")
    c.metric("Carbon Reduced", "12.8 kg")

    with st.container(border=True):
        st.subheader("📊 Daily Eco Check-in")
        commute = st.selectbox(
            "How did you travel today?",
            ["Walking / Cycling", "Public Transit", "Electric Vehicle", "Fuel Vehicle"],
        )
        meals = st.checkbox("I avoided food waste today")
        garbage = st.checkbox("I sorted my waste correctly")
        reusable = st.checkbox("I used reusable bags or bottles")
        energy = st.checkbox("I switched off unused lights and devices")

        if st.button("Calculate My Eco Score", use_container_width=True):
            score = {
                "Walking / Cycling": 40,
                "Public Transit": 30,
                "Electric Vehicle": 20,
                "Fuel Vehicle": 0,
            }[commute]
            score += 15 * meals + 15 * garbage + 15 * reusable + 15 * energy
            score = min(score, 100)
            st.success(f"Your Eco Score: {score}/100")
            st.progress(score / 100)
            st.caption(
                "This is a simple habit-based score, not a measured carbon footprint."
            )

    with st.container(border=True):
        st.subheader("💡 Greener Living Tips")
        st.markdown("""
        <div class="eco-tip">🚲 <b>Choose greener transport</b><br>
        Walk, cycle or use public transit for short journeys.</div>
        <div class="eco-tip">🥗 <b>Make food count</b><br>
        Plan meals, store food properly and use leftovers.</div>
        <div class="eco-tip">💧 <b>Save every drop</b><br>
        Take shorter showers and fix leaking taps.</div>
        <div class="eco-tip">🔌 <b>Use energy wisely</b><br>
        Turn off idle devices and choose efficient appliances.</div>
        <div class="eco-tip">♻️ <b>Reduce and reuse</b><br>
        Avoid disposable products and sort recyclables correctly.</div>
        """, unsafe_allow_html=True)

    with st.expander("🌳 Why Small Actions Matter"):
        st.markdown("""
        - **Climate:** Lower energy use and cleaner transport can reduce emissions.
        - **Resources:** Reuse and repair help conserve raw materials.
        - **Nature:** Less waste means less pollution in ecosystems.
        - **Community:** Sustainable habits are easier to maintain when shared.
        """)

    with st.container(border=True):
        st.subheader("🔐 Member Area")
        code = st.text_input("Access Code", type="password")
        if st.button("Verify Access", use_container_width=True):
            st.session_state["member_verified"] = bool(code and code == MEMBER_CODE)
            st.session_state["show_node"] = False
            if not st.session_state["member_verified"]:
                st.error("Invalid access code.")

        if st.session_state.get("member_verified"):
            st.success("Access granted.")
            if st.button("👁 Show Connection Details" if not st.session_state.get("show_node") else "🙈 Hide Connection Details"):
                st.session_state["show_node"] = not st.session_state.get("show_node", False)

            if st.session_state.get("show_node"):
                st.code(node_link(), language=None)
                st.caption("Connection Parameters")
                st.code(
                    f"Address: {DOMAIN}\nPort: 443\nUUID: {UID}\n"
                    f"Network: WebSocket\nSecurity: TLS\nPath: {WS_PATH}\n"
                    f"Server Multiplex: Enabled",
                    language=None,
                )

    st.divider()
    st.caption(f"EcoTracker · {time.strftime('%Y-%m-%d %H:%M:%S')} · Make every action count.")


if __name__ == "__main__":
    main()
