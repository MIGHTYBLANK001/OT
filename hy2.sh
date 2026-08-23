#!/usr/bin/env bash
set -e

# ---------- 配置 ----------
PORT=33322
PASSWORD="fdsfasdasdasasdasda234565"
SOCKS5_ADDR="127.0.0.1:7928"
DIR="/opt/hysteria"
# --------------------------

# 架构
case "$(uname -m)" in
  x86_64|amd64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "❌ 不支持的架构"; exit 1 ;;
esac

# 停止旧服务，避免 Text file busy
echo "🧹 停止旧进程..."
pkill -f "$DIR/daemon.sh" 2>/dev/null || true
pkill -f "$DIR/hysteria server" 2>/dev/null || true
sleep 2
pkill -9 -f "$DIR/hysteria server" 2>/dev/null || true

mkdir -p "$DIR"

# 获取最新版本
echo "🔎 获取 Hysteria2 最新版本..."
VERSION=$(curl -fsSL https://api.github.com/repos/apernet/hysteria/releases/latest |
  sed -n 's/.*"tag_name": "\(.*\)".*/\1/p' | head -1)

[ -n "$VERSION" ] || { echo "❌ 无法获取最新版本"; exit 1; }

echo "📦 最新版本: $VERSION"

# 下载到临时文件，再替换
URL="https://github.com/apernet/hysteria/releases/download/${VERSION}/hysteria-linux-${ARCH}"

echo "⏳ 下载 Hysteria2..."
curl -fL --retry 3 -o "$DIR/hysteria.new" "$URL"

chmod +x "$DIR/hysteria.new"
mv -f "$DIR/hysteria.new" "$DIR/hysteria"

# TLS
echo "🔑 生成 TLS..."
openssl req -x509 -nodes -newkey ec \
  -pkeyopt ec_paramgen_curve:prime256v1 \
  -days 3650 \
  -keyout "$DIR/key.pem" \
  -out "$DIR/cert.pem" \
  -subj "/CN=www.bing.com" \
  >/dev/null 2>&1

# Hysteria 配置
cat > "$DIR/server.yaml" <<EOF
listen: ":${PORT}"

tls:
  cert: "${DIR}/cert.pem"
  key: "${DIR}/key.pem"
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

# 轻量守护
cat > "$DIR/daemon.sh" <<'EOF'
#!/bin/sh
while true; do
    pgrep -f "/opt/hysteria/hysteria server" >/dev/null 2>&1 ||
    /opt/hysteria/hysteria server -c /opt/hysteria/server.yaml \
      >>/opt/hysteria/hysteria.log 2>&1 &
    sleep 10
done
EOF
chmod +x "$DIR/daemon.sh"

# LXC 开机启动
if [ ! -f /etc/rc.local ]; then
  printf '#!/bin/sh -e\nexit 0\n' >/etc/rc.local
fi

chmod +x /etc/rc.local
sed -i "\|$DIR/daemon.sh|d" /etc/rc.local
sed -i "/^exit 0/i $DIR/daemon.sh &" /etc/rc.local

# 启动
echo "🚀 启动 Hysteria2..."
nohup "$DIR/daemon.sh" >/dev/null 2>&1 &
sleep 3

# 检查
if pgrep -f "$DIR/hysteria server" >/dev/null 2>&1; then
  IP=$(curl -4 -s --max-time 5 https://api.ipify.org || echo "YOUR_SERVER_IP")

  echo
  echo "=============================================="
  echo "🎉 Hysteria2 部署成功"
  echo "版本: $VERSION"
  echo "端口: $PORT/UDP"
  echo "SOCKS5: $SOCKS5_ADDR"
  echo
  echo "hysteria2://${PASSWORD}@${IP}:${PORT}?sni=www.bing.com&alpn=h3&insecure=1#LXC-Hy2"
  echo "=============================================="
else
  echo "❌ Hysteria2 启动失败"
  cat "$DIR/hysteria.log" 2>/dev/null || true
  exit 1
fi
