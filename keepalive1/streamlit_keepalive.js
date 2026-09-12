/*
 * streamlit_keepalive.js
 * 单文件版 Streamlit Cloud 保活脚本 —— 青龙面板订阅拉取即用(Node.js,不需要 python3)
 *
 * 原理:
 * Streamlit 应用休眠后普通 GET 请求会返回 200 但只是静态占位页,必须用真实浏览器
 * 建立 WebSocket 连接并点击 "Yes, get this app back up!" 按钮才能真正唤醒。
 * 本脚本用 Playwright(Node版)驱动系统 chromium 完成这一步,单次运行、用完即关,
 * 首次运行会自动 apk 装 chromium、npm 装 playwright(且跳过下载 playwright 自带
 * 的浏览器,只用系统 chromium,省磁盘和内存)。
 *
 * 青龙订阅配置(订阅管理 -> 新建订阅):
 *   链接:      你的 GitHub 仓库地址
 *   定时规则:  按需,例如 0 * / 6 * * *(每6小时,自己去掉空格)
 *   白名单:    keepalive
 *   自动添加任务: 开
 *
 * 环境变量(可选): STREAMLIT_URL
 */

const { execSync } = require('child_process');
const path = require('path');

const SCRIPT_DIR = __dirname;

const DEFAULT_URL = 'https://l2uetmksgajvryi4qmegvn.streamlit.app/';
const TARGET_URL = process.env.STREAMLIT_URL || DEFAULT_URL;

const NAV_TIMEOUT_MS = 60_000;        // 首次打开页面的超时
const WAKE_WAIT_TIMEOUT_S = 240;      // 点击唤醒后最多等待冷启动(4分钟)
const POLL_INTERVAL_S = 5;
const MAX_RETRY = 1;

