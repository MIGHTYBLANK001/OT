import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

# --- 核心配置 ---
BASE_DIR = Path("/tmp/.agsb_final").resolve()
UID = st.secrets.get("UUID", "")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "")
PORT = 49999
WS_PATH = f"/{UID[:8]}-vm"

def get_warp_config():
    """获取 WARP 注册信息 (移植自 argosbx.sh)"""
    try:
        url = "https://warp.xijp.eu.org"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode()
            if "Private_key" in content:
                pvk = content.split("Private_key：")[1].split("<br>")[0].strip()
                v6 = content.split("IPV6：")[1].split("<br>")[0].strip()
                res = content.split("reserved：")[1].split("<br>")[0].strip()
                return pvk, v6, json.loads(res)
    except:
        pass
    # 备选静态配置
    return "52cuYFgCJXp0LAq7+nWJIbCXXgU9eGggOc+Hlfz5u6A=", "2606:4700:110:8d8d:1845:c39f:2dd5:a03a", [215, 69, 233]

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
    # 彻底清理残留进程
    os.system("pkill -9 sing-box >/dev/null 2>&1")
    os.system("pkill -9 cloudflared >/dev/null 2>&1")
    time.sleep(2)

    # 获取 WARP 参数
    pvk, wpv6, res = get_warp_config()

    # Sing-box 混合配置
    cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess", "listen": "127.0.0.1", "listen_port": PORT,
            "users": [{"uuid": UID}], "sniff": True,
            "transport": {"type": "ws", "path": WS_PATH}
        }],
        "outbounds": [
            {"type": "direct", "tag": "direct"},
            {
                "type": "wireguard",
                "tag": "warp-out",
                "server": "engage.cloudflareclient.com",
                "server_port": 2408,
                "local_address": ["172.16.0.2/32", f"{wpv6}/128"],
                "private_key": pvk,
                "peer_public_key": "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=",
                "reserved": res,
                "mtu": 1280
            }
        ],
        "route": {
            "rules": [
                {"protocol": "dns", "outbound": "direct"},
                {"outbound": "warp-out"}
            ]
        }
    }
    with open("sb.json", "w") as f: json.dump(cfg, f)

    # 启动进程
    subprocess.Popen([str(sb), "run", "-c", "sb.json"], start_new_session=True)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], start_new_session=True)
    
    # 构造并打印节点链接到日志
    vmess = {"v":"2", "ps":"WARP-Streamlit", "add":DOMAIN, "port":"443", "id":UID, "net":"ws", "host":DOMAIN, "path":WS_PATH, "tls":"tls", "sni":DOMAIN}
    link = "vmess://" + base64.b64encode(json.dumps(vmess).encode()).decode()
    print(f"\n[SYSTEM_LOG] NODE_LINK: {link}\n", flush=True)

    return True

def main():
    st.set_page_config(page_title="Node Status", page_icon="🟢")
    st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;}</style>", unsafe_allow_html=True)
    st.title("🟢 Service Online")
    
    if not TOKEN or not DOMAIN:
        st.error("Missing Secrets: TOKEN or DOMAIN")
        return

    start_node()
    st.success("Tunnel and Sing-box (WARP) started. Check console logs for connection info.")

if __name__ == "__main__":
    main()
