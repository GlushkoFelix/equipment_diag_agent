"""LangGraph 图组装（ARCH §3.2）。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.runtime import routing
from app.runtime.nodes import Nodes
from app.runtime.state import DiagnosisState


async def report_check(state: DiagnosisState) -> dict:
    return {}


def build_graph(nodes: Nodes, checkpointer=None):
    graph = StateGraph(DiagnosisState)

    graph.add_node("parse_input", nodes.parse_input)
    graph.add_node("clarify", nodes.clarify)
    graph.add_node("retrieve", nodes.retrieve)
    graph.add_node("diagnose", nodes.diagnose)
    graph.add_node("auto_review_report", nodes.auto_review_report)
    graph.add_node("auto_confirm_report", nodes.auto_confirm_report)
    graph.add_node("human_review", nodes.human_review)
    graph.add_node("report", nodes.report)
    graph.add_node("report_check", report_check)
    graph.add_node("report_fix", nodes.report_fix)
    graph.add_node("finalize", nodes.finalize)
    graph.add_node("degraded_finalize", nodes.degraded_finalize)
    graph.add_node("degraded_review_finalize", nodes.degraded_review_finalize)
    graph.add_node("error", nodes.error)
    graph.add_node("aborted", nodes.aborted)
    graph.add_node("row_failed", nodes.row_failed)
    graph.add_node("sample_failed", nodes.sample_failed)

    graph.add_edge(START, "parse_input")
    graph.add_conditional_edges(
        "parse_input",
        routing.route_after_parse,
        {
            "retrieve": "retrieve",
            "clarify": "clarify",
            "error": "error",
            "row_failed": "row_failed",
            "sample_failed": "sample_failed",
        },
    )
    graph.add_edge("retrieve", "diagnose")
    graph.add_conditional_edges(
        "diagnose",
        routing.route_after_diagnose,
        {
            "report": "report",
            "retrieve": "retrieve",
            "auto_review_report": "auto_review_report",
            "auto_confirm_report": "auto_confirm_report",
            "human_review": "human_review",
        },
    )
    graph.add_edge("auto_review_report", "report")
    graph.add_edge("auto_confirm_report", "report")

    resume_map = {"report": "report", "parse_input": "parse_input", "aborted": "aborted"}
    graph.add_conditional_edges("clarify", routing.route_after_resume, resume_map)
    graph.add_conditional_edges("human_review", routing.route_after_resume, resume_map)

    graph.add_edge("report", "report_check")
    graph.add_conditional_edges(
        "report_check",
        routing.route_after_report_check,
        {
            "finalize": "finalize",
            "degraded_review_finalize": "degraded_review_finalize",
            "report_fix": "report_fix",
            "degraded_finalize": "degraded_finalize",
        },
    )
    graph.add_edge("report_fix", "report")

    for terminal in (
        "finalize",
        "degraded_finalize",
        "degraded_review_finalize",
        "error",
        "aborted",
        "row_failed",
        "sample_failed",
    ):
        graph.add_edge(terminal, END)

    return graph.compile(checkpointer=checkpointer)
