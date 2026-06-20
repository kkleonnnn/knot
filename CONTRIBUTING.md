# Contributing to KNOT

感谢你对 KNOT 感兴趣！本文档说明如何参与开发。

> **重要前提**：KNOT 当前处于 v0.6.0 内测期，使用 **Loop Protocol v3** 治理（详见 [CLAUDE.md](CLAUDE.md)）。
> 这意味着每个 PATCH 都有方案 / 评审 / 红线 / 验收 4 阶段。对外部贡献者来说，**先发 issue 讨论方向**远比直接提 PR 更高效。

## 快速开始

### 本地开发

```bash
# 1. 克隆
git clone https://github.com/kkleonnnn/knot.git
cd knot

# 2. Python 后端（editable 安装）
pip install -e ".[dev]"

# 3. 环境变量（必需）
export KNOT_MASTER_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
export JWT_SECRET=$(openssl rand -hex 32)

# 4. 启动后端
python -m uvicorn knot.main:app --reload --port 8000

# 5. 前端（另开终端）
cd frontend
npm install
npm run dev  # 默认 5173 端口
```

### 默认凭据

首次启动后用 `admin` / `admin123` 登录。**立即修改密码**。

## 贡献类型

### 1. Bug 报告

请 [新建 issue](https://github.com/kkleonnnn/knot/issues/new) 并包含：

- 版本号（`knot/main.py` 中 `version=...` 或前端右上角）
- 复现步骤（最小化）
- 期望 vs 实际行为
- 浏览器 console 截图 / 后端日志相关行
- 部署方式（docker / 裸机 / k8s）

### 2. 功能建议

- **小功能**（< 100 行 + 单一职责）：直接发 issue 描述用户故事
- **架构性改动**：先发 issue 讨论；KNOT 用 Loop Protocol v3，大改需要走 4 阶段评审
- **安全漏洞**：**不要发公开 issue**，详见 [SECURITY.md](SECURITY.md)

### 3. 代码 PR

#### 提交前检查

```bash
# 后端
ruff check knot/                       # 代码风格
lint-imports                           # 7 contracts KEPT
python3 scripts/check_file_sizes.py    # R-94 文件行数硬上限
pytest tests/ -v --tb=short --ignore=tests/eval

# 前端
cd frontend
npm run lint                           # 0 errors / 0 warnings 阻塞
npm run build                          # 必须能构建
```

CI 会跑全套（lint-test / frontend-lint / boot-smoke / docker-build），任何红都会阻塞合入。

#### PR 规范

- **分支命名**：`feat/<topic>` / `fix/<issue-number>-<topic>` / `chore/<topic>`
- **commit message**：参考 git log 既有风格（中英混排 OK；首行 ≤ 72 字符）
- **squash merge**：所有 PR 走 squash（保 main 线性）
- **CLAUDE.md 同步**：如果你的改动涉及红线 / 路线图 / 协议，请同步更新

#### 必须避免

- 跳过 CI hooks（`--no-verify`）
- 直接推 main（必须走 PR + review）
- 引入新顶层 npm / pip 依赖而不在 PR 描述中说明理由
- 修改 `LICENSE` / `NOTICE` / 删除 audit 红线代码

### 4. 文档贡献

- README / SECURITY / 本文档：欢迎直接 PR
- `docs/plans/v*.md`：这些是 Loop Protocol v3 的 PATCH 手册，**只有当前执行者 + 守护者修改**
- CLAUDE.md：协议文档，外部贡献者请发 issue 讨论再说

## Loop Protocol v3 简介（给外部贡献者）

KNOT 内部所有 PATCH 走 4 阶段：

1. **Stage 1**：当前 MINOR 的执行者（Claude agent 或开发者）起草手册 `docs/plans/v0.X.Y-*.md`
2. **Stage 2**：辅助 AI（Codex 等）独立初审给 Redline + 评分 + 风险点
3. **Stage 3**：上一 MINOR 的守护者（只读）终审，校验设计一致性 + 红线遗漏
4. **Stage 4**：执行者按终审意见落 commit，全 CI 绿 → PR

**外部贡献者**不需要走完整 4 阶段。但请理解：
- 对 KNOT 核心逻辑（agents / SQL validator / audit / crypto）的改动会被严格审视
- 简单 bug 修复 / 文档 / 测试 / 第三方依赖升级走 fast-path（PR review + CI 即可）
- 不确定时先发 issue 问

## 行为准则

- 尊重协作者；对人对事保持专业
- 不容忍骚扰 / 歧视 / 人身攻击
- 技术分歧通过 issue / PR 讨论，不在私信攻击
- 严重违规请联系 kk@100xex.com

> 完整行为准则见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)（Contributor Covenant 2.1）。

## License

提交 PR 即表示你同意你的贡献以 Apache-2.0 协议授权（与本项目一致）。
详见 [LICENSE](LICENSE)。

## 联系

- Issue：https://github.com/kkleonnnn/knot/issues
- Email：kk@100xex.com
- Security：见 [SECURITY.md](SECURITY.md)
