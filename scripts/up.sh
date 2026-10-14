#!/bin/bash
# 确保素材库服务在跑（幂等，可反复执行）
if curl -s -o /dev/null -m 2 http://127.0.0.1:8390/api/components; then
  echo "服务已在运行: http://127.0.0.1:8390/studio"
else
  cd ~/assets/.playground-work
  setsid python3 ~/assets/scripts/playground.py serve 8390 >> serve.log 2>&1 &
  sleep 2
  curl -s -o /dev/null -m 5 http://127.0.0.1:8390/api/components && echo "已启动: http://127.0.0.1:8390/studio | /compare" || echo "启动失败，看 ~/assets/.playground-work/serve.log"
fi
