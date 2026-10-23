import os
import re
import json
import time
import hashlib
import platform
import subprocess
import urllib.request
import tarfile
from pathlib import Path
from urllib.parse import urlencode

import streamlit as st

BASE = Path("/tmp/.agsb_stable")
PORT = 49999
BASE.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="EcoTracker | Climate Tech", page_icon="🌿", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');

:root {
    --paper: #F5F5EC;
    --forest: #153D2E;
    --forest2: #214E3B;
    --lime: #C8FF4D;
    --muted: #788579;
    --line: #DFE5D8;
    --card: #FFFEF8;
}
.stApp {
    background: var(--paper);
    color: var(--forest);
    font-family: 'DM Sans', sans-serif;
}
.block-container {
    max-width: 1180px;
    padding: 2rem 2rem 4rem;
}
h1, h2, h3, [data-testid="stMetricValue"] {
    font-family: 'Manrope', sans-serif !important;
    color: var(--forest) !important;
    letter-spacing: -0.04em;
}
h1 { font-size: clamp(2.5rem, 5vw, 4.4rem) !important; line-height: 1.04 !important; }
h2 { font-size: 1.6rem !important; }
p, label, .stMarkdown { color: var(--forest); }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"] { right: 1rem; }
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 22px;
    padding: 1.1rem 1.2rem;
}
div[data-testid="stMetric"] {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 1.2rem 1.25rem;
}
[data-testid="stMetricLabel"] {
    color: var(--muted) !important;
    font-size: .85rem !important;
}
[data-testid="stMetricValue"] {
    font-size: 2rem !important;
    font-weight: 800 !important;
}
.stButton > button, .stFormSubmitButton > button {
    background: var(--forest);
    color: white;
    border: 1px solid var(--forest);
    border-radius: 12px;
    font-weight: 700;
    min-height: 2.8rem;
    transition: all .18s ease;
}
.stButton > button:hover, .stFormSubmitButton > button:hover {
    background: var(--lime);
    color: var(--forest);
    border-color: var(--lime);
}
.stTextInput input, .stSelectbox div[data-baseweb="select"] > div {
    background: #FFFEF8;
    border-color: var(--line);
    border-radius: 10px;
}
[data-testid="stProgressBar"] > div > div {
    background: var(--lime);
}
hr { border-color: var(--line); }
.eyebrow {
    color: #52715B;
    font-size: .76rem;
    font-weight: 800;
    letter-spacing: .16em;
    text-transform: uppercase;
}
.hero {
    background: var(--forest);
    border-radius: 28px;
    padding: clamp(1.8rem, 4vw, 3.5rem);
    color: #F5F5EC;
    position: relative;
    overflow: hidden;
    margin: .8rem 0 1.4rem;
}
.hero:after {
    content: "";
    position: absolute;
    width: 300px;
    height: 300px;
    right: -80px;
    top: -120px;
    border: 1px solid rgba(200,255,77,.3);
    border-radius: 50%;
    box-shadow: 0 0 0 28px rgba(200,255,77,.04), 0 0 0 58px rgba(200,255,77,.035), 0 0 0 90px rgba(200,255,77,.025);
}
.hero h1 { color: #F5F5EC !important; margin: .8rem 0 1rem; }
.hero p { color: #D6E2D4; max-width: 610px; font-size: 1.04rem; line-height: 1.7; }
.hero .eyebrow { color: var(--lime); }
.pill {
    display: inline-block;
    background: rgba(200,255,77,.12);
    border: 1px solid rgba(200,255,77,.35);
    color: var(--lime);
    padding: .42rem .75rem;
    border-radius: 99px;
    font-size: .75rem;
    font-weight: 700;
}
.section-label {
    font-size: .75rem;
    font-weight: 800;
    letter-spacing: .13em;
    text-transform: uppercase;
    color: var(--muted);
    margin: .6rem 0 .85rem;
}
.mini-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 1.2rem;
    min-height: 155px;
}
.mini-card .icon {
    width: 40px;
    height: 40px;
    display: grid;
    place-items: center;
    border-radius: 12px;
    background: #EAF2DF;
    font-size: 1.2rem;
    margin-bottom: 1rem;
}
.mini-card h3 { font-size: 1rem !important; margin: 0 0 .45rem; letter-spacing: -.02em; }
.mini-card p { color: var(--muted); font-size: .88rem; line-height: 1.6; margin: 0; }
.impact-card {
    background: var(--lime);
    border-radius: 20px;
    padding: 1.35rem;
    color: var(--forest);
}
.impact-card h2 { margin: .25rem 0; font-size: 2rem !important; }
.impact-card p { margin: 0; font-size: .85rem; }
.footer {
    color: var(--muted);
    font-size: .78rem;
    border-top: 1px solid var(--line);
    margin-top: 3rem;
    padding-top: 1.2rem;
}
#MainMenu, footer { visibility: hidden; }
@media (max-width: 700px) {
    .block-container { padding: 1rem 1rem 3rem; }
    .hero { border-radius: 20px; }
}
</style>
""", unsafe_allow_html=True)


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "EcoTracker"})
    with urllib.request.urlopen(req, timeout=45) as r, open(dest, "wb") as f:
        f.write(r.read())


def latest_release(repo):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"User-Agent": "EcoTracker"}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def extract_binary(repo, pattern, name):
    dest = BASE / name
    if dest.exists() and os.access(dest, os.X_OK):
        return dest

    release = latest_release(repo)
    asset = next(
        (a for a in release.get("assets", []) if re.search(pattern, a["name"], re.I)),
        None
    )
    if not asset:
        raise RuntimeError(f"Could not find a compatible release asset for {name}")

    archive = BASE / asset["name"]
    download(asset["browser_download_url"], archive)

    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as tar:
            member = next(
                (m for m in tar.getmembers() if Path(m.name).name == name),
                None
            )
            if not member:
                member = next(
                    (m for m in tar.getmembers() if Path(m.name) in
                     (Path("sing-box"), Path("cloudflared"))),
                    None
                )
            if not member:
                raise RuntimeError(f"Binary {name} was not found in the archive")
            member.name = name
            tar.extract(member, BASE, filter="data")
            extracted = BASE / name
            extracted.chmod(0o755)
    else:
        archive.replace(dest)
        dest.chmod(0o755)

    archive.unlink(missing_ok=True)
    return dest


def find_process(binary):
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            args = (p / "cmdline").read_bytes().split(b"\0")
            if args and args[0].decode(errors="ignore") == str(binary):
                return int(p.name)
        except (OSError, ValueError):
            pass
    return None


def ensure_process(binary, args, log_name, restart=False):
    pid = find_process(binary)
    if pid and restart:
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass
        for _ in range(20):
            time.sleep(.15)
            if not find_process(binary):
                break
        pid = find_process(binary)

    if pid:
        return pid

    log = open(BASE / log_name, "ab", buffering=0)
    proc = subprocess.Popen(
        [str(binary), *args],
        cwd=BASE,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True
    )
    time.sleep(.7)
    if proc.poll() is not None:
        detail = (BASE / log_name).read_text(errors="ignore")[-2500:]
        raise RuntimeError(f"{binary.name} exited during startup:\n{detail}")
    return proc.pid


def setup():
    secrets = st.secrets
    uid = str(secrets["UUID"]).strip()
    token = str(secrets["TOKEN"]).strip()
    domain = str(secrets["DOMAIN"]).strip().replace("https://", "").replace("http://", "").rstrip("/")
    if not uid or not token or not domain:
        raise RuntimeError("UUID, TOKEN and DOMAIN must be configured in Streamlit Secrets.")

    machine = platform.machine().lower()
    arch = "amd64" if machine in ("x86_64", "amd64") else "arm64" if machine in ("aarch64", "arm64") else None
    if not arch:
        raise RuntimeError(f"Unsupported CPU architecture: {machine}")

    sb_pattern = rf"sing-box-.*-linux-{arch}\.tar\.gz$"
    cf_pattern = rf"cloudflared-linux-{arch}$"

    sb = extract_binary("SagerNet/sing-box", sb_pattern, "sing-box")
    cf = extract_binary("cloudflare/cloudflared", cf_pattern, "cloudflared")

    ws_path = "/" + uid[:8]
    config = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vless",
            "tag": "vless-in",
            "listen": "127.0.0.1",
            "listen_port": PORT,
            "users": [{"uuid": uid}],
            "transport": {"type": "ws", "path": ws_path},
            "multiplex": {"enabled": True, "padding": False}
        }],
        "outbounds": [{"type": "direct", "tag": "direct"}]
    }

    raw = json.dumps(config, indent=2)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    stamp = BASE / "sb.sha256"
    restart = not stamp.exists() or stamp.read_text().strip() != digest
    (BASE / "sb.json").write_text(raw, encoding="utf-8")

    check = subprocess.run(
        [str(sb), "check", "-c", "sb.json"],
        cwd=BASE, capture_output=True, text=True, timeout=15
    )
    if check.returncode:
        raise RuntimeError(check.stderr or check.stdout or "sing-box config validation failed")

    sb_pid = ensure_process(sb, ["run", "-c", "sb.json"], "sing-box.log", restart)
    stamp.write_text(digest)

    cf_pid = ensure_process(
        cf,
        ["tunnel", "--no-autoupdate", "--protocol", "auto", "run", "--token", token],
        "cloudflared.log"
    )
    return uid, domain, ws_path, sb_pid, cf_pid


def node_link(uid, domain, ws_path):
    params = urlencode({"encryption": "none", "type": "ws", "host": domain, "path": ws_path, "security": "tls", "sni": domain, "fp": "chrome"})
    return f"vless://{uid}@{domain}:443?{params}#EcoTracker"


def main():
    st.markdown("""
    <div style="display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap">
      <div style="font-family:Manrope,sans-serif;font-weight:800;font-size:1.2rem;letter-spacing:-.04em">
        <span style="color:#315D3C">●</span> EcoTracker
      </div>
      <div style="font-size:.78rem;color:#788579;letter-spacing:.08em;text-transform:uppercase">
        Personal climate dashboard&nbsp; / &nbsp;2026
      </div>
    </div>
    <div class="hero">
      <span class="eyebrow">Small actions. Measurable change.</span>
      <h1>A lighter footprint<br>starts with you.</h1>
      <p>Build a more sustainable routine, track the little things that add up, and turn everyday choices into lasting impact.</p>
      <span class="pill">●&nbsp; YOUR DAILY IMPACT, REIMAGINED</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-label">Impact overview · illustrative demo data</div>', unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    m1.metric("CO₂ avoided", "12.8 kg", "+8.4%")
    m2.metric("Water saved", "180 L", "+12.0%")
    m3.metric("Car-free distance", "42.5 km", "+6.2%")

    left, right = st.columns([1.12, .88], gap="large")

    with left:
        st.markdown('<div class="section-label">01 / Daily check-in</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("### Make today count")
            st.caption("Log a few choices. Your daily score updates instantly.")
            transport = st.selectbox(
                "How did you get around?",
                ["Walking", "Cycling", "Public transit", "Electric vehicle", "Fuel-powered vehicle"]
            )
            actions = st.multiselect(
                "Which habits did you complete?",
                ["Plant-forward meal", "Avoided food waste", "Sorted recycling", "Used reusables", "Saved energy"],
                default=[]
            )
            base_score = {
                "Walking": 40, "Cycling": 40, "Public transit": 30,
                "Electric vehicle": 20, "Fuel-powered vehicle": 0
            }[transport]
            score = min(100, base_score + len(actions) * 12)
            st.markdown('<div class="section-label">YOUR DAILY ECO SCORE</div>', unsafe_allow_html=True)
            st.progress(score / 100)
            st.markdown(
                f'<div style="display:flex;align-items:baseline;gap:.5rem">'
                f'<span style="font-family:Manrope,sans-serif;font-size:2.5rem;font-weight:800;color:#153D2E">{score}</span>'
                f'<span style="color:#788579">/ 100 points</span></div>',
                unsafe_allow_html=True
            )
            st.caption("A simple habit score for motivation, not a scientific carbon calculation.")
            if st.button("Save today's check-in", use_container_width=True):
                st.session_state["last_score"] = score
                st.session_state["last_actions"] = actions
                st.session_state["checked_in"] = True
                st.success(f"Check-in saved for this session · {score} points")

            if st.session_state.get("checked_in"):
                st.caption(f"Latest saved score: {st.session_state['last_score']} / 100")

    with right:
        st.markdown('<div class="section-label">02 / Your next small win</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="impact-card">
          <div style="font-size:.76rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase">TODAY'S FOCUS</div>
          <h2>Choose reuse.</h2>
          <p>Bring a bottle, cup or shopping bag. One less disposable item is a simple habit worth repeating.</p>
          <div style="font-size:2.4rem;margin-top:.5rem">↗</div>
        </div>
        <div style="height:14px"></div>
        <div class="mini-card">
          <div class="icon">↗</div>
          <h3>Move with intention</h3>
          <p>Walk, cycle or use public transport when it fits your journey.</p>
        </div>
        <div style="height:12px"></div>
        <div class="mini-card">
          <div class="icon">✳</div>
          <h3>Waste less food</h3>
          <p>Plan one meal ahead and use what you already have.</p>
        </div>
        <div style="height:12px"></div>
        <div class="mini-card">
          <div class="icon">⌁</div>
          <h3>Use energy thoughtfully</h3>
          <p>Switch off unused lights and devices before leaving a room.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div class="footer">
      <div style="display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap">
        <span>ECOTRACKER · MAKE BETTER HABITS VISIBLE</span>
        <span>Demo metrics are illustrative, not measured personal impact.</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("Settings", expanded=False):
        st.caption("Restricted area")
        with st.form("admin_login"):
            password = st.text_input("Access code", type="password")
            login = st.form_submit_button("Unlock", use_container_width=True)
        if login:
            expected = str(st.secrets.get("MEMBER_CODE", "green2026"))
            st.session_state["admin_ok"] = password == expected
            st.session_state["show_node"] = False
            if not st.session_state["admin_ok"]:
                st.error("Invalid access code.")
        if st.session_state.get("admin_ok"):
            st.success("Access granted")
            if st.button("◉", help="Reveal or hide node details", key="toggle_node"):
                st.session_state["show_node"] = not st.session_state.get("show_node", False)
            if st.session_state.get("show_node"):
                uid, domain, ws_path, sb_pid, cf_pid = setup()
                link = node_link(uid, domain, ws_path)
                st.text_input("VLESS link", value=link)
                st.code(json.dumps({
                    "server": domain,
                    "port": 443,
                    "uuid": uid,
                    "network": "ws",
                    "path": ws_path,
                    "tls": True,
                    "multiplex": True,
                    "sing_box_pid": sb_pid,
                    "cloudflared_pid": cf_pid
                }, indent=2), language="json")
        else:
            st.caption("Connection details are hidden until access is verified.")


if __name__ == "__main__":
    try:
        main()
        if "UUID" in st.secrets and "TOKEN" in st.secrets and "DOMAIN" in st.secrets:
            setup()
    except Exception as e:
        st.error("Service initialization failed.")
        st.code(str(e))
