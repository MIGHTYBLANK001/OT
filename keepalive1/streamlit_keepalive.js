'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const CONFIG = {
  url:
    process.env.STREAMLIT_URL ||
    'https://l2uetmksgajvryi4qmegvn.streamlit.app/',

  // 首次环境安装总预算：10 分钟
  installTimeout: 10 * 60 * 1000,

  // 整个任务硬超时：15 分钟
  totalTimeout: 15 * 60 * 1000,

  // 页面唤醒最长等待时间
  wakeTimeout: 5 * 60 * 1000,

  pollInterval: 5000,
  reloadInterval: 30000,

  // 页面恢复后继续停留
  holdTime: 60000,

  // 通知最长等待时间
  notifyTimeout: 30000
};

const BASE = __dirname;

// 使用脚本路径生成独立锁名，避免不同脚本互相影响
const LOCK_FILE = path.join(
  '/tmp',
  `streamlit-keepalive-${Buffer.from(__filename)
    .toString('hex')
    .slice(-32)}.lock`
);

const children = new Set();

let browser = null;
let finished = false;
let deadlineTimer = null;
let startedAt = Date.now();
let lockOwned = false;

/**
 * 输出带时间的日志。
 */
function log(message) {
  console.log(`[${new Date().toLocaleString()}] ${message}`);
}

/**
 * 等待指定毫秒数。
 */
function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 判断文件是否存在且可执行。
 */
function executable(file) {
  if (!file) return false;

  try {
    fs.accessSync(file, fs.constants.X_OK);
    return true;
  } catch (_) {
    return false;
  }
}

/**
 * 返回截止时间前剩余的毫秒数。
 */
function remainingTime(deadline) {
  const remaining = deadline - Date.now();

  if (remaining <= 0) {
    throw new Error('环境安装时间已达到 10 分钟上限');
  }

  return remaining;
}

/**
 * 判断指定 PID 是否仍在运行。
 */
function processExists(pid) {
  if (!Number.isInteger(pid) || pid <= 0) {
    return false;
  }

  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    // EPERM 表示进程存在，但当前用户无权发送信号
    return error && error.code === 'EPERM';
  }
}

/**
 * 获取跨进程单实例锁。
 *
 * 青龙若同时启动本脚本多次，只有第一个实例能够获得锁。
 * 其余实例直接正常退出，不重复打开浏览器或发送通知。
 */
function acquireLock() {
  try {
    const fd = fs.openSync(LOCK_FILE, 'wx');

    fs.writeFileSync(
      fd,
      JSON.stringify({
        pid: process.pid,
        script: __filename,
        startedAt: new Date().toISOString()
      }),
      'utf8'
    );

    fs.closeSync(fd);
    lockOwned = true;

    log(`已获得单实例锁：${LOCK_FILE}`);
    return true;
  } catch (error) {
    if (!error || error.code !== 'EEXIST') {
      throw new Error(`创建单实例锁失败：${error.message}`);
    }
  }

  // 锁文件已存在，检查持锁进程是否仍在运行
  let lockInfo = null;

  try {
    lockInfo = JSON.parse(fs.readFileSync(LOCK_FILE, 'utf8'));
  } catch (_) {
    log('检测到无效锁文件，准备清理');
  }

  if (lockInfo && processExists(Number(lockInfo.pid))) {
    log(
      `检测到脚本已在运行，PID：${lockInfo.pid}，本次重复启动直接退出`
    );

    return false;
  }

  // PID 不存在或锁内容无效，说明这是异常退出留下的失效锁
  log('检测到失效锁，正在清理');

  try {
    fs.unlinkSync(LOCK_FILE);
  } catch (error) {
    if (error.code !== 'ENOENT') {
      throw new Error(`清理失效锁失败：${error.message}`);
    }
  }

  // 清理后重新以原子方式获取一次
  try {
    const fd = fs.openSync(LOCK_FILE, 'wx');

    fs.writeFileSync(
      fd,
      JSON.stringify({
        pid: process.pid,
        script: __filename,
        startedAt: new Date().toISOString()
      }),
      'utf8'
    );

    fs.closeSync(fd);
    lockOwned = true;

    log(`已重新获得单实例锁：${LOCK_FILE}`);
    return true;
  } catch (error) {
    if (error && error.code === 'EEXIST') {
      log('其他实例已抢先获得锁，本次启动直接退出');
      return false;
    }

    throw new Error(`重新创建单实例锁失败：${error.message}`);
  }
}

/**
 * 释放单实例锁。
 *
 * 释放前再次核对 PID，避免删除其他进程后来创建的锁。
 */
function releaseLock() {
  if (!lockOwned) return;

  try {
    let lockInfo = null;

    try {
      lockInfo = JSON.parse(fs.readFileSync(LOCK_FILE, 'utf8'));
    } catch (_) {}

    if (!lockInfo || Number(lockInfo.pid) === process.pid) {
      fs.unlinkSync(LOCK_FILE);
      log('已释放单实例锁');
    }
  } catch (error) {
    if (error.code !== 'ENOENT') {
      log(`释放单实例锁失败：${error.message}`);
    }
  } finally {
    lockOwned = false;
  }
}

