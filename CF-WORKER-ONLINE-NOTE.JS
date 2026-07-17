export default {
  async fetch(request, env) {
    // ==========================================
    // 🛠️ 【安全配置】在这里设置你专属的隐藏访问路径（必须以 / 开头）
    // ==========================================
    const SECRET_PATH = "/这里改成你想要的隐藏路径，必须斜杠开头"; 

    const url = new URL(request.url);
    
    // 如果访问的路径不匹配你的专属暗号，直接返回伪装的 404 页面
    if (url.pathname !== SECRET_PATH) {
      return new Response(`
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <title>404 Not Found</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #fff; color: #000; padding: 50px; text-align: center; }
            h1 { font-size: 24px; font-weight: 500; margin-top: 100px; display: inline-block; border-right: 1px solid rgba(0, 0, 0, 0.3); padding: 0 20px 0 0; margin-right: 20px; align-items: center; }
            .desc { inline-block; text-align: left; vertical-align: middle; display: inline-block; font-size: 14px; font-weight: normal; line-height: 49px; margin: 0; padding: 0; }
          </style>
        </head>
        <body>
          <div>
            <h1>404</h1>
            <div class="desc">This page could not be found.</div>
          </div>
        </body>
        </html>
      `, { status: 404, headers: { 'Content-Type': 'text/html' } });
    }

    // 将 KV 存储的 key 锁定为你的隐藏路径名
    const key = SECRET_PATH;

    // 处理保存请求 (POST) - 只有通过了上面的路径校验才会走到这里
    if (request.method === 'POST') {
      const text = await request.text();
      await env.NOTES.put(key, text);
      return new Response('Saved');
    }

    // 获取当前存储的内容
    const value = await env.NOTES.get(key) || '';

    // 返回带自动保存与手动保存的 16:9 720P 页面
    const html = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>在线轻记事本</title>
      <style>
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

        .container {
          width: 100%;
          max-width: 1280px; 
          background: #C7EDCC; 
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

        textarea { 
          width: 100%; 
          aspect-ratio: 16 / 9; 
          background: #E1F3E5; 
          color: #2E4F33; 
          border: 1px solid #B2D8B9; 
          padding: 20px; 
          box-sizing: border-box; 
          font-size: 16px; 
          line-height: 1.6;
          border-radius: 8px; 
          resize: none; 
          outline: none; 
          font-family: inherit;
          transition: border-color 0.2s;
        }
        textarea:focus {
          border-color: #7BB385;
        }

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
          <span>在线编辑剪贴板</span>
          <span>自动保存 / Ctrl+S</span>
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

        // 自动保存
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
