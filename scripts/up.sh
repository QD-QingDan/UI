#!/bin/bash
# 素材库服务保活（幂等，可反复执行）：playground :8390 + 检索 API :8321
ok() { curl -s -o /dev/null -m 2 "$1"; }

# playground serve
if ok http://127.0.0.1:8390/api/components; then
  echo "[8390] 已在运行"
else
  cd ~/assets/.playground-work
  setsid python3 ~/assets/scripts/playground.py serve 8390 >> serve.log 2>&1 &
  sleep 2
  ok http://127.0.0.1:8390/api/components && echo "[8390] 已启动" || echo "[8390] 启动失败，看 ~/assets/.playground-work/serve.log"
fi

# 检索 API
if ok http://127.0.0.1:8321/health; then
  echo "[8321] 已在运行"
else
  cd ~/assets
  setsid python3 ~/assets/scripts/server.py 8321 >> ~/assets/.playground-work/server.log 2>&1 &
  sleep 2
  ok http://127.0.0.1:8321/health && echo "[8321] 已启动" || echo "[8321] 启动失败，看 server.log"
fi
echo "工作台: http://127.0.0.1:8390/"