function log(msg) {
  const t = new Date().toTimeString().slice(0, 8);
  console.log(`[${t}] ${msg}`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function which(bin) {
  try {
    const out = execSync(`command -v ${bin} 2>/dev/null`, { encoding: 'utf8' }).trim();
    return out || null;
  } catch {
    return null;
  }
}

function ensureChromium() {
  let path = which('chromium-browser') || which('chromium');
  if (path) return path;

  if (!which('apk')) {
    throw new Error('未检测到 chromium,且当前系统没有 apk 命令,无法自动安装,请手动装好 chromium');
  }

  log('未检测到 chromium,尝试通过 apk 自动安装(仅首次运行需要)...');
  execSync(
    'apk add --no-cache chromium nss freetype freetype-dev harfbuzz ca-certificates ttf-freefont',
    { stdio: 'inherit' }
  );

  path = which('chromium-browser') || which('chromium');
  if (!path) throw new Error('apk 安装命令已执行但仍未找到 chromium,请查看上面的安装日志排查');
  return path;
}

function ensurePlaywright() {
  try {
    require.resolve('playwright');
    return;
  } catch {
    // 继续走下面的安装逻辑
  }

  try {
    require.resolve(path.join(SCRIPT_DIR, 'node_modules', 'playwright'));
    return;
  } catch {
    // 确实没装,继续安装
  }

  log('未检测到 playwright,安装到脚本自身目录(仅首次运行需要,跳过下载自带浏览器,不碰青龙根目录依赖)...');
  execSync(`npm install --no-save --legacy-peer-deps --prefix "${SCRIPT_DIR}" playwright`, {
    stdio: 'inherit',
    cwd: SCRIPT_DIR,
    env: { ...process.env, PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: '1' },
  });
}

function notify(title, content) {
  const candidates = [
    '/ql/data/scripts/sendNotify.js',
    '/ql/scripts/sendNotify.js',
    './sendNotify.js',
    './sendNotify',
  ];
  for (const p of candidates) {
    try {
      const mod = require(p);
      const fn = typeof mod === 'function' ? mod : mod.sendNotify;
      if (typeof fn === 'function') {
        fn(title, content);
        return;
      }
    } catch {
      // 继续尝试下一个候选路径
    }
  }
  log(`[通知发送失败,仅打印日志]\n标题: ${title}\n内容: ${content}`);
}

async function runOnce(chromiumPath) {
  const { chromium } = require('playwright');

  const startTs = new Date();
  const result = {
    url: TARGET_URL,
    start_time: startTs.toLocaleString('zh-CN', { hour12: false }),
    status: '未知',
    detail: '',
    duration_s: 0,
  };

  const browser = await chromium.launch({
    executablePath: chromiumPath,
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--disable-software-rasterizer',
      '--disable-extensions',
      '--disable-background-networking',
      '--disable-sync',
      '--disable-default-apps',
      '--js-flags=--max-old-space-size=128',
    ],
  });

  try {
    const context = await browser.newContext({ viewport: { width: 1024, height: 768 } });
    const page = await context.newPage();
    page.setDefaultTimeout(NAV_TIMEOUT_MS);

    await page.goto(TARGET_URL, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT_MS });
    await page.waitForTimeout(4000); // 留时间给页面渲染出关键元素

    const wakeButton = page.getByRole('button', { name: 'Yes, get this app back up!' });
    const appContainer = page.locator("[data-testid='stAppViewContainer']");

    if ((await wakeButton.count()) > 0) {
      result.detail = '检测到休眠页,已点击唤醒按钮';
      await wakeButton.first().click();

      let waited = 0;
      let awake = false;
      while (waited < WAKE_WAIT_TIMEOUT_S) {
        await sleep(POLL_INTERVAL_S * 1000);
        waited += POLL_INTERVAL_S;
        if ((await appContainer.count()) > 0) {
          awake = true;
          break;
        }
      }

      if (awake) {
        result.status = '唤醒成功';
        result.detail += `,等待 ${waited}s 后应用已启动`;
      } else {
        result.status = '唤醒超时';
        result.detail += `,等待 ${waited}s 后应用仍未渲染出主体(可能仍在冷启动)`;
      }
    } else if ((await appContainer.count()) > 0) {
      result.status = '本来就是活的';
      result.detail = '访问时应用已在运行,无需唤醒';
    } else {
      result.status = '状态未知';
      result.detail = '未检测到休眠按钮也未检测到应用主体,页面结构可能变化,建议人工检查一次';
    }
  } finally {
    await browser.close();
  }

  result.duration_s = Math.round((Date.now() - startTs.getTime()) / 100) / 10;
  return result;
}

async function main() {
  ensurePlaywright();
  const chromiumPath = ensureChromium();

  let lastErr = null;
  for (let attempt = 1; attempt <= MAX_RETRY + 1; attempt++) {
    try {
      return await runOnce(chromiumPath);
    } catch (e) {
      lastErr = e;
      log(`[第 ${attempt} 次尝试失败] ${e.message}`);
      await sleep(3000);
    }
  }

  return {
    url: TARGET_URL,
    start_time: new Date().toLocaleString('zh-CN', { hour12: false }),
    status: '异常',
    detail: `重试 ${MAX_RETRY + 1} 次后仍失败: ${lastErr && lastErr.message}`,
    duration_s: 0,
  };
}

(async () => {
  let r;
  try {
    r = await main();
  } catch (e) {
    r = {
      url: TARGET_URL,
      start_time: new Date().toLocaleString('zh-CN', { hour12: false }),
      status: '环境准备失败',
      detail: `${e.message}`,
      duration_s: 0,
    };
  }

  const title = `Streamlit保活 - ${r.status}`;
  const content =
    `目标: ${r.url}\n` +
    `开始时间: ${r.start_time}\n` +
    `耗时: ${r.duration_s}s\n` +
    `结果: ${r.status}\n` +
    `详情: ${r.detail}`;

  console.log(content);
  notify(title, content);
})();
