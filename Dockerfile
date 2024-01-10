# 使用官方的Python镜像作为基础镜像
FROM python:3.10-slim-buster

# 设置工作目录
WORKDIR /app

# 将当前目录的内容复制到工作目录中
COPY . /app

# 安装项目依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装Gunicorn
RUN pip install gunicorn supervisor

# 安装cron
RUN apt-get update && apt-get -y install cron

# 添加entrypoint脚本
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 暴露端口，使得Flask应用可以被访问
EXPOSE 8080

# 复制supervisor配置文件到容器中的适当位置
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# 定义环境变量
ENV FLASK_APP=app.py

# 设置容器的入口点为entrypoint脚本
ENTRYPOINT ["/entrypoint.sh"]

# 当容器启动时，使用supervisor来启动你的应用
CMD ["/usr/local/bin/supervisord"]

## 当容器启动时，运行Flask应用
## CMD ["flask", "run", "--host=0.0.0.0", "--port=2096"]
#CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]