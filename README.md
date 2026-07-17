部署hy2 for lxc 128

wget -O- https://raw.githubusercontent.com/MIGHTYBLANK001/OT/main/hy2.sh | bash

重启

pkill -f daemon.sh || true && pkill -f hysteria || true && nohup /opt/hysteria/daemon.sh > /dev/null 2>&1 &

查看 Hy2 的实时运行日志（排查故障）

pkill -f daemon.sh || true && pkill -f hysteria || true

/opt/hysteria/hysteria server -c /opt/hysteria/server.yaml



云记事本部署：

CF-WORKER-ONLINE-NOTE.JS:

KV: NOTES

https://github.com/ToiCF/GrainTCP

https://github.com/Luckylos/SS-kuangbao

vless://[你的UUID]@[你的Workers域名或优选IP]:443?encryption=none&security=tls&sni=[你的Workers域名]&type=ws&host=[你的Workers域名]&path=%2F#ToiCF_Kuangbao_Optimized
