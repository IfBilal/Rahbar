"""End-to-end level: answers (docs/a3-ragops/06 section 6).

Every valid question (answerable, hard and unanswerable) is sent to /api/ask with the cache
bypassed and the seed fixed. A failed or timed-out call stays in the latency list at the
timeout, so p95 cannot look good by silently dropping the slow cases.
"""

from __future__ import annotations

from typing import Any

from .clients import Api, Judge
from .judge import faithfulness_proxy, judge_answer
from .metrics import mean, norm_doc, percentile
from .traces import TraceReader

FALLBACK_PREFIX = "I could not produce a reliable, properly cited answer"


def eval_headers(cfg: dict[str, Any], run_id: str, label: str) -> dict[str, str]:
    h = {"X-Eval-Seed": str(cfg["e2e"]["seed"]),
         "X-Eval-Temperature": str(cfg["e2e"]["temperature"]),
         "X-Eval-Run": run_id, "X-Eval-Label": label}
    if cfg["e2e"].get("bypass_cache", True):
        h["X-Eval-Bypass-Cache"] = "true"
    return h


def citation_stats(resp: dict[str, Any], gold: list[dict[str, Any]]) -> dict[str, Any]:
    """Valid citations are those matching a passage in THIS response's `retrieved` list
    (A2 definition); an answer given with no citation counts as invalid."""
    retrieved = {(norm_doc(r.get("source")), r.get("page")) for r in resp.get("retrieved") or []}
    cites = resp.get("citations") or []
    valid = sum(1 for c in cites if (norm_doc(c.get("source")), c.get("page")) in retrieved)
    without = 1 if resp.get("answered_from_context") and not cites else 0
    gold_pairs = {(norm_doc(g["doc"]), int(g["page"])) for g in gold}
    gold_hit = any((norm_doc(c.get("source")), c.get("page")) in gold_pairs for c in cites)
    return {"checked": len(cites), "valid": valid, "without": without, "gold_hit": gold_hit}


def abstained(resp: dict[str, Any]) -> bool:
    return not resp.get("answered_from_context") and not (resp.get("citations") or [])


def run(api: Api, judge: Judge | None, traces: TraceReader, questions: list[dict[str, Any]],
        cfg: dict[str, Any], run_id: str, label: str, seed: int,
        notes: list[str]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    timeout = float(cfg["e2e"]["timeout_s"])
    headers = eval_headers(cfg, run_id, label)
    per_q: dict[str, dict[str, Any]] = {}
    seconds: list[float] = []
    totals = {"checked": 0, "valid": 0, "without": 0}
    gold_hits: list[float] = []
    judged: list[str] = []
    proxies: list[float] = []
    abst_ok = false_abst = n_unans = n_ans = fallbacks = 0
    unparseable = 0
    tokens_in: list[float] = []
    tokens_out: list[float] = []
    obeyed: list[str] = []
    no_trace = 0
    for q in questions:
        resp = api.ask(q["question"], headers, timeout)
        sec = float(resp.get("_seconds", timeout))
        seconds.append(sec)
        row: dict[str, Any] = {"category": q["category"], "seconds": round(sec, 2),
                               "trace_id": resp.get("trace_id") or resp.get("_headers", {}).get("x-trace-id")}
        if resp.get("_error"):
            row["error"] = resp["_error"]
            per_q[q["id"]] = row
            if q.get("answerable"):
                n_ans += 1
                false_abst += 1
            else:
                n_unans += 1
            continue
        row["cached"] = bool(resp.get("cached"))
        if row["cached"]:
            notes.append(f"{q['id']}: answered from the semantic cache despite the bypass header")
        answer = str(resp.get("answer", ""))
        row["answer"] = answer[:400]
        row["answered_from_context"] = bool(resp.get("answered_from_context"))
        if answer.startswith(FALLBACK_PREFIX):
            fallbacks += 1
        for phrase in q.get("must_not") or []:
            if phrase.lower() in answer.lower():
                obeyed.append(f"{q['id']}: {phrase}")
        if q.get("answerable"):
            n_ans += 1
            if abstained(resp):
                false_abst += 1
            cs = citation_stats(resp, q["gold"])
            for key in totals:
                totals[key] += cs[key]
            row["citations"], row["citation_validity"] = cs["checked"], (
                None if cs["checked"] + cs["without"] == 0
                else round(cs["valid"] / (cs["checked"] + cs["without"]), 4))
            if row["answered_from_context"]:
                gold_hits.append(1.0 if cs["gold_hit"] else 0.0)
            context = traces.context(row["trace_id"])
            if row["answered_from_context"]:
                if context is None:
                    no_trace += 1
                else:
                    proxy = faithfulness_proxy(answer, context)
                    row["proxy"] = proxy
                    if proxy is not None:
                        proxies.append(proxy)
                    if judge is not None:
                        j = judge_answer(judge, q["question"], answer, context, seed,
                                         int(cfg["judge"]["max_context_chars"]))
                        row["judge_label"] = j["label"]
                        if j["unparseable"]:
                            unparseable += 1
                        elif j["label"]:
                            judged.append(j["label"])
        else:
            n_unans += 1
            if abstained(resp):
                abst_ok += 1
        tk = resp.get("tokens") or {}
        if tk.get("in") is not None:
            tokens_in.append(float(tk["in"]))
            tokens_out.append(float(tk.get("out") or 0))
        per_q[q["id"]] = row
    if no_trace:
        notes.append(f"endpoint: {no_trace} answers had no readable trace/prompt, so they were "
                     "not judged; mount the traces volume")
    n_j = len(judged)

    def share(label: str) -> float | None:
        return None if not n_j else round(judged.count(label) / n_j, 4)
    denom = totals["checked"] + totals["without"]
    p50, p95 = percentile(seconds, 50), percentile(seconds, 95)
    block = {
        "n": len(questions), "n_answerable": n_ans, "n_unanswerable": n_unans,
        "faithfulness": share("supported"), "faithfulness_partial": share("partial"),
        "faithfulness_unsupported": share("unsupported"),
        "faithfulness_proxy": None if not proxies else round(sum(proxies) / len(proxies), 4),
        "abstention_correctness": None if not n_unans else round(abst_ok / n_unans, 4),
        "false_abstention_rate": None if not n_ans else round(false_abst / n_ans, 4),
        "citation_validity": None if not denom else round(totals["valid"] / denom, 4),
        "citations_checked": totals["checked"], "answered_without_citation": totals["without"],
        "citation_gold_hit": None if not gold_hits else round(sum(gold_hits) / len(gold_hits), 4),
        "latency_p50_s": None if p50 is None else round(p50, 2),
        "latency_p95_s": None if p95 is None else round(p95, 2),
        "fallback_rate": None if not questions else round(fallbacks / len(questions), 4),
        "injection_obeyed": obeyed,
        "tokens_in_mean": None if not tokens_in else round(mean(tokens_in) or 0),
        "tokens_out_mean": None if not tokens_out else round(mean(tokens_out) or 0),
        "judge": {"model": getattr(judge, "model", None), "unparseable": unparseable,
                  "judged": n_j}}
    return block, per_q
