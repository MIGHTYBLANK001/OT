#!/usr/bin/env bash
set -e

# ---------- 核心配置区域 ----------
PORT=33322
PASSWORD="fdsfasdasdasasdasda234565"
SOCKS5_ADDR="127.0.0.1:7928"
# ----------------------------------

# 1. 自动识别架构并清理旧进程
ARCH=$(uname -m)
[[ "$ARCH" == "x86_64" || "$ARCH" == "amd64" ]] && BIN_ARCH="amd64"
[[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]] && BIN_ARCH="arm64"
[[ -z "$BIN_ARCH" ]] && { echo "❌ 不支持的架构: $ARCH"; exit 1; }

pkill -f daemon.sh || true
pkill -f hysteria || true
mkdir -p /opt/hysteria

# 2. 下载核心与生成 TLS 证书
echo "⏳ 下载 Hysteria2 官方核心内核..."
curl -L -o /opt/hysteria/hysteria "https://github.com/apernet/hysteria/releases/download/app/v2.6.5/hysteria-linux-${BIN_ARCH}"
chmod +x /opt/hysteria/hysteria

echo "🔑 生成自签 TLS 证书..."
openssl req -x509 -nodes -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
    -days 3650 -keyout /opt/hysteria/key.pem -out /opt/hysteria/cert.pem -subj "/CN=www.bing.com"

# 3. 写入最终验证成功的强分流配置文件 (ACL 绝对控制版)
echo "📄 写入强分流极简配置文件..."
cat > /opt/hysteria/server.yaml <<EOF
listen: ":${PORT}"
tls:
  cert: "/opt/hysteria/cert.pem"
  key: "/opt/hysteria/key.pem"
  alpn:
    - "h3"
auth:
  type: "password"
  password: "${PASSWORD}"

outbounds:
  - name: proxy_socks5
    type: socks5
    socks5:
      addr: "${SOCKS5_ADDR}"

acl:
  inline:
    - proxy_socks5(any)

bandwidth:
  up: "200mbps"
  down: "200mbps"
EOF

# 4. 配置绝对兼容 LXC 的进程文件级守护脚本
echo "⚙️ 配置后台守护机制..."
cat > /opt/hysteria/daemon.sh <<'EOF'
#!/bin/sh
while true; do
    if ! ps aux | grep "/opt/hysteria/hysteria" | grep -v "grep" > /dev/null; then
        /opt/hysteria/hysteria server -c /opt/hysteria/server.yaml > /dev/null 2>&1 &
    fi
    sleep 10
done
EOF
chmod +x /opt/hysteria/daemon.sh

# 5. 适配 LXC 容器的开机自启动项
echo "🚀 写入系统开机自动启动项..."
rc_local="/etc/rc.local"
if [ ! -f "$rc_local" ]; then
    echo '#!/bin/sh -e' > "$rc_local"
    echo "exit 0" >> "$rc_local"
fi
chmod +x "$rc_local"

if ! grep -q "/opt/hysteria/daemon.sh" "$rc_local"; then
    sed -i '/exit 0/i \/opt/hysteria/daemon.sh &' "$rc_local" || echo "/opt/hysteria/daemon.sh &" >> "$rc_local"
fi

# 6. 正式拉起服务
nohup /opt/hysteria/daemon.sh > /dev/null 2>&1 &

# 获取公网 IP 并回显节点
IP=$(curl -s --max-time 5 https://api.ipify.org || echo "YOUR_SERVER_IP")
echo "=========================================================================="
echo "🎉 Hysteria2 (LXC 强保活版) 部署成功！"
echo "📱 手机/电脑客户端通用导入连接节点："
echo "hysteria2://${PASSWORD}@${IP}:${PORT}?sni=www.bing.com&alpn=h3&insecure=1#LXC-Hy2-Chain"
echo "=========================================================================="
