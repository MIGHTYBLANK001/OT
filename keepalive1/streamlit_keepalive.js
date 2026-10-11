/*
 * streamlit_keepalive.js
 * Streamlit Cloud 保活脚本
 * Node.js 20+ | Alpine | Debian | Ubuntu | 青龙面板
 *
 * 环境变量：
 * STREAMLIT_URL       目标地址
 * CHROMIUM_PATH       指定浏览器路径（可选）
 * PLAYWRIGHT_PATH     指定 Playwright 模块路径（可选）
 * KEEPALIVE_WAIT      唤醒等待秒数，默认 300
 * KEEPALIVE_HOLD      成功检测后的停留秒数，默认 30
 * KEEPALIVE_TIMEOUT   总超时秒数，默认 540
 *
 * 依赖：系统 Chromium + npm 包 playwright
 * 不主动加载青龙 sendNotify.js，避免通知依赖影响主流程。
 */

'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn, spawnSync } = require('child_process');

const ROOT = __dirname;
const URL = process.env.STREAMLIT_URL ||
  'https://l2uetmksgajvryi4qmegvn.streamlit.app/';

const NAV_TIMEOUT = 60000;
const WAKE_WAIT = numberEnv('KEEPALIVE_WAIT', 300, 30, 600);
const HOLD_SECONDS = numberEnv('KEEPALIVE_HOLD', 30, 0, 120);
const TOTAL_TIMEOUT = numberEnv('KEEPALIVE_TIMEOUT', 540, 60, 900);
const POLL_SECONDS = 5;
const RELOAD_SECONDS = 30;
const MAX_RETRIES = 2;

let browserInstance = null;
let childProcesses = new Set();
let stopping = false;

function numberEnv(name, fallback, min, max) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) && value >= min && value <= max
    ? Math.floor(value)
    : fallback;
}

function log(message) {
  console.log(`[${new Date().toISOString()}] ${message}`);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function fileExists(file) {
  try {
    return fs.statSync(file).isFile();
  } catch (_) {
    return false;
  }
}

function commandPath(command) {
  const result = spawnSync(
    'sh',
    ['-c', 'command -v "$1"', 'sh', command],
    { encoding: 'utf8', timeout: 5000, stdio: ['ignore', 'pipe', 'ignore'] }
  );

  return result.status === 0 ? result.stdout.trim() : '';
}

function run(command, args, timeoutMs = 120000) {
  return new Promise((resolve, reject) => {
    log(`执行命令：${command} ${args.join(' ')}`);

    const child = spawn(command, args, {
      stdio: 'inherit',
      env: process.env,
    });

    childProcesses.add(child);

    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill('SIGTERM');

      setTimeout(() => {
        if (child.exitCode === null) child.kill('SIGKILL');
      }, 2000).unref();

      reject(new Error(`命令执行超时：${command}`));
    }, timeoutMs);

    child.once('error', error => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      childProcesses.delete(child);
      reject(error);
    });

    child.once('close', code => {
      childProcesses.delete(child);
      clearTimeout(timer);

      if (settled) return;
      settled = true;

      if (code === 0) resolve();
      else reject(new Error(`${command} 退出，代码 ${code}`));
    });
  });
}

function detectOS() {
  let id = '';
  let like = '';

  try {
    const text = fs.readFileSync('/etc/os-release', 'utf8');

    for (const line of text.split(/\r?\n/)) {
      const match = line.match(/^(ID|ID_LIKE)=(.*)$/);
      if (!match) continue;

      const value = match[2].replace(/^["']|["']$/g, '').toLowerCase();
      if (match[1] === 'ID') id = value;
      else like = value;
    }
  } catch (_) {}

  if (id === 'alpine' || commandPath('apk')) return 'alpine';
  if (['debian', 'ubuntu'].includes(id) || commandPath('apt-get')) {
    return 'debian';
  }

  if (/\b(debian|ubuntu)\b/.test(like)) return 'debian';
  return 'unknown';
}

function findChromium() {
  if (process.env.CHROMIUM_PATH) {
    if (!fileExists(process.env.CHROMIUM_PATH)) {
      throw new Error(`CHROMIUM_PATH 不存在：${process.env.CHROMIUM_PATH}`);
    }
    return process.env.CHROMIUM_PATH;
  }

  for (const name of [
    'chromium',
    'chromium-browser',
    'google-chrome',
    'google-chrome-stable',
  ]) {
    const p = commandPath(name);
    if (p) return p;
  }

  for (const p of [
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium/chromium',
  ]) {
    if (fileExists(p)) return p;
  }

  return '';
}

function findPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_PATH,
    path.join(ROOT, 'node_modules', 'playwright'),
    '/ql/data/scripts/node_modules/playwright',
    '/ql/data/dep_cache/node/global/5/node_modules/playwright',
    '/ql/data/dep_cache/node/global/5/.pnpm/node_modules/playwright',
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      const resolved = require.resolve(candidate);
      return require(resolved);
    } catch (_) {}

    try {
      const packageJson = path.join(candidate, 'package.json');
      if (fileExists(packageJson)) return require(candidate);
    } catch (_) {}
  }

  try {
    return require('playwright');
  } catch (_) {}

  try {
    const npmRoot = commandPath('npm');
    if (npmRoot) {
      const result = spawnSync('npm', ['root', '-g'], {
        encoding: 'utf8',
        timeout: 5000,
      });

      if (result.status === 0) {
        const modulePath = path.join(result.stdout.trim(), 'playwright');
        if (fileExists(path.join(modulePath, 'package.json'))) {
          return require(modulePath);
        }
      }
    }
  } catch (_) {}

  return null;
}

