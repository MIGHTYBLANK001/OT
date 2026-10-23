
import hashlib, json, os, platform, re, subprocess, tarfile, time, urllib.request
from pathlib import Path
from urllib.parse import urlencode
import streamlit as st

BASE, PORT = Path("/tmp/.agsb_stable"), 49999
BASE.mkdir(exist_ok=True)

st.set_page_config(page_title="EcoTracker", page_icon="🌿", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;600;700;800&display=swap');
:root{--bg:#F5F5EC;--green:#153D2E;--lime:#C8FF4D;--muted:#788579;--line:#DFE5D8;--card:#FFFEF8}
.stApp{background:var(--bg);color:var(--green);font-family:'DM Sans',sans-serif}
.block-container{max-width:1160px;padding:2rem 2rem 4rem}
h1,h2,h3,[data-testid=stMetricValue]{font-family:Manrope,sans-serif!important;color:var(--green)!important;letter-spacing:-.04em}
h1{font-size:clamp(2.5rem,5vw,4.4rem)!important;line-height:1.05!important}
[data-testid=stMetric]{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:1.2rem}
[data-testid=stMetricLabel]{color:var(--muted)!important}
.stButton>button,.stFormSubmitButton>button{background:var(--green);color:white;border:1px solid var(--green);border-radius:11px;font-weight:700;min-height:2.7rem}
.stButton>button:hover,.stFormSubmitButton>button:hover{background:var(--lime);color:var(--green);border-color:var(--lime)}
.stTextInput input,.stSelectbox [data-baseweb=select]>div{background:var(--card);border-color:var(--line);border-radius:10px}
[data-testid=stProgressBar]>div>div{background:var(--lime)}
[data-testid=stVerticalBlockBorderWrapper]{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:1rem}
.hero{background:var(--green);color:var(--bg);padding:clamp(1.7rem,4vw,3.5rem);border-radius:26px;margin:1rem 0 1.5rem;position:relative;overflow:hidden}
.hero:after{content:"";position:absolute;width:260px;height:260px;right:-70px;top:-100px;border:1px solid #C8FF4D66;border-radius:50%;box-shadow:0 0 0 28px #C8FF4D0A,0 0 0 60px #C8FF4D08}
.hero h1{color:var(--bg)!important;margin:.7rem 0}
.hero p{color:#D6E2D4;max-width:590px;line-height:1.7}
.eyebrow,.section{font-size:.75rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase}
.eyebrow{color:var(--lime)}
.section{color:var(--muted);margin:.8rem 0}
.pill{display:inline-block;border:1px solid #C8FF4D66;color:var(--lime);background:#C8FF4D12;padding:.4rem .7rem;border-radius:99px;font-size:.75rem;font-weight:700}
.tip{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:1rem 1.1rem;margin-bottom:.7rem}
.tip b{font-family:Manrope,sans-serif}
.tip p{color:var(--muted);font-size:.88rem;margin:.35rem 0 0}
.impact{background:var(--lime);padding:1.3rem;border-radius:18px;margin-bottom:.8rem}
.impact h2{margin:.35rem 0}
.impact p{font-size:.88rem;margin:0}
.footer{color:var(--muted);font-size:.78rem;border-top:1px solid var(--line);padding-top:1rem;margin-top:2.5rem}
#MainMenu,footer{visibility:hidden}
@media(max-width:700px){.block-container{padding:1rem}.hero{border-radius:20px}}
</style>
""", unsafe_allow_html=True)


def fetch(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "EcoTracker"})
    with urllib.request.urlopen(req, timeout=45) as r:
        dest.write_bytes(r.read())


def binary(repo, pattern, name):
    path = BASE / name
    if path.exists() and os.access(path, os.X_OK):
        return path
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest", headers={"User-Agent": "EcoTracker"})
    with urllib.request.urlopen(req, timeout=20) as r:
        release = json.load(r)
    asset = next((a for a in release["assets"] if re.search(pattern, a["name"], re.I)), None)
    if not asset:
        raise RuntimeError(f"No compatible {name} release asset found")
    archive = BASE / asset["name"]
    fetch(asset["browser_download_url"], archive)
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as tar:
            member = next((m for m in tar.getmembers() if Path(m.name).name == name), None)
            if not member:
                raise RuntimeError(f"{name} not found in archive")
            member.name = name
            tar.extract(member, BASE, filter="data")
    else:
        archive.replace(path)
    archive.unlink(missing_ok=True)
    path.chmod(0o755)
    return path


def pid_of(binary):
    for p in Path("/proc").iterdir():
        if p.name.isdigit():
            try:
                if (p / "cmdline").read_bytes().split(b"\0")[0].decode() == str(binary):
                    return int(p.name)
            except (OSError, ValueError):
                pass


def run(binary, args, log, restart=False):
    pid = pid_of(binary)
    if pid and restart:
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass
        for _ in range(20):
            time.sleep(.15)
            if not pid_of(binary):
                break
        pid = pid_of(binary)
    if pid:
        return pid
    with open(BASE / log, "ab") as f:
        proc = subprocess.Popen([str(binary), *args], cwd=BASE, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(.6)
    if proc.poll() is not None:
        raise RuntimeError((BASE / log).read_text(errors="ignore")[-2000:])
    return proc.pid


def setup():
    uid, token, domain = (str(st.secrets[k]).strip() for k in ("UUID", "TOKEN", "DOMAIN"))
    domain = domain.removeprefix("https://").removeprefix("http://").rstrip("/")
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower())
    if not uid or not token or not domain or not arch:
        raise RuntimeError("Check UUID, TOKEN, DOMAIN and CPU architecture in Secrets")
    sb = binary("SagerNet/sing-box", rf"sing-box-.*-linux-{arch}\.tar\.gz$", "sing-box")
    cf = binary("cloudflare/cloudflared", rf"cloudflared-linux-{arch}$", "cloudflared")
    path = "/" + uid[:8]
    config = {"log":{"level":"error"},"inbounds":[{"type":"vless","tag":"vless-in","listen":"127.0.0.1","listen_port":PORT,"users":[{"uuid":uid}],"transport":{"type":"ws","path":path},"multiplex":{"enabled":True,"padding":False}}],"outbounds":[{"type":"direct","tag":"direct"}]}
    raw = json.dumps(config, indent=2)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    stamp, cfg = BASE / "sb.sha256", BASE / "sb.json"
    restart = not stamp.exists() or stamp.read_text().strip() != digest
    cfg.write_text(raw)
    check = subprocess.run([str(sb), "check", "-c", str(cfg)], cwd=BASE, capture_output=True, text=True, timeout=15)
    if check.returncode:
        raise RuntimeError(check.stderr or check.stdout or "sing-box config validation failed")
    sbpid = run(sb, ["run", "-c", str(cfg)], "sing-box.log", restart)
    stamp.write_text(digest)
    cfpid = run(cf, ["tunnel", "--no-autoupdate", "--protocol", "auto", "run", "--token", token], "cloudflared.log")
    return uid, domain, path, sbpid, cfpid


def main():
    st.markdown("""
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap">
      <b style="font:800 1.2rem Manrope,sans-serif">● EcoTracker</b>
      <span style="font-size:.78rem;color:#788579;letter-spacing:.08em">PERSONAL CLIMATE DASHBOARD</span>
    </div>
    <div class="hero"><div class="eyebrow">SMALL ACTIONS. MEASURABLE CHANGE.</div>
    <h1>A lighter footprint<br>starts with you.</h1>
    <p>Build sustainable routines, track the little things that add up, and turn everyday choices into lasting impact.</p>
    <span class="pill">● YOUR DAILY IMPACT, REIMAGINED</span></div>
    <div class="section">01 / Impact overview · illustrative demo data</div>
    """, unsafe_allow_html=True)
    cols = st.columns(3)
    for col, label, value, delta in zip(cols, ["CO₂ avoided", "Water saved", "Car-free distance"], ["12.8 kg", "180 L", "42.5 km"], ["+8.4%", "+12.0%", "+6.2%"]):
        col.metric(label, value, delta)

    left, right = st.columns([1.1, .9], gap="large")
    with left:
        st.markdown('<div class="section">02 / Daily check-in</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.subheader("Make today count")
            st.caption("Log your choices to calculate a simple daily habit score.")
            travel = st.selectbox("How did you get around?", ["Walking", "Cycling", "Public transit", "Electric vehicle", "Fuel-powered vehicle"])
            habits = st.multiselect("Which habits did you complete?", ["Plant-forward meal", "Avoided food waste", "Sorted recycling", "Used reusables", "Saved energy"])
            score = min(100, {"Walking":40,"Cycling":40,"Public transit":30,"Electric vehicle":20,"Fuel-powered vehicle":0}[travel] + 12 * len(habits))
            st.markdown('<div class="section">YOUR DAILY ECO SCORE</div>', unsafe_allow_html=True)
            st.progress(score / 100)
            st.markdown(f"<h2 style='font-size:2.5rem'>{score}<span style='font-size:1rem;color:#788579'> / 100 points</span></h2>", unsafe_allow_html=True)
            st.caption("A motivational habit score, not a scientific carbon calculation.")
            if st.button("Save today's check-in", use_container_width=True):
                st.session_state.update(saved_score=score, checked_in=True)
                st.success(f"Saved for this session · {score} points")
            if st.session_state.get("checked_in"):
                st.caption(f"Latest saved score: {st.session_state['saved_score']} / 100")

    with right:
        st.markdown('<div class="section">03 / Your next small win</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="impact"><div class="eyebrow" style="color:#315D3C">TODAY'S FOCUS</div>
        <h2>Choose reuse.</h2><p>Bring a bottle, cup or shopping bag. Small habits become powerful when repeated.</p><div style="font-size:2.2rem">↗</div></div>
        <div class="tip"><b>↗ &nbsp; Move with intention</b><p>Walk, cycle or take public transit when practical.</p></div>
        <div class="tip"><b>✳ &nbsp; Waste less food</b><p>Plan a meal and use what you already have.</p></div>
        <div class="tip"><b>⌁ &nbsp; Use energy thoughtfully</b><p>Switch off unused lights and devices.</p></div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="footer">ECOTRACKER · MAKE BETTER HABITS VISIBLE<br>Demo metrics are illustrative, not measured personal impact.</div>', unsafe_allow_html=True)

    with st.expander("Settings"):
        with st.form("admin"):
            password = st.text_input("Access code", type="password")
            login = st.form_submit_button("Unlock", use_container_width=True)
        if login:
            st.session_state.admin_ok = password == str(st.secrets.get("MEMBER_CODE", "green2026"))
            st.session_state.show_node = False
            if not st.session_state.admin_ok:
                st.error("Invalid access code.")
        if st.session_state.get("admin_ok"):
            st.success("Access granted")
            if st.button("◉", help="Reveal or hide node details"):
                st.session_state.show_node = not st.session_state.get("show_node", False)
            if st.session_state.get("show_node"):
                uid, domain, path, sbpid, cfpid = setup()
                link = f"vless://{uid}@{domain}:443?{urlencode({'encryption':'none','type':'ws','host':domain,'path':path,'security':'tls','sni':domain,'fp':'chrome'})}#EcoTracker"
                st.text_input("VLESS link", value=link)
                st.json({"server":domain,"port":443,"uuid":uid,"network":"ws","path":path,"tls":True,"multiplex":True,"sing_box_pid":sbpid,"cloudflared_pid":cfpid})
        else:
            st.caption("Connection details remain hidden until access is verified.")


try:
    main()
    if all(k in st.secrets for k in ("UUID", "TOKEN", "DOMAIN")):
        setup()
except Exception as e:
    st.error("Service initialization failed.")
    st.code(str(e))
