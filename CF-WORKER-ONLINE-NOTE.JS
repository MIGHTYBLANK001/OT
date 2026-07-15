export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const key = url.pathname === '/' ? 'default_note' : url.pathname;

    // 处理保存请求 (POST)
    if (request.method === 'POST') {
      const text = await request.text();
      await env.NOTES.put(key, text);
      return new Response('Saved');
    }

    // 获取当前存储的内容
    const value = await env.NOTES.get(key) || '';

    // 返回优化后的 HTML 页面
    const html = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>在线轻记事本 (720P)</title>
      <style>
        /* 1. 经典护眼豆沙绿背景 */
        body { 
          margin: 0; 
          padding: 30px 20px; 
          background-color: #DCEFE0; 
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          display: flex;
          justify-content: center;
          align-items: center;
          min-height: 100vh;
          box-sizing: border-box;
        }

        /* 2. 外层容器：最大限制在 720P 宽度 (1280px) */
        .container {
          width: 100%;
          max-width: 1280px; /* 720P 宽 */
          background: #C7EDCC; /* 标准豆沙绿 */
          border-radius: 12px;
          box-shadow: 0 12px 30px rgba(60, 90, 60, 0.15);
          padding: 24px;
          box-sizing: border-box;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          color: #2E4F33;
          font-weight: 600;
          font-size: 14px;
        }

        /* 3. 文本框：强制 16:9 比例 */
        textarea { 
          width: 100%; 
          /* 使用 aspect-ratio 属性锁定 16:9 比例 */
          aspect-ratio: 16 / 9; 
          background: #E1F3E5; /* 稍浅的豆沙绿，高对比度不刺眼 */
          color: #2E4F33; /* 暗绿色字体 */
          border: 1px solid #B2D8B9; 
          padding: 20px; 
          box-sizing: border-box; 
          font-size: 16px; 
          line-height: 1.6;
          border-radius: 8px; 
          resize: none; /* 锁定比例，禁止用户手动拉伸 */
          outline: none; 
          font-family: inherit;
          transition: border-color 0.2s;
        }
        textarea:focus {
          border-color: #7BB385;
        }

        /* 4. 底部工具栏与保存按钮 */
        .footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        #status { 
          color: #55825D; 
          font-size: 13px; 
          opacity: 0; 
          transition: opacity 0.3s; 
        }

        .btn-save {
          background-color: #4E8759;
          color: white;
          border: none;
          padding: 10px 20px;
          font-size: 14px;
          font-weight: bold;
          border-radius: 6px;
          cursor: pointer;
          transition: background 0.2s, transform 0.1s;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .btn-save:hover {
          background-color: #3D6B46;
        }
        .btn-save:active {
          transform: scale(0.97);
        }
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <span>在线编辑剪贴板 (720P 16:9 比例)</span>
          <span style="font-weight: normal; opacity: 0.7;">自动保存 / Ctrl+S</span>
        </div>
        
        <textarea id="pad" placeholder="在此输入内容...">${value}</textarea>
        
        <div class="footer">
          <div id="status">已保存</div>
          <button class="btn-save" id="saveBtn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
            保存内容
          </button>
        </div>
      </div>

      <script>
        const pad = document.getElementById('pad');
        const status = document.getElementById('status');
        const saveBtn = document.getElementById('saveBtn');
        let timeout;

        function showSavedTip() {
          status.style.opacity = '1';
          setTimeout(() => status.style.opacity = '0', 1500);
        }

        async function saveData() {
          status.innerText = '正在保存...';
          status.style.opacity = '1';
          try {
            await fetch(window.location.pathname, {
              method: 'POST',
              body: pad.value
            });
            status.innerText = '保存成功';
            showSavedTip();
          } catch (e) {
            status.innerText = '保存失败';
            showSavedTip();
          }
        }

        // 自动保存 (停止打字1.5秒)
        pad.addEventListener('input', () => {
          clearTimeout(timeout);
          timeout = setTimeout(saveData, 1500);
        });

        // 按钮手动保存
        saveBtn.addEventListener('click', () => {
          clearTimeout(timeout);
          saveData();
        });

        // 快捷键保存
        document.addEventListener('keydown', (e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            clearTimeout(timeout);
            saveData();
          }
        });
      </script>
    </body>
    </html>
    `;

    return new Response(html, { headers: { 'Content-Type': 'text/html' } });
  }
};
