# scripts/

## refactor/

v0.3.x 工程化重构期间的迁移脚本，**进仓库永久保留**作为审计证据：

- `v0.3.0_migration.sh` — 拆 persistence.py → repositories/，建 models/，干掉 sys.path hack，全局裸名 import 改写
- `v0.3.0_rollback.sh` — `git revert` 一键回滚

每个脚本幂等可重入，运行前请确保已 `git stash` 本地未提交改动。

合作伙伴 / 部署方升级到 v0.3.0 时：
```bash
git pull
pip install -e ".[dev]"
# 老 import 会立即报错；按 CHANGELOG v0.3.0 BREAKING 段迁移业务文件
```
