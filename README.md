部署hy2 for lxc 128
wget -O- https://raw.githubusercontent.com/MIGHTYBLANK001/OT/main/hy2.sh | bash
重启
pkill -f daemon.sh || true && pkill -f hysteria || true && nohup /opt/hysteria/daemon.sh > /dev/null 2>&1 &
查看 Hy2 的实时运行日志（排查故障）
pkill -f daemon.sh || true && pkill -f hysteria || true
/opt/hysteria/hysteria server -c /opt/hysteria/server.yaml
