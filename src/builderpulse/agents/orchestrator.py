"""
BuilderPulse Multi-Agent 编排 — orchestrator.py
用 LangGraph 实现 fetch → digest → push 管道。

用法:
    from builderpulse.agents.orchestrator import run_pipeline
    result = run_pipeline(sources=["blog"], lang="zh")
"""

from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph


# === 状态定义 ===

class PipelineState(TypedDict):
    """管道状态。"""
    sources: list[str]
    lang: str
    fetched_items: list[dict]
    digest: str
    delivered: bool
    error: str | None


# === 节点函数 ===

def fetch_node(state: PipelineState) -> dict:
    """从源获取内容。"""
    sources = state.get("sources", ["blog"])
    lang = state.get("lang", "zh")

    # 模拟获取 (实际调用 BuilderPulse source_aggregator)
    items = []
    for source in sources:
        items.append({
            "source": source,
            "title": f"AI Builder Update from {source}",
            "url": f"https://example.com/{source}/1",
            "summary": f"Latest AI builder content from {source}.",
        })

    return {"fetched_items": items}


def digest_node(state: PipelineState) -> dict:
    """生成摘要。"""
    items = state.get("fetched_items", [])
    lang = state.get("lang", "zh")

    if not items:
        return {"digest": "No content found.", "error": None}

    # 模拟 LLM 摘要 (实际调用 BuilderPulse pipeline)
    if lang == "zh":
        digest = f"今日 AI Builder 动态：共 {len(items)} 条内容。\n\n"
        for item in items:
            digest += f"- {item['title']}: {item['summary']}\n"
    else:
        digest = f"Today's AI Builder updates: {len(items)} items.\n\n"
        for item in items:
            digest += f"- {item['title']}: {item['summary']}\n"

    return {"digest": digest, "error": None}


def push_node(state: PipelineState) -> dict:
    """推送摘要。"""
    digest = state.get("digest", "")
    error = state.get("error")

    if error:
        return {"delivered": False, "error": error}

    if not digest:
        return {"delivered": False, "error": "No digest to deliver."}

    # 模拟推送 (实际调用 BuilderPulse deliver)
    print(f"[BuilderPulse] Delivering digest ({len(digest)} chars)...")
    return {"delivered": True, "error": None}


def error_node(state: PipelineState) -> dict:
    """错误处理。"""
    error = state.get("error", "Unknown error")
    print(f"[BuilderPulse] Error: {error}")
    return {"delivered": False}


# === 条件边 ===

def should_push(state: PipelineState) -> str:
    """判断是否推送 (fetch 后检查)。"""
    if state.get("error"):
        return "error"
    if state.get("fetched_items"):
        return "push"
    return "error"


# === 构建图 ===

def build_pipeline() -> StateGraph:
    """构建 LangGraph 管道。"""
    graph = StateGraph(PipelineState)

    # 添加节点
    graph.add_node("fetch", fetch_node)
    graph.add_node("digest", digest_node)
    graph.add_node("push", push_node)
    graph.add_node("error", error_node)

    # 添加边
    graph.set_entry_point("fetch")
    graph.add_conditional_edges("fetch", should_push, {"push": "digest", "error": "error"})
    graph.add_edge("digest", "push")
    graph.add_edge("push", END)
    graph.add_edge("error", END)

    return graph.compile()


# === 公共 API ===

def run_pipeline(sources: list[str] = None, lang: str = "zh") -> dict:
    """运行管道。"""
    pipeline = build_pipeline()

    initial_state: PipelineState = {
        "sources": sources or ["blog"],
        "lang": lang,
        "fetched_items": [],
        "digest": "",
        "delivered": False,
        "error": None,
    }

    result = pipeline.invoke(initial_state)
    return result


# === CLI ===

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BuilderPulse Multi-Agent Pipeline")
    parser.add_argument("--sources", nargs="+", default=["blog"], help="Content sources")
    parser.add_argument("--lang", default="zh", choices=["zh", "en"], help="Output language")
    args = parser.parse_args()

    result = run_pipeline(sources=args.sources, lang=args.lang)

    print("\n=== Pipeline Result ===")
    print(f"Sources: {result['sources']}")
    print(f"Items fetched: {len(result['fetched_items'])}")
    print(f"Digest length: {len(result['digest'])} chars")
    print(f"Delivered: {result['delivered']}")
    print(f"Error: {result['error']}")

    if result['digest']:
        print(f"\n=== Digest ===\n{result['digest']}")
