# 1. 基础镜像使用指定的 ygkkk/argosbx:latest
FROM ygkkk/argosbx:latest
# 2. 切换到原镜像的工作目录
WORKDIR /app
# 3. 声明容器对外暴露的端口
EXPOSE 54654
# 4. 设置默认的环境变量
ENV vwpt=54654
ENV PORT=3000
ENV UUID=5acf9979-5b4a-41cb-9ebb-da6185f7fa1c
# 5. 正确的方括号格式启动命令（注意逗号和双引号）
CMD ["node", "index.js"]
