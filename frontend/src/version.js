// v0.6.4.11 task #44 — 前端版本单一真相源（doc-不变量 CI 守护）
// Shell sidebar + Login footer 读此常量（不再硬编 version 字面 → drift 不可能）。
// CI bridge（tests/test_doc_invariants.py::test_app_version_synced_with_main）断言
// APP_VERSION === knot.main.app.version；任一不改即红。每 PATCH 升版本须同步此处（4 源点之一）。
export const APP_VERSION = '0.7.15';