/**
 * 执行系统命令，支持超时和子进程清理。
 */
function run(command, args = [], timeout = 60000) {
  return new Promise((resolve, reject) => {
    let child;
    let output = '';
    let timedOut = false;
    let settled = false;
    let forceTimer = null;

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

      forceTimer = setTimeout(() => {
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

      if (forceTimer) {
        clearTimeout(forceTimer);
      }

      children.delete(child);

      if (error) {
        reject(error);
      } else {
        resolve(result);
      }
    }

    function collect(data) {
      const value = data.toString();

      output += value;

      // 仅保留最后 20 KB，避免安装输出过多占用内存
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

    child.once('error', error => {
      finish(error);
    });

    child.once('close', code => {
      if (timedOut) {
        finish(new Error(`命令执行超时：${command}`));
        return;
      }

      if (code === 0) {
        finish(null, output);
        return;
      }

      finish(
        new Error(
          `${command} 退出码 ${code}\n${output.slice(-3000)}`
        )
      );
    });
  });
}

/**
 * 查找系统 Chromium。
 */
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

  return candidates.find(executable) || null;
}

/**
 * 加载已有 Playwright。
 */
function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_PATH,
    path.join(BASE, 'node_modules', 'playwright'),
    path.join(BASE, 'node_modules', 'playwright-core')
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      const playwright = require(candidate);

      if (
        playwright.chromium &&
        typeof playwright.chromium.launch === 'function'
      ) {
        return playwright;
      }
    } catch (_) {}
  }

  return null;
}

/**
 * 安装 Chromium。
 */
async function installChromium(deadline) {
  if (findChromium()) {
    log('已存在 Chromium，跳过安装');
    return;
  }

  if (
    typeof process.getuid === 'function' &&
    process.getuid() !== 0
  ) {
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
        [
          'export DEBIAN_FRONTEND=noninteractive',
          'apt-get update -y',
          '(apt-get install -y chromium || ' +
            'apt-get install -y chromium-browser)'
        ].join(' && ')
      ],
      remainingTime(deadline)
    );
  } else {
    throw new Error(
      '不支持当前系统，仅支持 Alpine 和 Debian 系'
    );
  }

  if (!findChromium()) {
    throw new Error(
      'Chromium 安装命令已结束，但没有找到可执行文件'
    );
  }

  log('Chromium 安装完成');
}

/**
 * 安装或加载 Playwright。
 */
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
      '--prefix',
      BASE,
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

/**
 * 准备浏览器运行环境。
 */
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

/**
 * 获取页面正文。
 */
async function getPageText(page) {
  try {
    return await page.locator('body').innerText();
  } catch (_) {
    return '';
  }
}

/**
 * 尝试点击 Streamlit 唤醒按钮。
 */
async function clickWakeButton(page) {
  const buttons = page.locator('button');
  const count = await buttons.count();

  for (let index = 0; index < count; index++) {
    const button = buttons.nth(index);
    let label = '';

    try {
      label = await button.innerText();
    } catch (_) {}

    if (/get this app back up/i.test(label)) {
      await button.click();
      log(`已点击唤醒按钮：${label.trim()}`);
      return true;
    }
  }

  try {
    const button = page.getByText(
      /yes,?\s*get this app back up/i
    );

    if (await button.count()) {
      await button.first().click();
      log('已点击 Streamlit 唤醒按钮');
      return true;
    }
  } catch (_) {}

  return false;
}

/**
 * 等待 Streamlit 页面退出休眠状态。
 */
async function waitForWake(page, sleepPattern, waitingPattern) {
  const wakeDeadline = Date.now() + CONFIG.wakeTimeout;
  let lastReload = Date.now();

  while (Date.now() < wakeDeadline) {
    await delay(CONFIG.pollInterval);

    const text = await getPageText(page);

    if (
      !sleepPattern.test(text) &&
      !waitingPattern.test(text)
    ) {
      log('页面已退出休眠状态');
      return;
    }

    if (Date.now() - lastReload < CONFIG.reloadInterval) {
      continue;
    }

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

  throw new Error('等待唤醒超时，页面仍未恢复');
}

/**
 * 执行一次完整保活任务。
 */
async function runOnce() {
  const { chromium, playwright } =
    await prepareEnvironment();

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
    viewport: {
      width: 1365,
      height: 900
    }
  });

  page.setDefaultNavigationTimeout(60000);
  page.setDefaultTimeout(10000);

  log('正在打开 Streamlit 页面');

  const response = await page.goto(CONFIG.url, {
    waitUntil: 'commit',
    timeout: 30000
  });

  log(
    `页面响应状态：${response ? response.status() : '未知'}`
  );

  // 给页面脚本留出执行时间
  await delay(5000);

  const sleepPattern =
    /gone to sleep|get this app back up|z{3,}/i;

  const waitingPattern =
    /waking up|please wait/i;

  const text = await getPageText(page);

  if (sleepPattern.test(text)) {
    log('检测到休眠页面，尝试唤醒');

    const clicked = await clickWakeButton(page);

    if (!clicked) {
      throw new Error('未找到 Streamlit 唤醒按钮');
    }

    await waitForWake(
      page,
      sleepPattern,
      waitingPattern
    );
  } else {
    log('页面未检测到休眠提示');
  }

  log(
    `继续保持页面运行 ${CONFIG.holdTime / 1000} 秒`
  );

  await delay(CONFIG.holdTime);

  log('保活流程完成');
}

