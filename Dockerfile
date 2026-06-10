# 1. 基础镜像（内部已自带 ttyd 和 tini）
FROM tsl0922/ttyd:latest

# 2. 如果你想基于 Ubuntu/Debian 补充依赖，可以保留这行（官方 ttyd 其实基于 Alpine，这里按你原意的 Ubuntu 编写）
# RUN apt-get update && apt-get install -y --no-install-recommends tini && rm -rf /var/lib/apt/lists/*

EXPOSE 7681
WORKDIR /root

# 3. 正确的 CMD 声明方式（注意：是大写 CMD，且参数用双引号数组隔开）
CMD ["ttyd", "-W", "-c", "admin:nimdanimda", "sh"]