async function ensurePlaywright() {
  let playwright = findPlaywright();
  if (playwright) return playwright;

  const npm = commandPath('npm');
  if (!npm) {
    throw new Error(
      '未找到 Playwright，也未检测到 npm。请安装 npm 和 playwright。'
    );
  }

  log('未找到 Playwright，尝试安装到脚本目录');

  const env = {
    ...process.env,
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: '1',
  };

  try {
    await run(npm, [
      'install',
      '--no-save',
      '--no-audit',
      '--no-fund',
      '--legacy-peer-deps',
      '--prefix',
      ROOT,
      'playwright',
    ], 180000);
  } catch (error) {
    log(`默认 npm 源安装失败：${error.message}`);

    await run(npm, [
      'install',
      '--no-save',
      '--no-audit',
      '--no-fund',
      '--legacy-peer-deps',
      '--prefix',
      ROOT,
      '--registry=https://registry.npmmirror.com',
      'playwright',
    ], 180000);
  }

  playwright = findPlaywright();

  if (!playwright) {
    throw new Error('Playwright 安装后仍无法加载');
  }

  return playwright;
}

async function ensureChromium() {
  let executable = findChromium();
  if (executable) return executable;

  const osType = detectOS();
  log(`未找到系统 Chromium，检测到系统：${osType}`);

  if (osType === 'unknown') {
    throw new Error(
      '无法识别系统包管理器。请预装 Chromium，并通过 CHROMIUM_PATH 指定路径。'
    );
  }

  // 系统包安装仅在 root 环境执行，避免权限错误和交互式 sudo 卡住。
  if (typeof process.getuid === 'function' && process.getuid() !== 0) {
    throw new Error(
      '当前用户没有 root 权限，无法自动安装系统 Chromium。请在镜像构建阶段安装。'
    );
  }

  if (osType === 'alpine') {
    await run('apk', [
      'add', '--no-cache',
      'chromium',
      'nss',
      'freetype',
      'harfbuzz',
      'ca-certificates',
      'ttf-freefont',
    ], 180000);
  } else {
    await run('apt-get', ['update'], 180000);

    try {
      await run('apt-get', [
        'install', '-y', '--no-install-recommends',
        'chromium',
        'ca-certificates',
        'fonts-liberation',
      ], 180000);
    } catch (error) {
      log(`chromium 安装失败：${error.message}，尝试 chromium-browser`);

      await run('apt-get', [
        'install', '-y', '--no-install-recommends',
        'chromium-browser',
        'ca-certificates',
        'fonts-liberation',
      ], 180000);
    }
  }

  executable = findChromium();

  if (!executable) {
    throw new Error(
      '安装完成后未找到 Chromium，请检查软件源、包名和实际安装路径。'
    );
  }

  return executable;
}

