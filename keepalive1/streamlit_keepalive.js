/*
 * streamlit_keepalive.js
 * Streamlit Cloud 保活脚本
 * 兼容 Alpine / Debian / Ubuntu
 * Node.js + Playwright + 系统 Chromium
 *
 * 青龙订阅：
 *   白名单：keepalive
 *   环境变量：STREAMLIT_URL（可选）
 *
 * 依赖：
 *   Node.js、npm
 *   首次运行自动安装 Chromium 和 Playwright
 */

'use strict';

const {
  execFileSync,
  spawnSync,
} = require('child_process');
const fs = require('fs');
const path = require('path');

const SCRIPT_DIR = __dirname;
const DEFAULT_URL =
  'https://l2uetmksgajvryi4qmegvn.streamlit.app/';
const TARGET_URL = process.env.STREAMLIT_URL || DEFAULT_URL;

const NAV_TIMEOUT_MS = 60_000;
const WAKE_WAIT_TIMEOUT_S = 300;
const POLL_INTERVAL_S = 5;
const RELOAD_EVERY_S = 30;
const MAX_RETRY = 1;
const OVERALL_TIMEOUT_MS = 9 * 60 * 1000;

let activeBrowser = null;
let finished = false;
let timedOut = false;

function log(msg) {
  console.log(`[${new Date().toTimeString().slice(0, 8)}] ${msg}`);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function commandExists(bin) {
  const r = spawnSync('sh', ['-c', 'command -v "$1"', 'sh', bin], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'ignore'],
  });
  return r.status === 0 && !!r.stdout.trim();
}

function runCommand(bin, args, options = {}) {
  log(`执行：${bin} ${args.join(' ')}`);
  execFileSync(bin, args, {
    stdio: 'inherit',
    ...options,
  });
}

