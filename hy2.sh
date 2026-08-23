#!/usr/bin/env bash
set -e

# ---------- 核心配置 ----------
PORT=33322
PASSWORD="fdsfasdasdasasdasda234565"
SOCKS5_ADDR="127.0.0.1:7928"
VERSION="v2.6.5"
DIR="/opt/hysteria"
# -----------------------------

# 1. 自动识别架构
ARCH=$(uname -m)
case "$ARCH" in
  x86_64|amd64) BIN_ARCH="amd64" ;;
  aarch64|arm64) BIN_ARCH="arm64" ;;
  *) echo "❌ 不支持的架构: $ARCH"; exit 1 ;;
esac

# 2. 停止旧 daemon 和 Hysteria
echo "🧹 停止旧进程..."
pkill -f "$DIR/daemon.sh" 2>/dev/null || true
pkill -f "$DIR/hysteria server" 2>/dev/null || true
sleep 2

mkdir -p "$DIR"

# 确认旧 Hysteria 已退出，避免 Text file busy
if pgrep -f "$DIR/hysteria server" >/dev/null 2>&1; then
    echo "⚠️ 强制停止旧 Hysteria..."
    pkill -9 -f "$DIR/hysteria server" 2>/dev/null || true
    sleep 1
fi

# 3. 下载 Hysteria2
echo "⏳ 下载 Hysteria2 ${VERSION}..."

URL="https://github.com/apernet/hysteria/releases/download/app/${VERSION}/hysteria-linux-${BIN_ARCH}"

curl -fL --retry 3 -o "$DIR/hysteria.new" "$URL"

chmod +x "$DIR/hysteria.new"

# 原子替换，避免 Text file busy
mv -f "$DIR/hysteria.new" "$DIR/hysteria"
chmod +x "$DIR/hysteria"

# 4. 生成 TLS 证书
echo "🔑 生成 TLS 证书..."

openssl req -x509 -nodes -newkey ec \
  -pkeyopt ec_paramgen_curve:prime256v1 \
  -days 3650 \
  -keyout "$DIR/key.pem" \
  -out "$DIR/cert.pem" \
  -subj "/CN=www.bing.com" \
  >/dev/null 2>&1

# 5. 写入 Hysteria 配置
echo "📄 写入配置..."

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

# 6. 写入轻量 daemon
echo "⚙️ 配置后台守护..."

cat > "$DIR/daemon.sh" <<'EOF'
#!/bin/sh

while true; do
    if ! pgrep -f "/opt/hysteria/hysteria server" >/dev/null 2>&1; then
        /opt/hysteria/hysteria server \
          -c /opt/hysteria/server.yaml \
          >> /opt/hysteria/hysteria.log 2>&1 &
    fi
    sleep 10
done
EOF

chmod +x "$DIR/daemon.sh"

# 7. LXC 开机启动
echo "🚀 配置开机启动..."

if [ ! -f /etc/rc.local ]; then
    printf '#!/bin/sh -e\nexit 0\n' > /etc/rc.local
fi

chmod +x /etc/rc.local

# 删除旧启动项，避免重复
sed -i "\|$DIR/daemon.sh|d" /etc/rc.local

# 添加到 exit 0 前
sed -i "/^exit 0/i $DIR/daemon.sh &" /etc/rc.local

# 8. 启动 daemon
echo "🚀 启动 Hysteria2..."

nohup "$DIR/daemon.sh" >/dev/null 2>&1 &

sleep 3

# 9. 检查服务
if pgrep -f "$DIR/hysteria server" >/dev/null 2>&1; then

    IP=$(curl -4 -s --max-time 5 https://api.ipify.org || echo "YOUR_SERVER_IP")

    echo
    echo "=================================================================="
    echo "🎉 Hysteria2 ${VERSION} 部署成功"
    echo "=================================================================="
    echo
    echo "监听端口: ${PORT}/UDP"
    echo "SOCKS5:    ${SOCKS5_ADDR}"
    echo "日志:      ${DIR}/hysteria.log"
    echo
    echo "客户端节点:"
    echo
    echo "hysteria2://${PASSWORD}@${IP}:${PORT}?sni=www.bing.com&alpn=h3&insecure=1#LXC-Hy2-Chain"
    echo
    echo "=================================================================="

else

    echo
    echo "❌ Hysteria2 启动失败"
    echo
    echo "========== 日志 =========="
    cat "$DIR/hysteria.log" 2>/dev/null || true
    echo "=========================="
    exit 1

fi
