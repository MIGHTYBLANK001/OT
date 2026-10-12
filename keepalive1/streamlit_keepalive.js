'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const CONFIG = {
  url: process.env.STREAMLIT_URL ||
    'https://l2uetmksgajvryi4qmegvn.streamlit.app/',

  // 首次环境安装的总预算：5 分钟
  installTimeout: 5 * 60 * 1000,

  // 整个任务的硬超时：10 分钟
  totalTimeout: 10 * 60 * 1000,

  // 页面唤醒等待
  wakeTimeout: 5 * 60 * 1000,
  pollInterval: 5000,
  reloadInterval: 30000,

  // 页面唤醒后继续停留
  holdTime: 60000,

  // 通知最多等待 8 秒
  notifyTimeout: 8000
};

const BASE = __dirname;
const children = new Set();

let browser = null;
let finished = false;
let deadlineTimer = null;
let startedAt = Date.now();

function log(message) {
  console.log(`[${new Date().toLocaleString()}] ${message}`);
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function executable(file) {
  if (!file) return false;

  try {
    fs.accessSync(file, fs.constants.X_OK);
    return true;
  } catch (_) {
    return false;
  }
}

function remainingTime(deadline) {
  const remaining = deadline - Date.now();

  if (remaining <= 0) {
    throw new Error('环境安装时间已达到 5 分钟上限');
  }

  return remaining;
}

// 执行系统命令，支持超时和子进程清理
function run(command, args = [], timeout = 60000) {
  return new Promise((resolve, reject) => {
    let child;
    let output = '';
    let timedOut = false;
    let settled = false;

    log(`执行：${command} ${args.join(' ')}`);

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
      timedOut = true;

      try {
        child.kill('SIGTERM');
      } catch (_) {}

      const forceTimer = setTimeout(() => {
        try {
          child.kill('SIGKILL');
        } catch (_) {}
      }, 2000);

      forceTimer.unref();
    }, Math.max(1, timeout));

    function finish(error, result) {
      if (settled) return;

      settled = true;
      clearTimeout(timer);
      children.delete(child);

      if (error) reject(error);
      else resolve(result);
    }

    function collect(data) {
      const value = data.toString();
      output += value;

      if (output.length > 20000) {
        output = output.slice(-20000);
      }

      return value;
    }

    child.stdout.on('data', data => {
      process.stdout.write(collect(data));
    });

    child.stderr.on('data', data => {
      process.stderr.write(collect(data));
    });

    child.on('error', error => {
      finish(error);
    });

    child.on('close', code => {
      if (timedOut) {
        finish(new Error(`命令执行超时：${command}`));
      } else if (code === 0) {
        finish(null, output);
      } else {
        finish(new Error(
          `${command} 退出码 ${code}\n${output.slice(-3000)}`
        ));
      }
    });
  });
}

// 查找系统 Chromium
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
    if (executable(file)) return file;
  }

  return null;
}

// 查找已有 Playwright
function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_PATH,
    path.join(BASE, 'node_modules', 'playwright'),
    path.join(BASE, 'node_modules', 'playwright-core')
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      const mod = require(candidate);

      if (mod.chromium && typeof mod.chromium.launch === 'function') {
        return mod;
      }
    } catch (_) {}
  }

  return null;
}

// 安装 Chromium：安装命令共享同一个 5 分钟预算
async function installChromium(deadline) {
  if (findChromium()) {
    log('已存在 Chromium，跳过安装');
    return;
  }

  if (typeof process.getuid === 'function' &&
      process.getuid() !== 0) {
    throw new Error(
      '安装 Chromium 需要 root 权限，请以 root 运行青龙容器'
    );
  }

  const alpine = fs.existsSync('/etc/alpine-release');
  const debian = fs.existsSync('/etc/debian_version');

  if (alpine) {
    log('检测到 Alpine，开始安装 Chromium');

    await run(
      'apk',
      ['add', '--no-cache', 'chromium'],
      remainingTime(deadline)
    );
  } else if (debian) {
    log('检测到 Debian，开始安装 Chromium');

    await run(
      'sh',
      [
        '-c',
        'export DEBIAN_FRONTEND=noninteractive; ' +
        'apt-get update -y && ' +
        '(apt-get install -y chromium || ' +
        'apt-get install -y chromium-browser)'
      ],
      remainingTime(deadline)
    );
  } else {
    throw new Error('不支持当前系统，仅支持 Alpine 和 Debian 系');
  }

  if (!findChromium()) {
    throw new Error(
      'Chromium 安装命令已结束，但没有找到可执行文件'
    );
  }

  log('Chromium 安装完成');
}

// 安装 Playwright，使用剩余的安装预算
async function ensurePlaywright(deadline) {
  let playwright = loadPlaywright();

  if (playwright) {
    log('Playwright 已安装，跳过安装');
    return playwright;
  }

  log('开始安装 Playwright');

  await run(
    'npm',
    [
      'install',
      '--prefix', BASE,
      '--no-save',
      '--no-audit',
      '--no-fund',
      'playwright'
    ],
    remainingTime(deadline)
  );

  playwright = loadPlaywright();

  if (!playwright) {
    throw new Error('Playwright 安装完成，但模块加载失败');
  }

  log('Playwright 安装完成');
  return playwright;
}

