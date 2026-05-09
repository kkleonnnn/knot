#!/bin/bash
set -e

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "❌ 缺少 .env 文件，请先复制并填写："
  echo "   cp .env.example .env"
  exit 1
fi

# 检查前端是否已构建（或仍是旧版 babel 页面）
if [ ! -f knot/static/index.html ] || grep -q "babel" knot/static/index.html 2>/dev/null; then
  echo "📦 构建前端..."
  cd frontend && npm install && npm run build && cd ..
fi

if ! python3 -c "import uvicorn" 2>/dev/null; then
  echo "📦 安装 Python 依赖..."
  pip3 install -r requirements.txt
fi

echo "🚀 启动 KNOT..."
echo "   地址：http://localhost:8000"
echo "   停止：Ctrl+C"
echo ""
python3 -m uvicorn knot.main:app --reload --port 8000