function detectOS() {
  let id = '';
  let idLike = '';

  try {
    const content = fs.readFileSync('/etc/os-release', 'utf8');
    for (const line of content.split('\n')) {
      const m = line.match(/^(ID|ID_LIKE)=(.*)$/);
      if (!m) continue;

      const value = m[2].trim().replace(/^["']|["']$/g, '');
      if (m[1] === 'ID') id = value.toLowerCase();
      if (m[1] === 'ID_LIKE') idLike = value.toLowerCase();
    }
  } catch (_) {}

  if (id === 'alpine') return 'alpine';
  if (id === 'debian' || id === 'ubuntu') return 'debian';
  if (/\b(debian|ubuntu)\b/.test(idLike)) return 'debian';

  if (commandExists('apk')) return 'alpine';
  if (commandExists('apt-get')) return 'debian';

  throw new Error(
    `不支持的系统：ID=${id || 'unknown'}，ID_LIKE=${idLike || 'unknown'}`
  );
}

function findChromium() {
  const candidates = [
    'chromium',
    'chromium-browser',
    'google-chrome-stable',
    'google-chrome',
  ];

  for (const bin of candidates) {
    if (commandExists(bin)) {
      const r = spawnSync('sh', ['-c', 'command -v "$1"', 'sh', bin], {
        encoding: 'utf8',
      });
      if (r.status === 0 && r.stdout.trim()) {
        return r.stdout.trim().split('\n')[0];
      }
    }
  }

  const fixedPaths = [
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium/chromium',
  ];

  return fixedPaths.find(p => fs.existsSync(p)) || null;
}

function ensureChromium() {
  let browserPath = findChromium();
  if (browserPath) {
    log(`检测到系统浏览器：${browserPath}`);
    return browserPath;
  }

  const os = detectOS();
  log(`未检测到 Chromium，系统类型：${os}，开始安装`);

  if (os === 'alpine') {
    if (!commandExists('apk')) {
      throw new Error('缺少 apk，无法安装 Chromium');
    }

    runCommand('apk', [
      'add', '--no-cache',
      'chromium',
      'nss',
      'freetype',
      'harfbuzz',
      'ca-certificates',
      'ttf-freefont',
    ]);
  } else {
    if (!commandExists('apt-get')) {
      throw new Error('缺少 apt-get，无法安装 Chromium');
    }

    if (typeof process.getuid === 'function' && process.getuid() !== 0) {
      throw new Error(
        'Debian/Ubuntu 安装 Chromium 需要 root 权限，请在容器构建阶段安装，或使用 root 执行首次安装'
      );
    }

    runCommand('apt-get', ['update']);

    try {
      runCommand('apt-get', [
        'install', '-y', '--no-install-recommends',
        'chromium',
        'ca-certificates',
        'fonts-liberation',
      ]);
    } catch (e) {
      log('安装 chromium 失败，尝试 chromium-browser');
      runCommand('apt-get', [
        'install', '-y', '--no-install-recommends',
        'chromium-browser',
        'ca-certificates',
        'fonts-liberation',
      ]);
    }
  }

  browserPath = findChromium();
  if (!browserPath) {
    throw new Error(
      '安装命令执行完成，但找不到浏览器可执行文件，请检查系统软件源及安装日志'
    );
  }

  log(`Chromium 安装完成：${browserPath}`);
  return browserPath;
}

function ensurePlaywright() {
  const localModule = path.join(SCRIPT_DIR, 'node_modules', 'playwright');

  try {
    require.resolve('playwright');
    log('Playwright 模块已存在');
    return;
  } catch (_) {}

  if (fs.existsSync(path.join(localModule, 'package.json'))) {
    log('检测到脚本目录中的 Playwright 模块');
    return;
  }

  if (!commandExists('npm')) {
    throw new Error('未检测到 npm，请先安装 Node.js 和 npm');
  }

  log('安装 Playwright（不下载 Playwright 自带浏览器）');

  const env = {
    ...process.env,
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: '1',
  };

  const args = [
    'install',
    '--no-save',
    '--no-audit',
    '--no-fund',
    '--legacy-peer-deps',
    '--prefix', SCRIPT_DIR,
    'playwright',
  ];

  function install(registry) {
    const finalArgs = [...args];
    if (registry) {
      finalArgs.push('--registry', registry);
    }

    execFileSync('npm', finalArgs, {
      cwd: SCRIPT_DIR,
      env,
      stdio: 'inherit',
    });
  }

  try {
    install(process.env.NPM_REGISTRY || undefined);
  } catch (e) {
    log('默认 npm 源安装失败，尝试 npmmirror');
    install('https://registry.npmmirror.com');
  }

  if (!fs.existsSync(path.join(localModule, 'package.json'))) {
    throw new Error('npm 执行后仍未找到 Playwright 模块');
  }

  log('Playwright 安装完成');
}

async function notify(title, content) {
  const candidates = [
    '/ql/data/scripts/sendNotify.js',
    '/ql/scripts/sendNotify.js',
    path.join(SCRIPT_DIR, 'sendNotify.js'),
    path.join(SCRIPT_DIR, 'sendNotify'),
  ];

  for (const p of candidates) {
    try {
      const mod = require(p);
      const fn = typeof mod === 'function' ? mod : mod.sendNotify;

      if (typeof fn === 'function') {
        await Promise.resolve(fn(title, content));
        return;
      }
    } catch (e) {
      log(`通知模块不可用：${p}，${e.message}`);
    }
  }

  log(`未找到可用通知模块\n标题：${title}\n内容：\n${content}`);
}

async function runOnce(chromiumPath) {
  const { chromium } = require('playwright');
  const startTs = Date.now();

  const result = {
    url: TARGET_URL,
    start_time: new Date().toLocaleString('zh-CN', { hour12: false }),
    status: '未知',
    detail: '',
    duration_s: 0,
  };

  const browser = await chromium.launch({
    executablePath: chromiumPath,
    headless: true,
    timeout: NAV_TIMEOUT_MS,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--disable-software-rasterizer',
      '--disable-extensions',
      '--disable-background-networking',
      '--disable-sync',
      '--disable-default-apps',
      '--disable-features=Translate,BackForwardCache',
      '--blink-settings=imagesEnabled=false',
      '--js-flags=--max-old-space-size=128',
    ],
  });

  activeBrowser = browser;
  log('Chromium 已启动');

  try {
    const context = await browser.newContext({
      viewport: { width: 800, height: 600 },
    });

    const page = await context.newPage();
    page.setDefaultTimeout(NAV_TIMEOUT_MS);
    page.setDefaultNavigationTimeout(NAV_TIMEOUT_MS);

    await page.route('**/*', route => {
      const type = route.request().resourceType();

      if (['image', 'font', 'media'].includes(type)) {
        return route.abort();
      }

      return route.continue();
    });

    log(`开始加载：${TARGET_URL}`);

    await page.goto(TARGET_URL, {
      waitUntil: 'domcontentloaded',
      timeout: NAV_TIMEOUT_MS,
    });

    await page.waitForTimeout(4000);

    async function isSleeping() {
      const text = await page.locator('body').innerText().catch(() => '');
      return /gone to sleep|get this app back up|Zzz{2,}/i.test(text);
    }

    if (await isSleeping()) {
      result.detail = '检测到休眠页';

      const button = page.getByRole('button', {
        name: /get this app back up/i,
      });

      if (await button.count()) {
        await button.first().click();
        result.detail += '，已点击唤醒按钮';
        log('已点击唤醒按钮');
      } else {
        result.detail += '，未找到唤醒按钮';
      }

      let waited = 0;
      let awake = false;

      while (waited < WAKE_WAIT_TIMEOUT_S) {
        await sleep(POLL_INTERVAL_S * 1000);
        waited += POLL_INTERVAL_S;

        if (waited % RELOAD_EVERY_S === 0) {
          try {
            await page.reload({
              waitUntil: 'domcontentloaded',
              timeout: NAV_TIMEOUT_MS,
            });
          } catch (e) {
            log(`${waited}s 时刷新失败：${e.message}`);
          }
        }

        if (!(await isSleeping())) {
          awake = true;
          break;
        }

        log(`唤醒等待中：${waited}/${WAKE_WAIT_TIMEOUT_S}s`);
      }

      if (awake) {
        result.status = '唤醒成功';
        result.detail += `，等待 ${waited}s 后休眠文案消失`;
      } else {
        result.status = '唤醒超时';
        result.detail += `，等待 ${waited}s 后仍检测到休眠文案`;
      }
    } else {
      result.status = '本来就是活的';
      result.detail = '未检测到休眠文案，无需唤醒';
    }

    log('继续保持浏览器连接 60 秒');
    await page.waitForTimeout(60_000);
  } finally {
    activeBrowser = null;
    await browser.close().catch(() => {});
  }

  result.duration_s = Math.round((Date.now() - startTs) / 100) / 10;
  return result;
}

async function main() {
  log('开始执行 Streamlit 保活流程');

  // 优先完成系统浏览器准备，避免无意义地下载 npm 模块
  const chromiumPath = ensureChromium();
  ensurePlaywright();

  let lastErr;

  for (let attempt = 1; attempt <= MAX_RETRY + 1; attempt++) {
    try {
      return await runOnce(chromiumPath);
    } catch (e) {
      lastErr = e;
      activeBrowser = null;
      log(`第 ${attempt} 次执行失败：${e.stack || e.message}`);

      if (attempt <= MAX_RETRY) {
        await sleep(3000);
      }
    }
  }

  return {
    url: TARGET_URL,
    start_time: new Date().toLocaleString('zh-CN', { hour12: false }),
    status: '异常',
    detail: `重试 ${MAX_RETRY + 1} 次后失败：${lastErr?.message || '未知错误'}`,
    duration_s: 0,
  };
}

function withTimeout(promise, ms) {
  let timer;

  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      timedOut = true;

      if (activeBrowser) {
        activeBrowser.close().catch(() => {});
      }

      reject(new Error(`整体执行超时（${ms / 1000}s）`));
    }, ms);
  });

  return Promise.race([promise, timeout])
    .finally(() => clearTimeout(timer));
}

