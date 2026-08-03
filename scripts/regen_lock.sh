#!/usr/bin/env bash
# 重新生成 requirements.lock（v0.9.14 · d1' + d7 + Stage 3 Q3）
#
# ⭐ 为什么必须在容器里生成，不能 `pip freeze` 当前 venv：
#   本机开发 venv 是 3.12，而 CI 与生产镜像都是 3.11。不同解释器解析出的
#   传递依赖集合与 wheel 不同 ⇒ 在 venv 里 freeze 出来的 lock 对生产**无效**。
#
# ⭐ 基础镜像**不在本脚本里硬编**，而是从 Dockerfile 的**最后一个 FROM**派生
#   （= 多阶段构建里真正被 tag 的那个 stage = 运行 stage）。
#   理由（Stage 3 Q3-② / Sd7）：「用哪个 Python」若在脚本与 Dockerfile 各写一份，
#   它们会静默漂开、lock 又在错的环境里生成 —— 那正是 d1' 存在的理由。
#   派生 ⇒ 两处不可能不一致；哨兵 Sd7 断言的是「派生真的产出运行 stage 的镜像」，
#   而不是比对两个字面量（判据锚在产出，不锚在文本）。
#
# 用法：  ./scripts/regen_lock.sh              # 写入 requirements.lock
#         ./scripts/regen_lock.sh --check      # 只比对，不写（CI/本地自查用）
#         ./scripts/regen_lock.sh --print-base # 只打印派生出的基础镜像（Sd7 用；不碰 docker）
#
# 何时需要重新生成（d7）：
#   · 改了 requirements.txt（加/删依赖、动区间）
#   · 换了 Dockerfile 运行 stage 的基础镜像（Python 版本变了）
#   · 想吸收上游安全更新（有意动作，须复核 diff）
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# ── 从 Dockerfile 派生运行 stage 的基础镜像（Sd7 的单一真相源）───────────────
derive_base_image() {
    awk '/^[[:space:]]*FROM[[:space:]]/ { img = $2 } END { if (img == "") exit 1; print img }' Dockerfile
}
BASE="$(derive_base_image)"
[ -n "$BASE" ] || { echo "无法从 Dockerfile 派生基础镜像" >&2; exit 1; }

# ⭐ Sd7 用：只把派生结果打到 stdout 就退出，**不启动 docker**。
#    哨兵因此测的是「这段派生真的产出什么」，而不是「脚本文本里写着什么」
#    （判据锚在产出，不锚在描述 —— 本仓 R-SENTINEL-AST 的同一条内核）。
if [ "${1:-}" = "--print-base" ]; then
    printf '%s\n' "$BASE"
    exit 0
fi

# ⭐ 目标平台**必须显式指定**，不能沿用宿主：本机是 darwin/arm64，而 CI
#    （`ubuntu-latest`）与生产 K8s 都是 **linux/amd64** ⇒ 不指定就会生成一份
#    对生产无效的 lock。实证：首次生成时头部打出 `machine: aarch64`，当场自证无效。
#    （可用 LOCK_PLATFORM 覆盖，仅用于「同一份 spec 在别的架构上解析出什么」这类对照实验。）
PLATFORM="${LOCK_PLATFORM:-linux/amd64}"

MODE="${1:-write}"
OUT="requirements.lock"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

echo "→ 基础镜像（派生自 Dockerfile 最后一个 FROM）: $BASE" >&2
echo "→ 目标平台: $PLATFORM" >&2

# ⚠️ 只挂 requirements.txt 且只读 —— 容器看不到仓库其余部分，也就不可能把
#    本项目自身或任何本地包装进 freeze 结果（集合等值比对要求环境只含生产依赖）。
docker run --rm --platform "$PLATFORM" \
    -v "$REPO/requirements.txt:/requirements.txt:ro" \
    -e "BASE=$BASE" -e "PLATFORM=$PLATFORM" \
    "$BASE" \
    sh -eu -c '
        # 安装输出全部转 stderr，stdout 只留 lock 内容
        pip install --no-cache-dir --quiet -r /requirements.txt 1>&2

        # ── 头部由本脚本（在容器内）**生成**，不是手写声明 ────────────────
        #    Sd5 因此验的是「这段话是派生的」，而不是「有这么一段话」。
        python - <<PY
import platform, sys
try:
    from importlib.metadata import version as _v
    pipver = _v("pip")
except Exception:
    pipver = "unknown"
print("# requirements.lock —— 全树精确 pin（自动生成，请勿手改）")
print("# 生成方式: ./scripts/regen_lock.sh    （在容器内 pip freeze）")
print("# 生成环境:")
print(f"#   base-image : ${BASE}")
print(f"#   --platform : ${PLATFORM}")
print(f"#   python     : {platform.python_version()} ({sys.implementation.name})")
print(f"#   platform   : {platform.system().lower()}")
print(f"#   machine    : {platform.machine()}")
print(f"#   pip        : {pipver}")
print("#")
print("# ⚠️ 本文件只对上面这个环境有效。换 Python 版本 / 平台 / 架构都必须重新生成。")
print("# ⚠️ 精确版本由本文件钉；requirements.txt 的区间只是「不让 pip 解析到明知会坏的地方」")
print("#    的声明，不代表区间内每个点都验过 —— 验过的只有本文件这一点。")
PY

        # ⚠️ 用 pip freeze（不加 --all）：pip / setuptools / wheel 不进 lock，
        #    否则把 lock 当 constraints 用时会连 pip 自己一起约束住。
        pip freeze
    ' > "$TMP"

# 基本自检：至少要有头部 + 若干 == 行
grep -q '^# 生成环境:' "$TMP" || { echo "生成结果缺头部，中止" >&2; exit 1; }
n=$(grep -c '==' "$TMP" || true)
[ "$n" -ge 20 ] || { echo "生成结果只有 $n 个 pin，明显不对，中止" >&2; exit 1; }

if [ "$MODE" = "--check" ]; then
    if diff -u "$OUT" "$TMP"; then
        echo "✅ requirements.lock 与容器内实际解析一致（$n 个 pin）" >&2
    else
        echo "⛔ requirements.lock 已过期 —— 跑 ./scripts/regen_lock.sh 重新生成" >&2
        exit 1
    fi
else
    cp "$TMP" "$OUT"
    echo "✅ 已写入 $OUT（$n 个 pin）" >&2
fi