async function runOnce(chromiumPath, playwright) {
  const start = Date.now();

  const result = {
    url: URL,
    status: '未知',
    detail: '',
    duration_s: 0,
  };

  const browser = await playwright.chromium.launch({
    executablePath: chromiumPath,
    headless: true,
    timeout: NAV_TIMEOUT,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--disable-extensions',
      '--disable-background-networking',
      '--disable-sync',
      '--disable-default-apps',
      '--blink-settings=imagesEnabled=false',
    ],
  });

  browserInstance = browser;

  try {
    const context = await browser.newContext({
      viewport: { width: 800, height: 600 },
    });

    const page = await context.newPage();
    page.setDefaultTimeout(NAV_TIMEOUT);
    page.setDefaultNavigationTimeout(NAV_TIMEOUT);

    await page.route('**/*', route => {
      const type = route.request().resourceType();

      if (['image', 'font', 'media'].includes(type)) {
        return route.abort();
      }

      return route.continue();
    });

    log(`正在打开：${URL}`);

    await page.goto(URL, {
      waitUntil: 'domcontentloaded',
      timeout: NAV_TIMEOUT,
    });

    await page.waitForTimeout(4000);

    async function isSleeping() {
      const text = await page.locator('body').innerText().catch(() => '');
      return /gone to sleep|get this app back up|Zzz{2,}/i.test(text);
    }

    if (!(await isSleeping())) {
      result.status = '本来就是活的';
      result.detail = '未检测到 Streamlit 休眠提示';
    } else {
      result.detail = '检测到休眠页';

      const button = page.getByRole('button', {
        name: /get this app back up/i,
      });

      if (await button.count()) {
        await button.first().click();
        result.detail += '，已点击唤醒按钮';
      } else {
        result.detail += '，未找到唤醒按钮';
      }

      let waited = 0;
      let awake = false;

      while (waited < WAKE_WAIT) {
        await sleep(POLL_SECONDS * 1000);
        waited += POLL_SECONDS;

        if (waited % RELOAD_SECONDS === 0) {
          try {
            await page.reload({
              waitUntil: 'domcontentloaded',
              timeout: NAV_TIMEOUT,
            });
          } catch (error) {
            log(`刷新失败：${error.message}`);
          }
        }

        if (!(await isSleeping())) {
          awake = true;
          break;
        }

        log(`等待唤醒：${waited}/${WAKE_WAIT}s`);
      }

      result.status = awake ? '唤醒成功' : '唤醒超时';
      result.detail += awake
        ? `，等待 ${waited}s 后休眠提示消失`
        : `，等待 ${waited}s 后仍检测到休眠提示`;
    }

    if (HOLD_SECONDS > 0) {
      log(`保持浏览器连接 ${HOLD_SECONDS}s`);
      await page.waitForTimeout(HOLD_SECONDS * 1000);
    }
  } finally {
    browserInstance = null;
    await browser.close().catch(() => {});
  }

  result.duration_s = Math.round((Date.now() - start) / 100) / 10;
  return result;
}

async function main() {
  log(`Node.js：${process.version}`);
  log(`平台：${process.platform} / ${os.arch()}`);
  log(`系统：${detectOS()}`);

  const chromiumPath = await ensureChromium();
  log(`浏览器路径：${chromiumPath}`);

  const playwright = await ensurePlaywright();

  let lastError;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await runOnce(chromiumPath, playwright);
    } catch (error) {
      lastError = error;
      log(`第 ${attempt}/${MAX_RETRIES} 次尝试失败：${error.stack || error.message}`);

      if (attempt < MAX_RETRIES) await sleep(3000);
    }
  }

  return {
    url: URL,
    status: '异常',
    detail: lastError?.message || '未知错误',
    duration_s: 0,
  };
}

function stopChildren() {
  stopping = true;

  if (browserInstance) {
    browserInstance.close().catch(() => {});
    browserInstance = null;
  }

  for (const child of childProcesses) {
    try {
      child.kill('SIGTERM');
    } catch (_) {}
  }
}

async function mainWithTimeout() {
  let timer;

  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      stopChildren();
      reject(new Error(`总执行时间超过 ${TOTAL_TIMEOUT}s`));
    }, TOTAL_TIMEOUT * 1000);
  });

  try {
    return await Promise.race([main(), timeout]);
  } finally {
    clearTimeout(timer);
  }
}

async function entry() {
  let result;

  try {
    result = await mainWithTimeout();
  } catch (error) {
    result = {
      url: URL,
      status: stopping ? '执行超时' : '执行失败',
      detail: error.message,
      duration_s: 0,
    };
  }

  console.log('\n========== Streamlit 保活结果 ==========');
  console.log(`目标：${result.url}`);
  console.log(`状态：${result.status}`);
  console.log(`耗时：${result.duration_s}s`);
  console.log(`详情：${result.detail}`);
  console.log('========================================');

  // 不 require 青龙通知模块。
  // 当前青龙若启用了会在脚本启动前执行的通知 preload，
  // 该 preload 自身的兼容性错误必须在青龙运行环境中修复。
  process.exitCode = ['异常', '执行超时', '执行失败'].includes(result.status)
    ? 1
    : 0;
}

process.on('SIGTERM', stopChildren);
process.on('SIGINT', stopChildren);

entry().catch(error => {
  console.error('[致命错误]', error.stack || error);
  stopChildren();
  process.exitCode = 1;
});
```
