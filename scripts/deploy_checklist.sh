#!/bin/bash
# scripts/deploy_checklist.sh — v0.6.0.8 一键部署辅助
#
# 用途：在云服务器 git clone 后运行，自动生成 KNOT_MASTER_KEY + JWT_SECRET、
# 切到 OR-only DEFAULT_MODEL、提示填 OPENROUTER_API_KEY。
#
# 用法：
#   git clone https://github.com/kkleonnnn/knot.git && cd knot
#   bash scripts/deploy_checklist.sh
#
# 红线：
# - 仅幂等准备阶段（不启动容器、不改 git tracked file）
# - 已存在 .env → 仅校验三项 MUST 是否合规，**不覆盖**用户配置
# - 缺失 openssl / python3 → exit 1 友好报错
set -euo pipefail

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
green() { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
yellow() { printf '\033[1;33m⚠ %s\033[0m\n' "$*"; }
red() { printf '\033[1;31m✗ %s\033[0m\n' "$*"; }
bar() { printf '%s\n' "$(printf '━%.0s' $(seq 1 60))"; }

bar
bold "KNOT 部署前 checklist (v0.6.0.8)"
bar

# 依赖检查
command -v python3 >/dev/null 2>&1 || { red "python3 未安装"; exit 1; }
command -v openssl >/dev/null 2>&1 || { red "openssl 未安装"; exit 1; }
green "python3 + openssl 已就绪"

# .env 处理
if [[ ! -f .env ]]; then
  bold "未发现 .env — 从 .env.example 创建"
  cp .env.example .env
  green "已拷贝 .env.example → .env"
else
  yellow ".env 已存在 — 仅校验，不覆盖"
fi

# MUST-1: KNOT_MASTER_KEY
CURRENT_MK=$(grep '^KNOT_MASTER_KEY=' .env | cut -d= -f2- || true)
if [[ -z "$CURRENT_MK" ]]; then
  bold "生成 KNOT_MASTER_KEY (Fernet 32-byte base64)..."
  NEW_MK=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  sed -i.bak "s|^KNOT_MASTER_KEY=.*|KNOT_MASTER_KEY=$NEW_MK|" .env
  green "KNOT_MASTER_KEY 已写入 .env"
  yellow "🔐 务必备份到密码管理器！一旦丢失，所有加密数据无法解密"
  echo "    KNOT_MASTER_KEY=$NEW_MK"
else
  green "KNOT_MASTER_KEY 已存在（$(echo "$CURRENT_MK" | cut -c1-12)...，长度 $(echo -n "$CURRENT_MK" | wc -c)）"
fi

# MUST-1: JWT_SECRET
CURRENT_JWT=$(grep '^JWT_SECRET=' .env | cut -d= -f2- || true)
if [[ -z "$CURRENT_JWT" ]] \
  || [[ "$CURRENT_JWT" == "knot-secret-change-in-production" ]] \
  || [[ "$CURRENT_JWT" == "chatbi-secret-change-in-production" ]] \
  || [[ "$CURRENT_JWT" == "bi-agent-secret-change-in-production" ]] \
  || [[ ${#CURRENT_JWT} -lt 16 ]]; then
  bold "生成 JWT_SECRET (openssl rand -hex 32)..."
  NEW_JWT=$(openssl rand -hex 32)
  sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=$NEW_JWT|" .env
  green "JWT_SECRET 已写入 .env"
else
  green "JWT_SECRET 已合规（长度 ${#CURRENT_JWT}）"
fi

# MUST-2: DEFAULT_MODEL
CURRENT_DM=$(grep '^DEFAULT_MODEL=' .env | cut -d= -f2- || true)
if [[ "$CURRENT_DM" != anthropic/* ]] && [[ "$CURRENT_DM" != openai/* ]] && [[ "$CURRENT_DM" != */* ]]; then
  bold "DEFAULT_MODEL 切到 OR-only key..."
  sed -i.bak "s|^DEFAULT_MODEL=.*|DEFAULT_MODEL=anthropic/claude-haiku-4.5|" .env
  green "DEFAULT_MODEL 切到 anthropic/claude-haiku-4.5"
else
  green "DEFAULT_MODEL 已是 OR 路径（$CURRENT_DM）"
fi

# 提示 OPENROUTER_API_KEY
if grep -q '^OPENROUTER_API_KEY=$' .env || ! grep -q '^OPENROUTER_API_KEY=' .env; then
  yellow "⚠️ OPENROUTER_API_KEY 未填 — admin UI 登录后可在「API & 模型」tab 填，或现在编辑 .env"
fi

# 数据目录
mkdir -p data
green "data/ 目录已就绪"

bar
bold "部署 checklist 完成 — 下一步："
bar
echo "  1. docker build -t knot ."
echo "  2. docker run -d -p 8000:8000 \\"
echo "       -v \$(pwd)/data:/app/knot/data \\"
echo "       --env-file .env --restart unless-stopped \\"
echo "       --name knot knot"
echo "  3. 浏览器访问 http://<server>:8000"
echo "  4. admin/admin123 登录后立即改密码 + 改用户名"
echo "  5. 「API & 模型」tab 填 OpenRouter Key + 验证 3 个 agent 模型"
echo ""
yellow "🔐 KNOT_MASTER_KEY 已存档到密码管理器? 没存的话 ctrl+c → 现在去存"
bar
