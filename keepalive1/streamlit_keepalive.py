#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
streamlit_keepalive.py
单文件版 Streamlit Cloud 保活脚本 —— 青龙面板订阅拉取即用

原理:
Streamlit 应用休眠后普通 GET 请求会返回 200 但只是静态占位页,必须用真实浏览器
建立 WebSocket 连接并点击"Yes, get this app back up!"按钮才能真正唤醒。
本脚本用 Playwright 驱动系统 chromium 完成这一步,单次运行、用完即关,
并在首次运行时自动补装所需的系统依赖(apk)和 python 依赖(pip),
不需要额外的安装脚本。

青龙订阅配置(在"订阅管理"里新建):
    链接:      你 fork/上传后的 GitHub 仓库地址
    定时规则:  自己按休眠周期定,例如 0 */6 * * * (每6小时跑一次)
    白名单:    脚本文件名关键字,例如 keepalive
    自动添加任务: 开

环境变量(可选):
    STREAMLIT_URL   目标应用地址,不填用下面 DEFAULT_URL
"""

import os
import sys
import time
import shutil
import subprocess
import traceback
from datetime import datetime

DEFAULT_URL = "https://l2uetmksgajvryi4qmegvn.streamlit.app/"
TARGET_URL = os.environ.get("STREAMLIT_URL", DEFAULT_URL)

NAV_TIMEOUT_MS = 60_000          # 首次打开页面的超时
WAKE_WAIT_TIMEOUT_S = 240        # 点击唤醒后最多等待冷启动(4分钟)
POLL_INTERVAL_S = 5
MAX_RETRY = 1


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def ensure_chromium():
    """检测系统 chromium,没有就用 apk 自动装(需要 root 权限,青龙容器默认满足)"""
    for name in ("chromium-browser", "chromium"):
        path = shutil.which(name)
        if path:
            return path

    if shutil.which("apk") is None:
        raise RuntimeError("未检测到 chromium,且当前系统没有 apk 命令,无法自动安装,请手动装好 chromium")

    log("未检测到 chromium,尝试通过 apk 自动安装(仅首次运行需要)...")
    pkgs = ["chromium", "nss", "freetype", "freetype-dev", "harfbuzz", "ca-certificates", "ttf-freefont"]
    subprocess.run(["apk", "add", "--no-cache"] + pkgs, check=True)

    for name in ("chromium-browser", "chromium"):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError("apk 安装命令已执行但仍未找到 chromium,请查看上面的安装日志排查")


def ensure_playwright():
    """检测 playwright 的 python 包,没有就自动 pip install(仅首次运行需要)"""
    try:
        import playwright  # noqa: F401
        return
    except ImportError:
        log("未检测到 playwright,尝试自动安装...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "playwright"],
            check=True,
        )


def notify(title, content):
    """走青龙自带 notify.py 发送通知,找不到就退化为打印日志"""
    for path in ("/ql/data/scripts", "/ql/scripts"):
        if path not in sys.path:
            sys.path.append(path)
    try:
        from notify import send
        send(title, content)
    except Exception as e:
        log(f"[通知发送失败,仅打印日志]\n标题: {title}\n内容: {content}\n错误: {e}")


def run_once(chromium_path):
    from playwright.sync_api import sync_playwright

    start_ts = datetime.now()
    result = {
        "url": TARGET_URL,
        "start_time": start_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "未知",
        "detail": "",
        "duration_s": 0,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=chromium_path,
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-default-apps",
                "--js-flags=--max-old-space-size=128",
            ],
        )
        try:
            context = browser.new_context(viewport={"width": 1024, "height": 768})
            page = context.new_page()
            page.set_default_timeout(NAV_TIMEOUT_MS)

            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(4000)  # 留时间给页面渲染出关键元素

            wake_button = page.get_by_role("button", name="Yes, get this app back up!")
            app_container = page.locator("[data-testid='stAppViewContainer']")

            if wake_button.count() > 0:
                result["detail"] = "检测到休眠页,已点击唤醒按钮"
                wake_button.first.click()

                waited = 0
                awake = False
                while waited < WAKE_WAIT_TIMEOUT_S:
                    time.sleep(POLL_INTERVAL_S)
                    waited += POLL_INTERVAL_S
                    if app_container.count() > 0:
                        awake = True
                        break

                if awake:
                    result["status"] = "唤醒成功"
                    result["detail"] += f",等待 {waited}s 后应用已启动"
                else:
                    result["status"] = "唤醒超时"
                    result["detail"] += f",等待 {waited}s 后应用仍未渲染出主体(可能仍在冷启动)"

            elif app_container.count() > 0:
                result["status"] = "本来就是活的"
                result["detail"] = "访问时应用已在运行,无需唤醒"

            else:
                result["status"] = "状态未知"
                result["detail"] = "未检测到休眠按钮也未检测到应用主体,页面结构可能变化,建议人工检查一次"

        finally:
            browser.close()

    result["duration_s"] = round((datetime.now() - start_ts).total_seconds(), 1)
    return result


def main():
    ensure_playwright()
    chromium_path = ensure_chromium()

    last_err = None
    for attempt in range(1, MAX_RETRY + 2):
        try:
            return run_once(chromium_path)
        except Exception as e:
            last_err = e
            log(f"[第 {attempt} 次尝试失败] {e}")
            time.sleep(3)

    return {
        "url": TARGET_URL,
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "异常",
        "detail": f"重试 {MAX_RETRY + 1} 次后仍失败: {last_err}\n{traceback.format_exc()[-500:]}",
        "duration_s": 0,
    }


if __name__ == "__main__":
    try:
        r = main()
    except Exception as e:
        r = {
            "url": TARGET_URL,
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "环境准备失败",
            "detail": f"{e}\n{traceback.format_exc()[-500:]}",
            "duration_s": 0,
        }

    title = f"Streamlit保活 - {r['status']}"
    content = (
        f"目标: {r['url']}\n"
        f"开始时间: {r['start_time']}\n"
        f"耗时: {r['duration_s']}s\n"
        f"结果: {r['status']}\n"
        f"详情: {r['detail']}"
    )
    print(content)
    notify(title, content)
