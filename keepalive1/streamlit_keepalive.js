'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');

const CONFIG = {
  url: process.env.STREAMLIT_URL ||
    'https://l2uetmksgajvryi4qmegvn.streamlit.app/',
  installTimeout: 5 * 60 * 1000,
  totalTimeout: 10 * 60 * 1000,
  wakeTimeout: 5 * 60 * 1000,
  pollInterval: 5000,
  holdTime: 60000,
  reloadInterval: 30000
};

const BASE = __dirname;
const children = new Set();
let browser = null;
let finished = false;

function log(message) {
  console.log(`[${new Date().toLocaleString()}] ${message}`);
}

function exists(file) {
  try {
    fs.accessSync(file, fs.constants.X_OK);
    return true;
  } catch (_) {
    return false;
  }
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function run(command, args = [], timeout = CONFIG.installTimeout) {
  return new Promise((resolve, reject) => {
    log(`执行：${command} ${args.join(' ')}`);

    let child;
    let output = '';

    try {
      child = spawn(command, args, {
        cwd: BASE,
        env: process.env,
        stdio: ['ignore', 'pipe', 'pipe']
      });
    } catch (error) {
      reject(error);
      return;
    }

    children.add(child);

    const timer = setTimeout(() => {
      output += '\n命令执行超时';
      child.kill('SIGTERM');

      const killTimer = setTimeout(() => {
        try {
          child.kill('SIGKILL');
        } catch (_) {}
      }, 3000);

      killTimer.unref();
    }, timeout);

    child.stdout.on('data', data => {
      const text = data.toString();
      output += text;
      if (output.length > 12000) output = output.slice(-12000);
      process.stdout.write(text);
    });

    child.stderr.on('data', data => {
      const text = data.toString();
      output += text;
      if (output.length > 12000) output = output.slice(-12000);
      process.stderr.write(text);
    });

    child.on('error', error => {
      clearTimeout(timer);
      children.delete(child);
      reject(error);
    });

    child.on('close', code => {
      clearTimeout(timer);
      children.delete(child);

      if (output.includes('命令执行超时')) {
        reject(new Error(`命令执行超时：${command}`));
      } else if (code === 0) {
        resolve(output);
      } else {
        reject(new Error(
          `${command} 退出码 ${code}\n${output.slice(-3000)}`
        ));
      }
    });
  });
}

function findChromium() {
  const candidates = [
    process.env.CHROMIUM_PATH,
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/lib/chromium/chromium',
    '/usr/lib/chromium-browser/chromium-browser'
  ].filter(Boolean);

  for (const file of candidates) {
    if (exists(file)) return file;
  }

  return null;
}

function loadPlaywright() {
  const candidates = [
    path.join(BASE, 'node_modules', 'playwright'),
    path.join(BASE, 'node_modules', 'playwright-core'),
    process.env.PLAYWRIGHT_PATH || ''
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (_) {}
  }

  return null;
}

async function installChromium() {
  if (findChromium()) {
    log('已检测到系统 Chromium，跳过安装');
    return;
  }

  const alpine = fs.existsSync('/etc/alpine-release');
  const debian = fs.existsSync('/etc/debian_version');

  if (typeof process.getuid === 'function' && process.getuid() !== 0) {
    throw new Error('安装 Chromium 需要 root 权限，请以 root 运行青龙容器');
  }

  if (alpine) {
    log('Alpine 系统：安装 Chromium，最多等待 5 分钟');
    await run('apk', ['add', '--no-cache', 'chromium']);
  } else if (debian) {
    log('Debian 系统：安装 Chromium，最多等待 5 分钟');
    await run('sh', [
      '-c',
      'export DEBIAN_FRONTEND=noninteractive; ' +
      'apt-get update -y && ' +
      '(apt-get install -y chromium || ' +
      'apt-get install -y chromium-browser)'
    ]);
  } else {
    throw new Error('暂不支持此系统：仅支持 Alpine 和 Debian 系');
  }

  if (!findChromium()) {
    throw new Error('安装命令完成，但没有找到 Chromium 可执行文件');
  }
}

async function ensurePlaywright() {
  let playwright = loadPlaywright();

  if (playwright) {
    log('已检测到 Playwright，跳过安装');
    return playwright;
  }

  log('安装 Playwright，最多等待 5 分钟');

  await run('npm', [
    'install',
    '--prefix', BASE,
    '--no-save',
    '--no-audit',
    '--no-fund',
    'playwright'
  ], CONFIG.installTimeout);

  playwright = loadPlaywright();

  if (!playwright) {
    throw new Error('Playwright 安装完成，但加载失败');
  }

  return playwright;
}

async function prepareEnvironment() {
  let chromium = findChromium();

  if (!chromium) {
    await installChromium();
    chromium = findChromium();
  }

  const playwright = await ensurePlaywright();

  return { chromium, playwright };
}

async function runOnce() {
  const { chromium, playwright } = await prepareEnvironment();

  log(`目标：${CONFIG.url}`);
  log(`浏览器：${chromium}`);

  browser = await playwright.chromium.launch({
    headless: true,
    executablePath: chromium,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu'
    ]
  });

  const page = await browser.newPage({
    viewport: { width: 1365, height: 900 }
  });

  page.setDefaultNavigationTimeout(60000);
  page.setDefaultTimeout(10000);

  log('正在打开 Streamlit 页面');

  await page.goto(CONFIG.url, {
    waitUntil: 'domcontentloaded',
    timeout: 60000
  });

  await delay(3000);

  const sleepPattern =
    /gone to sleep|get this app back up|zzz{2,}/i;

  async function getPageText() {
    try {
      return await page.locator('body').innerText();
    } catch (_) {
      return '';
    }
  }

  let text = await getPageText();

  if (sleepPattern.test(text)) {
    log('检测到休眠页面，尝试唤醒');

    const buttons = page.locator('button');
    const count = await buttons.count();
    let clicked = false;

    for (let i = 0; i < count; i++) {
      const button = buttons.nth(i);
      let label = '';

      try {
        label = await button.innerText();
      } catch (_) {}

      if (/get this app back up|yes/i.test(label)) {
        await button.click();
        clicked = true;
        log(`已点击唤醒按钮：${label.trim()}`);
        break;
      }
    }

    if (!clicked) {
      const candidates = [
        page.getByText(/yes,?\s*get this app back up/i),
        page.getByText(/get this app back up/i)
      ];

      for (const candidate of candidates) {
        try {
          if (await candidate.count()) {
            await candidate.first().click();
            clicked = true;
            break;
          }
        } catch (_) {}
      }
    }

    if (!clicked) {
      throw new Error('检测到休眠页面，但没有找到可点击的唤醒按钮');
    }

    const start = Date.now();
    let lastReload = Date.now();

    while (Date.now() - start < CONFIG.wakeTimeout) {
      await delay(CONFIG.pollInterval);

      text = await getPageText();

      if (!sleepPattern.test(text) &&
          !/please wait|waking up/i.test(text)) {
        log('页面已退出休眠状态');
        break;
      }

      if (Date.now() - lastReload >= CONFIG.reloadInterval) {
        log('唤醒等待中，刷新页面');
        try {
          await page.reload({ waitUntil: 'domcontentloaded' });
        } catch (_) {}
        lastReload = Date.now();
      }
    }

    text = await getPageText();

    if (sleepPattern.test(text)) {
      throw new Error('等待唤醒超时，页面仍显示休眠提示');
    }
  } else {
    log('页面未检测到休眠提示');
  }

  log(`保持页面运行 ${Math.round(CONFIG.holdTime / 1000)} 秒`);
  await delay(CONFIG.holdTime);

  log('保活任务完成');
}