async function finish() {
  let result;

  try {
    result = await withTimeout(main(), OVERALL_TIMEOUT_MS);
  } catch (e) {
    result = {
      url: TARGET_URL,
      start_time: new Date().toLocaleString('zh-CN', { hour12: false }),
      status: timedOut ? '执行超时' : '环境准备失败',
      detail: e.message,
      duration_s: 0,
    };
  }

  const content =
    `目标：${result.url}\n` +
    `开始时间：${result.start_time}\n` +
    `耗时：${result.duration_s}s\n` +
    `结果：${result.status}\n` +
    `详情：${result.detail}`;

  console.log('\n' + content);

  try {
    await withTimeout(notify(`Streamlit保活 - ${result.status}`, content), 15000);
  } catch (e) {
    log(`通知处理失败：${e.message}`);
  }

  finished = true;

  // 清除可能残留的定时器，避免脚本因后台任务而继续挂起
  process.exitCode = ['异常', '执行超时', '环境准备失败'].includes(result.status)
    ? 1
    : 0;
}

process.on('uncaughtException', e => {
  console.error('[未捕获异常]', e.stack || e);
  if (activeBrowser) activeBrowser.close().catch(() => {});
  process.exit(1);
});

process.on('unhandledRejection', e => {
  console.error('[未处理的 Promise 拒绝]', e?.stack || e);
  if (activeBrowser) activeBrowser.close().catch(() => {});
  process.exit(1);
});

finish().catch(e => {
  if (!finished) {
    console.error('[主流程失败]', e.stack || e);
    process.exitCode = 1;
  }
});
```
