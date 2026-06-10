import os, json, base64, platform, subprocess, time, tarfile
import threading
from pathlib import Path
import urllib.request

# ================= 📦 动态自建容器环境（单脚本核心） =================
# 在 Streamlit 还没有加载业务前，强行在容器根目录生成平台所需的依赖配置文件
def bootstrap_container_environment():
    """
    通过在运行期动态写入 packages.txt 和 requirements.txt，
    确保 Streamlit Cloud 容器能够自动下载并配置 Debian Chromium 浏览器。
    """
    # 1. 动态生成系统级包管理文件 packages.txt
    if not Path("packages.txt").exists():
        with open("packages.txt", "w", encoding="utf-8") as f:
            f.write("chromium\nchromium-driver\n")
        print("[Bootstrap] packages.txt 已自动生成，请等待系统二次部署完成。", flush=True)

    # 2. 动态生成 Python 依赖文件 requirements.txt
    if not Path("requirements.txt").exists():
        with open("requirements.txt", "w", encoding="utf-8") as f:
            f.write("streamlit\nselenium\n")
        print("[Bootstrap] requirements.txt 已自动生成。", flush=True)

# 立即执行环境初始化
bootstrap_container_environment()

# 环境配置完成后，安全导入 Streamlit 组件
import streamlit as st

# ================= ⚙️ 核心代理服务配置（完全保留原始逻辑） =================
BASE_DIR = Path("/tmp/.agsb_stable").resolve()
UID = st.secrets.get("UUID", "")
TOKEN = st.secrets.get("TOKEN", "")
DOMAIN = st.secrets.get("DOMAIN", "")
PORT = 49999
WS_PATH = f"/{UID[:8]}-vm"

def setup_binaries():
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
def start_services():
    sb, cf = setup_binaries()
    os.system("pkill -9 sing-box >/dev/null 2>&1")
    os.system("pkill -9 cloudflared >/dev/null 2>&1")
    time.sleep(1)

    cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "vmess", "listen": "127.0.0.1", "listen_port": PORT,
            "users": [{"uuid": UID}], 
            "sniff": True,
            "transport": {"type": "ws", "path": WS_PATH}
        }],
        "outbounds": [{"type": "direct"}]
    }
    with open("sb.json", "w") as f: json.dump(cfg, f)

    subprocess.Popen([str(sb), "run", "-c", "sb.json"], start_new_session=True)
    subprocess.Popen([str(cf), "tunnel", "--no-autoupdate", "run", "--token", TOKEN], start_new_session=True)
    
    vmess = {"v":"2", "ps":"Streamlit-Node", "add":DOMAIN, "port":"443", "id":UID, "net":"ws", "host":DOMAIN, "path":WS_PATH, "tls":"tls", "sni":DOMAIN}
    link = "vmess://" + base64.b64encode(json.dumps(vmess).encode()).decode()
    print(f"\n[NODE_LINK] {link}\n", flush=True)
    return link

# ================= 🟢 容器内无头浏览器纯内部保活线程 =================
def headless_browser_keepalive_daemon():
    time.sleep(20)
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        print("[Keep-Alive] 警告: 未检测到 selenium 库，内部浏览器保活未激活！", flush=True)
        return

    chrome_options = Options()
    chrome_options.add_argument("--headless")              # 无界面模式
    chrome_options.add_argument("--no-sandbox")             # 容器环境必备
    chrome_options.add_argument("--disable-dev-shm-usage")  # 共享内存保护
    chrome_options.add_argument("--blink-settings=imagesEnabled=false") # 禁用图片加载

    while True:
        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.get("http://127.0.0.1:8501")
            time.sleep(5) # 停留 5 秒确保 WebSocket 成功握手
            print(f"[Keep-Alive] 成功模拟网页打卡一次。当前页面标题: {driver.title}", flush=True)
        except Exception as e:
            print(f"[Keep-Alive] 模拟打卡轻微波动: {e}", flush=True)
        finally:
            if driver:
                try: driver.quit()
                except: pass
        time.sleep(600) # 每 10 分钟自动自刷保活一次

@st.cache_resource
def trigger_keepalive_once():
    t = threading.Thread(target=headless_browser_keepalive_daemon, daemon=True)
    t.start()
    return True

# ================= 🌿 深度伪装前端 UI 交互逻辑 =================
def main():
    # 页面配置全面包装为绿色环保、低碳生活主题
    st.set_page_config(page_title="EcoTracker - 低碳生活与碳足迹监测", page_icon="🌱", layout="centered")
    st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;}</style>", unsafe_allow_html=True)
    
    # 隐蔽启动后台核心服务
    link = ""
    if TOKEN and DOMAIN and UID:
        link = start_services()
        trigger_keepalive_once()

    # --- 伪装前端: 环保主题看板 ---
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
        score = 0
        if commute == "步行/自行车 (0碳排)": score += 50
        elif commute == "公共交通/地铁": score += 30
        if meals: score += 20
        if garbage: score += 20
        st.info(f"感谢打卡！今日低碳生活指数：**{score}/100**。继续保持！")

    st.write("---")
    st.subheader("💡 绿色环保小常识")
    with st.expander("1. 什么是‘碳中和’（Carbon Neutrality）？"):
        st.write("碳中和是指企业、团体或个人测算在一定时间内直接或间接产生的温室气体排放总量，通过植树造林等形式抵消自身产生的二氧化碳排放量，实现二氧化碳“零排放”。")
    with st.expander("2. 日常生活中有哪些行之有效的低碳习惯？"):
        st.write("• 随手关灯、拔掉闲置电器插头；\n• 尽量选择公共交通或绿色出行；\n• 减少一次性塑料制品的使用。")

    # ================= 🔐 核心节点隐藏入口 =================
    with st.expander("3. 区域网络节点碳补偿数据监测认证（系统核验）"):
        st.caption("注：此模块仅供个人节点数据核验与设备同步使用。")
        secret_key = st.text_input("请输入核验授权码 (Access Code)", type="password")
        
        # 🤫 暗号锁：输入 "green2026" 才会显示核心节点配置框
        if secret_key == "green2026": 
            st.success("授权成功，底层安全节点通道已建立：")
            if link: st.code(link)
            else: st.error("核心 secrets 配置不完整，无法生成通道。")
        elif secret_key != "":
            st.error("授权码校验失败，无访问权限。")

    # --- 前端高频无感刷新（维持 session 活跃与数据同步伪装） ---
    st.write("---")
    st.caption(f"系统运行环境：Debian Linux | 核心状态：🟢 正常运作")
    
    status_placeholder = st.empty()
    count = 0
    while True:
        count += 1
        status_placeholder.caption(f"🌍 绿色网络基准数据同步中... 次数: {count}")
        time.sleep(60)

if __name__ == "__main__":
    main()
