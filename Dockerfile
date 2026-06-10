# 1. 声明基础镜像
FROM tsl0922/ttyd:latest

EXPOSE 7681
WORKDIR /root

# 3. 正确的 CMD 语法（大写，无冒号，参数用双引号包裹的数组）
CMD ["ttyd", "-W", "-c", "admin:nimdanimda", "bash"]