// 仅在确实需要安装依赖时启动 5 分钟安装预算
async function prepareEnvironment() {
  let chromium = findChromium();
  let playwright = loadPlaywright();

  if (chromium && playwright) {
    log('运行环境已就绪，跳过安装');
    return { chromium, playwright };
  }

  const deadline = Date.now() + CONFIG.installTimeout;

  if (!chromium) {
    await installChromium(deadline);
    chromium = findChromium();
  }

  if (!playwright) {
    playwright = await ensurePlaywright(deadline);
  }

  if (!chromium || !playwright) {
    throw new Error('运行环境初始化失败');
  }

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

  await delay(2000);

  const sleepPattern =
    /gone to sleep|get this app back up|z{3,}/i;

  const waitingPattern = /waking up|please wait/i;

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

      if (/get this app back up/i.test(label)) {
        await button.click();
        clicked = true;
        log(`已点击唤醒按钮：${label.trim()}`);
        break;
      }
    }

    if (!clicked) {
      try {
        const button = page.getByText(
          /yes,?\s*get this app back up/i
        );

        if (await button.count()) {
          await button.first().click();
          clicked = true;
        }
      } catch (_) {}
    }

    if (!clicked) {
      throw new Error('未找到 Streamlit 唤醒按钮');
    }

    const wakeDeadline = Date.now() + CONFIG.wakeTimeout;
    let lastReload = Date.now();
    let awake = false;

    while (Date.now() < wakeDeadline) {
      await delay(CONFIG.pollInterval);

      text = await getPageText();

      if (!sleepPattern.test(text) && !waitingPattern.test(text)) {
        awake = true;
        log('页面已退出休眠状态');
        break;
      }

      if (Date.now() - lastReload >= CONFIG.reloadInterval) {
        log('仍在等待唤醒，刷新页面');

        try {
          await page.reload({
            waitUntil: 'domcontentloaded',
            timeout: 30000
          });
        } catch (error) {
          log(`刷新未完成：${error.message}`);
        }

        lastReload = Date.now();
      }
    }

    if (!awake) {
      throw new Error('等待唤醒超时，页面仍未恢复');
    }
  } else {
    log('页面未检测到休眠提示');
  }

  log(`继续保持页面运行 ${CONFIG.holdTime / 1000} 秒`);
  await delay(CONFIG.holdTime);

  log('保活流程完成');
}

// 发送青龙通知：支持常见路径及模块导出格式
async function sendQinglongNotify(title, content) {
  const candidates = [
    '/ql/data/scripts/sendNotify.js',
    '/ql/scripts/sendNotify.js'
  ];

  for (const file of candidates) {
    if (!fs.existsSync(file)) continue;

    try {
      const mod = require(file);
      const notify =
        mod.sendNotify ||
        mod.default ||
        mod;

      if (typeof notify !== 'function') {
        log(`通知模块没有导出 sendNotify 函数：${file}`);
        continue;
      }

      log(`正在通过 ${file} 发送通知`);

      await Promise.race([
        Promise.resolve().then(() => notify(title, content)),
        delay(CONFIG.notifyTimeout).then(() => {
          throw new Error('通知发送等待超时');
        })
      ]);

      log('通知函数已执行完成');
      return true;
    } catch (error) {
      log(`通知尝试失败：${file}；${error.message}`);
    }
  }

  log('未能通过候选路径发送通知，请检查青龙 sendNotify.js');
  return false;
}

// 统一结束处理
async function finish(status, detail, exitCode) {
  if (finished) return;
  finished = true;

  if (deadlineTimer) clearTimeout(deadlineTimer);

  // 先清理浏览器与命令进程
  for (const child of children) {
    try {
      child.kill('SIGTERM');
    } catch (_) {}
  }

  if (browser) {
    try {
      await Promise.race([
        browser.close(),
        delay(3000)
      ]);
    } catch (_) {}

    browser = null;
  }

  const elapsed = Math.round((Date.now() - startedAt) / 1000);

  const content = [
    `目标：${CONFIG.url}`,
    `状态：${status}`,
    `耗时：${elapsed}s`,
    detail ? `详情：${detail}` : ''
  ].filter(Boolean).join('\n');

  console.log('\n========== Streamlit 保活结果 ==========');
  console.log(content);
  console.log('========================================');

  // 通知失败不能覆盖真实的保活结果
  await sendQinglongNotify(`Streamlit 保活${status}`, content);

  // 通知青龙：脚本的主要工作已经结束
  try {
    if (typeof globalThis.daidaiDone === 'function') {
      globalThis.daidaiDone();
      log('已通知青龙任务结束检测器');
    }
  } catch (error) {
    log(`结束检测标记调用失败：${error.message}`);
  }

  process.exitCode = exitCode;
}

async function main() {
  startedAt = Date.now();

  // 10 分钟硬超时
  deadlineTimer = setTimeout(() => {
    log('任务达到 10 分钟总超时上限');

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

    finish(
      '执行失败',
      '任务总超时：10 分钟',
      1
    ).finally(() => {
      // 超时后仍有悬挂句柄时，确保任务不会无限运行
      process.exit(1);
    });
  }, CONFIG.totalTimeout);

  try {
    await runOnce();

    if (!finished) {
      await finish('执行成功', '', 0);
    }
  } catch (error) {
    if (!finished) {
      const detail =
        error && error.message ? error.message : String(error);

      console.error(detail);
      await finish('执行失败', detail, 1);
    }
  }
}

process.on('SIGTERM', () => {
  finish('执行失败', '任务收到 SIGTERM 信号', 1)
    .finally(() => process.exit(1));
});

process.on('SIGINT', () => {
  finish('执行失败', '任务收到 SIGINT 信号', 1)
    .finally(() => process.exit(1));
});

main();