/**
 * 发送青龙通知。
 */
async function sendQinglongNotify(title, content) {
  const candidates = [
    '/ql/data/scripts/sendNotify.js',
    '/ql/scripts/sendNotify.js'
  ];

  for (const file of candidates) {
    if (!fs.existsSync(file)) {
      continue;
    }

    try {
      const moduleValue = require(file);

      const notify =
        moduleValue.sendNotify ||
        moduleValue.default ||
        moduleValue;

      if (typeof notify !== 'function') {
        log(`通知模块没有导出 sendNotify 函数：${file}`);
        continue;
      }

      log(`正在通过 ${file} 发送通知`);

      await Promise.race([
        Promise.resolve().then(() =>
          notify(title, content)
        ),
        delay(CONFIG.notifyTimeout).then(() => {
          throw new Error('通知发送等待超时');
        })
      ]);

      log('通知函数已执行完成');
      return true;
    } catch (error) {
      log(
        `通知尝试失败：${file}；${error.message}`
      );
    }
  }

  log(
    '未能通过候选路径发送通知，请检查青龙 sendNotify.js'
  );

  return false;
}

/**
 * 结束全部子进程。
 */
function stopChildren(signal = 'SIGTERM') {
  for (const child of children) {
    try {
      child.kill(signal);
    } catch (_) {}
  }
}

/**
 * 关闭浏览器。
 */
async function closeBrowser() {
  if (!browser) return;

  const currentBrowser = browser;
  browser = null;

  try {
    await Promise.race([
      currentBrowser.close(),
      delay(3000)
    ]);
  } catch (_) {}
}

/**
 * 统一结束处理。
 */
async function finish(status, detail, exitCode) {
  if (finished) return;

  finished = true;

  if (deadlineTimer) {
    clearTimeout(deadlineTimer);
    deadlineTimer = null;
  }

  stopChildren('SIGTERM');
  await closeBrowser();

  const elapsed = Math.round(
    (Date.now() - startedAt) / 1000
  );

  const content = [
    `目标：${CONFIG.url}`,
    `状态：${status}`,
    `耗时：${elapsed}s`,
    detail ? `详情：${detail}` : ''
  ]
    .filter(Boolean)
    .join('\n');

  console.log(
    '\n========== Streamlit 保活结果 =========='
  );
  console.log(content);
  console.log(
    '========================================'
  );

  // 通知失败不得覆盖真实任务结果
  await sendQinglongNotify(
    `Streamlit 保活${status}`,
    content
  );

  try {
    if (typeof globalThis.daidaiDone === 'function') {
      globalThis.daidaiDone();
      log('已通知青龙任务结束检测器');
    }
  } catch (error) {
    log(`结束检测标记调用失败：${error.message}`);
  }

  releaseLock();
  process.exitCode = exitCode;
}

/**
 * 主任务。
 */
async function main() {
  startedAt = Date.now();

  if (!acquireLock()) {
    process.exitCode = 0;
    return;
  }

  deadlineTimer = setTimeout(() => {
    log(
      `任务达到 ${CONFIG.totalTimeout / 60000} 分钟总超时上限`
    );

    stopChildren('SIGKILL');

    finish(
      '执行失败',
      `任务总超时：${CONFIG.totalTimeout / 60000} 分钟`,
      1
    ).finally(() => {
      // 防止第三方通知模块留下悬挂句柄
      process.exit(1);
    });
  }, CONFIG.totalTimeout);

  try {
    await runOnce();
    await finish('执行成功', '', 0);
  } catch (error) {
    const detail =
      error && error.message
        ? error.message
        : String(error);

    console.error(detail);

    await finish(
      '执行失败',
      detail,
      1
    );
  }
}

/**
 * 信号处理。
 */
function handleSignal(signal) {
  finish(
    '执行失败',
    `任务收到 ${signal} 信号`,
    1
  ).finally(() => {
    process.exit(1);
  });
}

process.once('SIGTERM', () => {
  handleSignal('SIGTERM');
});

process.once('SIGINT', () => {
  handleSignal('SIGINT');
});

// 同一 Node.js 进程内防止重复加载启动
if (globalThis.__STREAMLIT_KEEPALIVE_STARTED__) {
  log('检测到脚本在当前进程中重复加载，已阻止重复执行');
} else {
  globalThis.__STREAMLIT_KEEPALIVE_STARTED__ = true;

  main().catch(error => {
    const detail =
      error && error.message
        ? error.message
        : String(error);

    console.error(`未处理异常：${detail}`);

    releaseLock();
    process.exitCode = 1;
  });
}
