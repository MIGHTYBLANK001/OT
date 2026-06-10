FROM tsl0922/ttyd:alpine

# 1. 切换到 root 账户
USER root

# 2. 仅安装最核心的 bash 和 curl，不安装任何多余工具，保持镜像极度轻量
RUN apk update && \
    apk add --no-cache bash curl && \
    rm -rf /var/cache/apk/*

# 3. 设置工作目录
WORKDIR /root

# 4. 默认端口
EXPOSE 7861

# 5. 确保运行期为纯 root 身份
USER root

# 6. 最小化启动命令：
CMD ["ttyd", "-p", "7861", "-W", "bash"]
