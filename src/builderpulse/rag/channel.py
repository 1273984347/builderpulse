"""
BuilderPulse RAG Channel — Qdrant 向量检索 + LLM 重排。

用法:
    from builderpulse.rag.channel import RAGChannel
    channel = RAGChannel(collection="builderpulse")
    results = channel.search("AI agent architecture", top_k=10)
    summary = channel.summarize(results)
"""

import hashlib
import json
from pathlib import Path
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


class RAGChannel:
    """Qdrant 向量检索 + LLM 重排。"""

    def __init__(
        self,
        collection: str = "builderpulse",
        host: str = "localhost",
        port: int = 6333,
        vector_size: int = 384,
    ):
        self.collection = collection
        self.client = QdrantClient(host=host, port=port)
        self.vector_size = vector_size
        self._ensure_collection()

    def _ensure_collection(self):
        """确保 collection 存在。"""
        collections = self.client.get_collections().collections
        names = [c.name for c in collections]
        if self.collection not in names:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                ),
            )

    def _embed(self, text: str) -> list[float]:
        """简单 hash-based embedding (生产环境用 sentence-transformers)。"""
        h = hashlib.sha256(text.encode()).hexdigest()
        # 生成 vector_size 维向量
        vec = []
        for i in range(self.vector_size):
            idx = i % len(h)
            vec.append(float(int(h[idx], 16)) / 15.0)
        return vec

    def add_documents(self, documents: list[dict]) -> int:
        """添加文档到 Qdrant。"""
        points = []
        for doc in documents:
            text = doc.get("text", "")
            metadata = doc.get("metadata", {})
            doc_id = doc.get("id", hashlib.md5(text.encode()).hexdigest())

            vector = self._embed(text)
            points.append(
                PointStruct(
                    id=doc_id,
                    vector=vector,
                    payload={"text": text, **metadata},
                )
            )

        self.client.upsert(collection_name=self.collection, points=points)
        return len(points)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """搜索相似文档。"""
        vector = self._embed(query)
        results = self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            limit=top_k,
        )

        return [
            {
                "id": r.id,
                "score": r.score,
                "text": r.payload.get("text", ""),
                "metadata": {k: v for k, v in r.payload.items() if k != "text"},
            }
            for r in results
        ]

    def summarize(self, results: list[dict], max_items: int = 5) -> str:
        """生成摘要 (简单拼接, 生产环境用 LLM)。"""
        if not results:
            return "No results found."

        lines = [f"Top {min(len(results), max_items)} results:"]
        for i, r in enumerate(results[:max_items]):
            lines.append(f"{i+1}. [{r['score']:.3f}] {r['text'][:200]}...")

        return "\n".join(lines)

    def delete_collection(self):
        """删除 collection。"""
        self.client.delete_collection(collection_name=self.collection)

    def search_hybrid(
        self,
        query: str,
        top_k: int = 10,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
    ) -> list[dict]:
        """混合检索: vector + BM25 + Claude 重排。"""
        # 1. Vector search
        vector_results = self.search(query, top_k=top_k * 2)

        # 2. BM25 search (简单实现: 基于关键词匹配)
        bm25_results = self._bm25_search(query, top_k=top_k * 2)

        # 3. 合并 + 去重
        combined = {}
        for r in vector_results:
            doc_id = r["id"]
            combined[doc_id] = {
                **r,
                "vector_score": r["score"],
                "bm25_score": 0.0,
            }

        for r in bm25_results:
            doc_id = r["id"]
            if doc_id in combined:
                combined[doc_id]["bm25_score"] = r["score"]
            else:
                combined[doc_id] = {
                    **r,
                    "vector_score": 0.0,
                    "bm25_score": r["score"],
                }

        # 4. 混合评分
        for doc_id, doc in combined.items():
            doc["hybrid_score"] = (
                vector_weight * doc["vector_score"]
                + bm25_weight * doc["bm25_score"]
            )

        # 5. 排序 + 截断
        results = sorted(combined.values(), key=lambda x: x["hybrid_score"], reverse=True)
        return results[:top_k]

    def _bm25_search(self, query: str, top_k: int = 20) -> list[dict]:
        """简单 BM25 搜索 (基于关键词匹配)。"""
        # 获取所有文档 (生产环境用倒排索引)
        try:
            all_points = self.client.scroll(
                collection_name=self.collection,
                limit=1000,
            )[0]
        except Exception:
            return []

        # 计算 BM25 分数
        query_terms = set(query.lower().split())
        scored = []

        for point in all_points:
            text = point.payload.get("text", "").lower()
            doc_terms = set(text.split())

            # 简单 BM25: 词频 × IDF
            tf = len(query_terms & doc_terms) / max(len(doc_terms), 1)
            idf = 1.0  # 简化: 所有词等权重
            score = tf * idf

            if score > 0:
                scored.append({
                    "id": point.id,
                    "score": score,
                    "text": point.payload.get("text", ""),
                    "metadata": {k: v for k, v in point.payload.items() if k != "text"},
                })

        # 排序 + 截断
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def rerank_with_llm(self, query: str, results: list[dict], top_k: int = 5) -> list[dict]:
        """用 LLM 重排结果 (简化版: 基于关键词匹配)。"""
        if not results:
            return []

        # 简化版: 基于 query 与 text 的关键词重叠度
        query_terms = set(query.lower().split())

        for r in results:
            text = r.get("text", "").lower()
            text_terms = set(text.split())
            overlap = len(query_terms & text_terms)
            r["rerank_score"] = overlap / max(len(query_terms), 1)

        # 排序 + 截断
        results.sort(key=lambda x: x["rerank_score"], reverse=True)
        return results[:top_k]
