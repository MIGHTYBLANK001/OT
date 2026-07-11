
部署hy2 for lxc 128

wget -O- https://raw.githubusercontent.com/MIGHTYBLANK001/OT/main/hy2.sh | bash

重启hy2

pkill -f daemon.sh || true && pkill -f hysteria || true && nohup /opt/hysteria/daemon.sh > /dev/null 2>&1 &

