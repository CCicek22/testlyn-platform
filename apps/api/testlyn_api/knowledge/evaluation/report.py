"""Markdown rendering for an evaluation report."""

from __future__ import annotations

from testlyn_api.knowledge.evaluation.runner import EvalReport, ModeReport


def _metric_names(top_k: int) -> tuple[str, str, str, str]:
    return (f"hit@{top_k}", f"recall@{top_k}", "mrr", f"ndcg@{top_k}")


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _metric_row(
    mode: ModeReport,
    scope: str,
    values: dict[str, float],
    count: int,
    top_k: int,
) -> str:
    cells = [_fmt(values.get(name)) for name in _metric_names(top_k)]
    return f"| {mode.mode} | {scope} | {count} | " + " | ".join(cells) + " |"


def render_markdown(report: EvalReport) -> str:
    lines = [
        f"Embedder `{report.embedder}`, {report.documents} documents, "
        f"{report.queries} queries, top_k {report.top_k}.",
        "",
        f"| mode | scope | queries | hit@{report.top_k} | recall@{report.top_k} | MRR | "
        f"nDCG@{report.top_k} |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for mode in report.modes.values():
        lines.append(
            _metric_row(mode, "overall", mode.overall, len(mode.queries), report.top_k)
        )
        for kind in sorted(mode.by_kind):
            count = sum(1 for q in mode.queries if q.kind == kind)
            lines.append(
                _metric_row(mode, kind, mode.by_kind[kind], count, report.top_k)
            )

    judged = [m for m in report.modes.values() if m.judge is not None]
    if judged:
        lines += [
            "",
            "| mode | judged precision@5 | judge errors | judged passages | "
            "accuracy | precision | recall | kappa |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for mode in judged:
            summary = mode.judge
            assert summary is not None
            a = summary.agreement
            lines.append(
                f"| {mode.mode} | {_fmt(summary.judged_precision)} | "
                f"{summary.judge_errors} | {a.n} | {_fmt(a.accuracy)} | "
                f"{_fmt(a.precision)} | {_fmt(a.recall)} | {_fmt(a.kappa)} |"
            )
    return "\n".join(lines) + "\n"
