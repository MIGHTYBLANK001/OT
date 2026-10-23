
import os
import json
import time
import uuid
import hashlib
import shutil
import tarfile
import platform
import subprocess
import urllib.request
import signal
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
            raise RuntimeError("sing-box binary not found")
        src = tar.extractfile(member)
        if src is None:
            raise RuntimeError("Unable to extract sing-box")
        with src, open(destination, "wb") as dst:
            shutil.copyfileobj(src, dst)
    destination.chmod(0o755)


def find_process(binary):
    target = str(binary).encode()
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            args = (entry / "cmdline").read_bytes().split(b"\0")
            if args and args[0] == target:
                return int(entry.name)
        except (OSError, ValueError):
            pass
    return None


def stop_process(pid):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(20):
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def log_tail(name):
    p = BASE / name
    return p.read_text(errors="replace")[-3000:] if p.exists() else "No log available"


def start_process(binary, args, log_name):
    with open(BASE / log_name, "ab", buffering=0) as log:
        proc = subprocess.Popen(
            [str(binary), *args],
            cwd=BASE,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    time.sleep(1)
    if proc.poll() is not None:
        raise RuntimeError(f"{binary.name} failed:\n{log_tail(log_name)}")
    return proc.pid


def ensure_process(binary, args, log_name, restart=False):
    pid = find_process(binary)
    if pid and restart:
        stop_process(pid)
        pid = None
    if pid:
        return pid
    return start_process(binary, args, log_name)


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
            "multiplex": {"enabled": True, "padding": False},
        }],
        "outbounds": [{"type": "direct", "tag": "direct"}],
    }

    raw = json.dumps(config, indent=2)
    config_hash = hashlib.sha256(raw.encode()).hexdigest()
    stamp = BASE / "sb.sha256"
    restart = not stamp.exists() or stamp.read_text().strip() != config_hash
    (BASE / "sb.json").write_text(raw, encoding="utf-8")

    check = subprocess.run(
        [str(sb), "check", "-c", "sb.json"],
        cwd=BASE, capture_output=True, text=True, timeout=15,
    )
    if check.returncode:
        raise RuntimeError(f"sing-box config error:\n{check.stdout}\n{check.stderr}")

    sb_pid = ensure_process(
        sb, ["run", "-c", "sb.json"], "sing-box.log", restart
    )
    stamp.write_text(config_hash)

    cf_pid = ensure_process(
        cf,
        ["tunnel", "--no-autoupdate", "--protocol", "auto", "run", "--token", TOKEN],
        "cloudflared.log",
    )
    return sb_pid, cf_pid


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
    st.title("EcoTracker")
    st.caption("Small Actions. Lasting Impact.")
    st.markdown(
        "Track sustainable habits, reduce waste, and make everyday choices "
        "that are better for the planet."
    )

    try:
        sb_pid, cf_pid = setup()
        st.success("Services are running")
    except Exception as e:
        st.error(f"Service startup failed: {e}")
        with st.expander("Diagnostics"):
            st.code(log_tail("sing-box.log"))
            st.code(log_tail("cloudflared.log"))

    st.subheader("Your Sustainability Snapshot")
    a, b, c = st.columns(3)
    a.metric("Green Travel", "42.5 km")
    b.metric("Water Saved", "180 L")
    c.metric("Carbon Reduced", "12.8 kg")

    with st.container(border=True):
        st.subheader("Daily Eco Check-in")
        commute = st.selectbox(
            "How did you travel today?",
            ["Walking / Cycling", "Public Transit", "Electric Vehicle", "Fuel Vehicle"],
        )
        meals = st.checkbox("I avoided food waste")
        waste = st.checkbox("I sorted waste correctly")
        reuse = st.checkbox("I used reusable bags or bottles")
        energy = st.checkbox("I switched off unused devices")

        if st.button("Calculate Eco Score", use_container_width=True):
            score = {
                "Walking / Cycling": 40,
                "Public Transit": 30,
                "Electric Vehicle": 20,
                "Fuel Vehicle": 0,
            }[commute]
            score = min(100, score + 15 * sum([meals, waste, reuse, energy]))
            st.metric("Today's Eco Score", f"{score}/100")
            st.progress(score / 100)
            st.caption("A simple habit score, not a measured carbon footprint.")

    with st.container(border=True):
        st.subheader("Greener Living")
        st.markdown("""
**Transport**
- Walk, cycle, or take public transit for short trips.
- Combine errands to reduce unnecessary journeys.

**Food**
- Plan meals and store food properly.
- Use leftovers and choose seasonal produce.

**Water and Energy**
- Take shorter showers and fix leaking taps.
- Switch off idle electronics and choose efficient appliances.

**Waste and Nature**
- Reuse, repair, and recycle whenever possible.
- Avoid single-use plastics and protect local green spaces.
""")

    with st.expander("About Sustainability"):
        st.markdown("""
- **Climate:** Cleaner transport and lower energy use can reduce emissions.
- **Resources:** Reuse and repair conserve materials.
- **Biodiversity:** Less pollution helps protect ecosystems.
- **Community:** Small, consistent habits can inspire others.
""")

    with st.expander("Admin"):
        st.caption("Restricted connection settings")
        with st.form("admin_login"):
            code = st.text_input("Access Code", type="password")
            login = st.form_submit_button("Verify")
        if login:
            st.session_state["admin_ok"] = bool(code and code == MEMBER_CODE)
            st.session_state["show_node"] = False
            if not st.session_state["admin_ok"]:
                st.error("Invalid access code")

        if st.session_state.get("admin_ok"):
            st.success("Access granted")
            if st.button("◉", help="Show or hide connection details"):
                st.session_state["show_node"] = not st.session_state.get("show_node", False)
            if st.session_state.get("show_node"):
                st.code(node_link(), language=None)
                st.code(
                    f"Address: {DOMAIN}\nPort: 443\nUUID: {UID}\n"
                    f"Network: WebSocket\nSecurity: TLS\nPath: {WS_PATH}\n"
                    "Server Multiplex: Enabled",
                    language=None,
                )

    st.divider()
    st.caption(f"EcoTracker | {time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
