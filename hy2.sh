#!/usr/bin/env bash
set -e

# ---------- 核心配置 ----------
PORT=33322
PASSWORD="fdsfasdasdasasdasda234565"
SOCKS5_ADDR="127.0.0.1:7928"
# -----------------------------

ARCH=$(uname -m)
case "$ARCH" in
  x86_64|amd64) BIN_ARCH=amd64 ;;
  aarch64|arm64) BIN_ARCH=arm64 ;;
  *) echo "❌ 不支持的架构: $ARCH"; exit 1 ;;
esac

# 清理旧进程
pkill -f /opt/hysteria/daemon.sh 2>/dev/null || true
pkill -f "/opt/hysteria/hysteria server" 2>/dev/null || true

mkdir -p /opt/hysteria

# 下载 Hysteria 2.6.5
echo "⏳ 下载 Hysteria2..."
curl -fL -o /opt/hysteria/hysteria \
  "https://github.com/apernet/hysteria/releases/download/app/v2.6.5/hysteria-linux-${BIN_ARCH}"
chmod +x /opt/hysteria/hysteria

# 生成 TLS
echo "🔑 生成 TLS 证书..."
openssl req -x509 -nodes -newkey ec \
  -pkeyopt ec_paramgen_curve:prime256v1 \
  -days 3650 \
  -keyout /opt/hysteria/key.pem \
  -out /opt/hysteria/cert.pem \
  -subj "/CN=www.bing.com"

# 写入配置
echo "📄 写入配置..."
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

outbound:
  type: socks5
  socks5:
    server: "${SOCKS5_ADDR}"

bandwidth:
  up: "200mbps"
  down: "200mbps"
EOF

# 配置守护
cat > /opt/hysteria/daemon.sh <<'EOF'
#!/bin/sh
while true; do
    if ! pgrep -f "/opt/hysteria/hysteria server" >/dev/null; then
        /opt/hysteria/hysteria server -c /opt/hysteria/server.yaml \
          >> /opt/hysteria/hysteria.log 2>&1 &
    fi
    sleep 10
done
EOF
chmod +x /opt/hysteria/daemon.sh

# LXC 开机启动
if [ ! -f /etc/rc.local ]; then
    printf '#!/bin/sh -e\nexit 0\n' > /etc/rc.local
fi
chmod +x /etc/rc.local

sed -i '\|/opt/hysteria/daemon.sh|d' /etc/rc.local
sed -i '/exit 0/i /opt/hysteria/daemon.sh &' /etc/rc.local

# 启动
nohup /opt/hysteria/daemon.sh >/dev/null 2>&1 &

sleep 2

# 检查
if pgrep -f "/opt/hysteria/hysteria server" >/dev/null; then
    IP=$(curl -4 -s --max-time 5 https://api.ipify.org || echo "YOUR_SERVER_IP")

    echo "=================================================================="
    echo "🎉 Hysteria2 部署成功"
    echo
    echo "hysteria2://${PASSWORD}@${IP}:${PORT}?sni=www.bing.com&alpn=h3&insecure=1#LXC-Hy2-Chain"
    echo
    echo "日志: /opt/hysteria/hysteria.log"
    echo "=================================================================="
else
    echo "❌ Hysteria 启动失败:"
    cat /opt/hysteria/hysteria.log 2>/dev/null || true
    exit 1
fi
