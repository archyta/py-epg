#!/bin/bash

# 创建一个新的cron任务，每天运行cleanup命令
echo "0 0 * * * root find /app/EPG_DATA -type f -mtime +10 -delete" >> /etc/crontab

# 启动cron
service cron start

# 运行原来的CMD命令
exec "$@"
