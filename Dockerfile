# 使用官方的Python镜像作为基础镜像
FROM python:3.8-slim-buster

# 设置工作目录
WORKDIR /app

# 将当前目录的内容复制到工作目录中
COPY . /app

# 安装项目依赖
RUN pip install --no-cache-dir -r requirements.txt

# 暴露端口，使得Flask应用可以被访问
EXPOSE 2096

# 定义环境变量
ENV FLASK_APP=app.py

# 当容器启动时，运行Flask应用
CMD ["flask", "run", "--host=0.0.0.0", "--port=2096"]