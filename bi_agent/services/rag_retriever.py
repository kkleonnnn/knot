"""
rag_retriever.py — 语义层 RAG 检索器（BM25）

功能:
  - 把语义层文本按段落切分成小块
  - 用 BM25 算法对每个问题检索最相关的几块
  - 替代「全量注入」，减少 Prompt 噪音

为什么用 BM25 而不是向量检索？
  - 零依赖：纯 Python，无需安装 faiss / chromadb 等向量库
  - SQL 场景效果足够：指标名/表名/字段名这类词精确匹配效果好
  - 速度快：语义层通常只有几十~几百行，BM25 毫秒级返回

参数说明 (BM25):
  k1=1.5  — 词频饱和度（越高越看重高频词）
  b=0.75  — 文档长度归一化（0=不归一化，1=完全归一化）
  经典值，大多数场景无需调整。
"""

import math
import re

# ─────────────────────────────────────────────
# 基础工具
# ─────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """
    轻量分词：中文按字拆，英文/数字/下划线按词拆，全部小写。
    特意不引入 jieba —— SQL 场景中，「orders」「user_id」「GMV」本身就是完整词，
    按 _ 分隔反而更精准。
    """
    return re.findall(r'[\u4e00-\u9fff]|[a-zA-Z_][a-zA-Z0-9_]*|\d+', text.lower())


def _split_into_chunks(text: str, lines_per_chunk: int = 5) -> list[str]:
    """
    把语义层文本按段落切分，每段约 lines_per_chunk 行。
    策略:
      - 空行 = 段落分隔符（立即切断）
      - 以 # 开头的标题行 = 新段落开始
      - 超过 lines_per_chunk 行强制切断
    """
    non_empty_lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
    if not non_empty_lines:
        return []

    chunks: list[str] = []
    current: list[str] = []

    for line in non_empty_lines:
        # 遇到标题行：把已有内容先输出，再开新段
        if line.startswith('#') and current:
            chunks.append('\n'.join(current))
            current = []
        current.append(line)
        if len(current) >= lines_per_chunk:
            chunks.append('\n'.join(current))
            current = []

    if current:
        chunks.append('\n'.join(current))

    return chunks


# ─────────────────────────────────────────────
# BM25 检索器
# ─────────────────────────────────────────────

class BM25Retriever:
    """
    BM25 Okapi 检索器。
    fit() 后可反复 search()，无状态变更。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus: list[str] = []
        self.tokenized: list[list[str]] = []
        self.idf: dict = {}
        self.avgdl: float = 0.0

    def fit(self, corpus: list[str]) -> None:
        """建立索引。corpus 是文本列表（每个元素对应一个「文档」）。"""
        self.corpus = corpus
        self.tokenized = [_tokenize(doc) for doc in corpus]
        N = len(corpus)
        self.avgdl = sum(len(t) for t in self.tokenized) / max(N, 1)

        # IDF = log( (N - df + 0.5) / (df + 0.5) + 1 )
        df: dict = {}
        for tokens in self.tokenized:
            for tok in set(tokens):
                df[tok] = df.get(tok, 0) + 1
        self.idf = {
            tok: math.log((N - freq + 0.5) / (freq + 0.5) + 1)
            for tok, freq in df.items()
        }

    def search(self, query: str, top_k: int = 3) -> list[tuple[str, float]]:
        """
        检索最相关的 top_k 个文档。
        返回 [(doc_text, bm25_score), ...]，按 score 降序，只返回 score > 0 的结果。
        """
        if not self.corpus:
            return []

        query_tokens = _tokenize(query)
        scored: list[tuple[int, float]] = []

        for i, doc_tokens in enumerate(self.tokenized):
            doc_len = len(doc_tokens)
            tf: dict = {}
            for tok in doc_tokens:
                tf[tok] = tf.get(tok, 0) + 1

            score = 0.0
            for tok in query_tokens:
                if tok not in self.idf:
                    continue
                f = tf.get(tok, 0)
                numer = self.idf[tok] * f * (self.k1 + 1)
                denom = f + self.k1 * (1 - self.b + self.b * doc_len / max(self.avgdl, 1))
                score += numer / denom

            scored.append((i, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [(self.corpus[idx], sc) for idx, sc in scored[:top_k] if sc > 0]


# ─────────────────────────────────────────────
# 公开 API
# ─────────────────────────────────────────────

def retrieve_semantic_context(
    question: str,
    semantic_text: str,
    top_k: int = 5,
    lines_per_chunk: int = 5,
) -> str:
    """
    从语义层全文中检索与 question 最相关的片段。

    参数:
      question      — 用户自然语言问题
      semantic_text — 语义层全文（来自 persistence.get_semantic_layer()）
      top_k         — 最多返回几个相关片段
      lines_per_chunk — 切分粒度（行数/块）

    返回:
      相关片段拼接的字符串（直接可注入 Prompt）。
      若语义层较短（块数 <= top_k），直接返回全文。
    """
    if not semantic_text.strip():
        return ""

    chunks = _split_into_chunks(semantic_text, lines_per_chunk=lines_per_chunk)

    # 块数不多时无需检索，全量返回
    if len(chunks) <= top_k:
        return semantic_text

    retriever = BM25Retriever()
    retriever.fit(chunks)
    results = retriever.search(question, top_k=top_k)

    if not results:
        # Fallback：返回前 2000 字符
        return semantic_text[:2000]

    return '\n\n'.join(doc for doc, _ in results)


# ─────────────────────────────────────────────
# 单独测试入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    sample_semantic = """
# 指标定义
GMV = SUM(pay_amount)，含税含运费
日活用户(DAU) = COUNT(DISTINCT user_id) per day，去重计算
留存率 = 次日回访用户数 / 首日新增用户数

# 表关联关系
orders.user_id = users.id
order_items.order_id = orders.id
order_items.product_id = products.id

# 时间字段说明
orders.created_at 是下单时间（Asia/Shanghai）
orders.paid_at 是支付时间（Asia/Shanghai）
users.register_at 是注册时间

# 渠道说明
channel 字段可选值: organic / paid_search / social / referral
paid_source 表示付费渠道来源

# 状态码
order_status: 1=待支付, 2=已支付, 3=已发货, 4=已完成, 5=已退款
user_level: 1=普通, 2=银牌, 3=金牌, 4=钻石
"""

    q1 = "查询昨天各渠道的 GMV"
    q2 = "分析用户留存率趋势"
    q3 = "订单状态为已完成的数量"

    for q in [q1, q2, q3]:
        ctx = retrieve_semantic_context(q, sample_semantic, top_k=2)
        print(f"\n问题: {q}")
        print(f"检索到的上下文:\n{ctx}")
        print("-" * 40)
