
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
from urllib.parse import quote

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
        req = urllib.request.Request(
            url, headers={"User-Agent": "EcoTracker"}
        )
        with urllib.request.urlopen(req, timeout=60) as response, open(tmp, "wb") as f:
            shutil.copyfileobj(response, f)
        if tmp.stat().st_size < minimum:
            raise RuntimeError(f"下载文件异常: {tmp.stat().st_size} bytes")
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


def extract_binary(archive, destination, filename):
    with tarfile.open(archive, "r:gz") as tar:
        member = next(
            (m for m in tar.getmembers()
             if Path(m.name).name == filename and m.isfile()),
            None,
        )
        if member is None:
            raise RuntimeError(f"发布包中未找到 {filename}")
        src = tar.extractfile(member)
        if src is None:
            raise RuntimeError("无法读取发布包")
        with src, open(destination, "wb") as dst:
            shutil.copyfileobj(src, dst)
    destination.chmod(0o755)


def run_logged(cmd, log_name):
    with open(BASE / log_name, "ab", buffering=0) as log:
        return subprocess.Popen(
            cmd,
            cwd=BASE,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def log_tail(name):
    path = BASE / name
    return path.read_text(errors="replace")[-4000:] if path.exists() else "(无日志)"


def check_config(sb):
    result = subprocess.run(
        [str(sb), "check", "-c", "sb.json"],
        cwd=BASE, capture_output=True, text=True, timeout=15,
    )
    if result.returncode:
        raise RuntimeError(
            f"sing-box 配置校验失败:\n{result.stdout}\n{result.stderr}"
        )


@st.cache_resource
def setup():
    if not UID or not TOKEN or not DOMAIN:
        raise RuntimeError("请在 Streamlit Secrets 中配置 UUID、TOKEN、DOMAIN")
    try:
        uuid.UUID(UID)
    except ValueError:
        raise RuntimeError("UUID 格式无效")

    BASE.mkdir(parents=True, exist_ok=True)
    sb, cf = BASE / "sing-box", BASE / "cloudflared"
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64",
            "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    if not arch:
        raise RuntimeError(f"不支持的 CPU 架构: {machine}")

    if not sb.exists() or sb.stat().st_size < 1_000_000:
        ver = latest("SagerNet", "sing-box")
        archive = BASE / "sing-box.tar.gz"
        download(
            f"https://github.com/SagerNet/sing-box/releases/download/"
            f"v{ver}/sing-box-{ver}-linux-{arch}.tar.gz",
            archive,
        )
        extract_binary(archive, sb, "sing-box")
        archive.unlink(missing_ok=True)

    if not cf.exists() or cf.stat().st_size < 1_000_000:
        ver = latest("cloudflare", "cloudflared")
        download(
            f"https://github.com/cloudflare/cloudflared/releases/download/"
            f"{ver}/cloudflared-linux-{arch}",
            cf,
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
            "transport": {
                "type": "ws",
                "path": WS_PATH,
            },
        }],
        "outbounds": [{"type": "direct", "tag": "direct"}],
    }
    (BASE / "sb.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )
    check_config(sb)

    # 缓存只初始化一次；避免每次 Streamlit 重跑都杀死旧进程。
    sb_proc = run_logged([str(sb), "run", "-c", "sb.json"], "sing-box.log")
    time.sleep(1)
    if sb_proc.poll() is not None:
        raise RuntimeError("sing-box 启动失败:\n" + log_tail("sing-box.log"))

    cf_proc = run_logged([
        str(cf), "tunnel", "--no-autoupdate",
        "--protocol", "auto", "run", "--token", TOKEN,
    ], "cloudflared.log")
    time.sleep(2)
    if cf_proc.poll() is not None:
        raise RuntimeError("cloudflared 启动失败:\n" + log_tail("cloudflared.log"))

    return sb_proc, cf_proc


def node_link():
    from urllib.parse import urlencode
    params = urlencode({
        "encryption": "none",
        "security": "tls",
        "sni": DOMAIN,
        "type": "ws",
        "host": DOMAIN,
        "path": WS_PATH,
    })
    return f"vless://{UID}@{DOMAIN}:443?{params}#VLESS-Node"


def main():
    st.set_page_config(page_title="EcoTracker", page_icon="🌱")
    st.markdown("""
    <style>
    #MainMenu,footer{visibility:hidden}
    .block-container{max-width:680px;padding-top:1.5rem}
    .hero{background:linear-gradient(135deg,#2e7d32,#1b5e20);
    color:white;padding:22px;border-radius:14px;text-align:center}
    </style>
    <div class="hero"><h1>🌱 EcoTracker</h1>
    <p>绿色生活 · 每日环保记录</p></div>
    """, unsafe_allow_html=True)

    if UID and TOKEN and DOMAIN:
        try:
            sb_proc, cf_proc = setup()
            if sb_proc.poll() is not None or cf_proc.poll() is not None:
                st.error("服务进程已退出，请检查下方日志并重新启动应用。")
                st.code(
                    "=== sing-box ===\n" + log_tail("sing-box.log")
                    + "\n=== cloudflared ===\n" + log_tail("cloudflared.log")
                )
            else:
                st.caption("服务进程运行中；这不代表外部节点已连通。")
        except Exception as e:
            st.error(f"服务启动失败：{e}")
    else:
        st.warning("请先配置 UUID、TOKEN、DOMAIN。")

    st.subheader("📊 环保概览")
    a, b, c = st.columns(3)
    a.metric("步行 / 骑行", "42.5 km")
    b.metric("节水", "180 L")
    c.metric("减碳", "12.8 kg")

    with st.container(border=True):
        st.subheader("每日环保打卡")
        commute = st.selectbox(
            "出行方式",
            ["步行 / 骑行", "公共交通", "电动车", "燃油车"],
        )
        meals = st.checkbox("今天没有浪费食物")
        garbage = st.checkbox("今天正确分类垃圾")

        if st.button("提交并计算", use_container_width=True):
            score = (50 if commute == "步行 / 骑行"
                     else 30 if commute == "公共交通" else 0)
            score += 20 * meals + 20 * garbage
            st.success(f"今日环保得分：{score}/100")
            st.progress(score / 100)

    with st.container(border=True):
        st.subheader("💡 环保建议")
        st.markdown(
            "- 及时关闭闲置灯具和电子设备。\n"
            "- 优先选择步行、骑行或公共交通。\n"
            "- 自带水杯和购物袋，减少一次性塑料。"
        )

    with st.container(border=True):
        st.subheader("🌿 会员验证")
        code = st.text_input("访问密码", type="password")
        if st.button("验证会员", use_container_width=True):
            if code and code == MEMBER_CODE:
                if not (UID and TOKEN and DOMAIN):
                    st.error("节点尚未配置完整。")
                else:
                    st.session_state["member_verified"] = True
            else:
                st.session_state["member_verified"] = False
                st.error("密码错误。")

        if st.session_state.get("member_verified") and UID and DOMAIN:
            st.success("验证成功")
            st.code(node_link(), language=None)
            st.caption("连接参数")
            st.code(
                f"地址：{DOMAIN}\n端口：443\nUUID：{UID}\n"
                f"网络：WebSocket\n安全：TLS\n路径：{WS_PATH}",
                language=None,
            )

    st.caption(f"Debian Linux · {time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