async function cleanup() {
  for (const child of children) {
    try {
      child.kill('SIGTERM');
    } catch (_) {}
  }

  if (browser) {
    try {
      await browser.close();
    } catch (_) {}
    browser = null;
  }
}

async function main() {
  const started = Date.now();
  let result = '执行成功';
  let exitCode = 0;
  let detail = '';

  const deadline = setTimeout(() => {
    if (finished) return;

    finished = true;
    console.error('\n总超时：任务运行达到 10 分钟上限');

    for (const child of children) {
      try {
        child.kill('SIGKILL');
      } catch (_) {}
    }

    if (browser) {
      try {
        browser.close();
      } catch (_) {}
    }

    console.log('\n========== Streamlit 保活结果 ==========');
    console.log(`目标：${CONFIG.url}`);
    console.log('状态：执行失败');
    console.log(`耗时：${Math.round((Date.now() - started) / 1000)}s`);
    console.log('详情：任务总超时（10 分钟）');
    console.log('========================================');
    process.exit(1);
  }, CONFIG.totalTimeout);

  try {
    await runOnce();
  } catch (error) {
    result = '执行失败';
    exitCode = 1;
    detail = error && error.message ? error.message : String(error);
    console.error(detail);
  } finally {
    if (!finished) {
      finished = true;
      clearTimeout(deadline);
      await cleanup();

      console.log('\n========== Streamlit 保活结果 ==========');
      console.log(`目标：${CONFIG.url}`);
      console.log(`状态：${result}`);
      console.log(`耗时：${Math.round((Date.now() - started) / 1000)}s`);
      if (detail) console.log(`详情：${detail}`);
      console.log('========================================');

      process.exitCode = exitCode;
    }
  }
}

process.on('SIGTERM', () => {
  cleanup().finally(() => process.exit(143));
});

process.on('SIGINT', () => {
  cleanup().finally(() => process.exit(130));
});

main();
