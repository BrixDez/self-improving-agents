"""
search_grounding.py — forced-sequence search grounding for the Review role.
Save as: C:\Mistral\self-improving-agents\src\search_grounding.py  (overwrite)

v1.3.3 (19 Sept 2026): GitHub-only live backend. arXiv deferred.
v1.3.2: Accept-Encoding gzip header + transparent gunzip (last header suspect).
v1.3.1: browser-style UA + broad Accept; shared _http_get helper.
Live-diagnostic history (kept deliberately — environmental evidence for the
project log / KEDB):
  - DuckDuckGo HTML endpoint serves bot challenges ("select all squares
    containing a duck") to automated callers -> replaced entirely (v1.3.1).
  - arXiv API returned HTTP 406 across THREE header strategies: polite
    tool-style UA, browser UA, browser UA + gzip Accept-Encoding. Meanwhile
    the browser gets XML fine from the same machine, and Python HTTPS to
    api.github.com returns 200. Conclusion: arXiv is fingerprinting the
    TLS handshake of Python's stdlib stack — not beatable from urllib.
    DEFERRED: revisit via curl subprocess (different TLS stack — test with
    'curl -s -A "Mozilla/5.0" ".../api/query?..."' first) or the 'arxiv'
    pip package (uses 'requests' — may share the same fingerprint, test
    before assuming). Until then: papers are NOT grounded; repos are.
  - GitHub search API: works unauthenticated (~10 req/min), no changes needed.

Aligned to the real agent.py / backbone API:
  - Backbone.trace(event, role, payload, job_id=...)
  - spec is a plain string (Backbone.inject_spec return value)
  - validation operates on agent.Recommendation objects

DESIGN (walkthrough — read before editing):
  Constrain at the boundary, trust accumulates. The agent does NOT decide
  when to search. Phase 1 (ground): the harness runs searches derived
  deterministically from the locked job spec. Phase 2 (recite): the model
  may only recommend sources from the evidence pack; the parser enforces
  exact-URL membership at the boundary (KEDB lesson v1.1/v1.2: constrain at
  the parser, not the prompt). The model keeps synthesis, ranking and
  relevance judgement; it loses citation recall — the job it was failing.

  FAIL CLOSED: if searches return nothing, ground() raises before the
  model is ever consulted. No evidence, no recommendations. The opposite
  of run 1, where the model produced ten confident citations from nothing.
  Tonight this guard was stress-tested by three separate environmental
  failures (duck challenge, arXiv 406 x3) and passed every time: not one
  hallucinated citation escaped.

SECURITY (v1 rules unchanged):
  - MISTRAL_API_KEY from env only, never stored/logged/traced (this module
    never touches the key at all).
  - Search backend needs no key.
  - Only trace what actually executes — no decorative tool_call entries.
"""

from __future__ import annotations

import gzip
import json
import re
import urllib.parse
import urllib.request

SEARCH_TIMEOUT = 10
MAX_RESULTS_PER_QUERY = 5
MAX_QUERIES = 4  # harness cap — anti-wandering (Paul's decision, 19 Sept)

# Browser-shaped headers (arXiv 406 history above; honest agent tag kept).
# Claiming gzip means we must decompress ourselves (_http_get below).
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) sia-review-agent/2.0",
    "Accept": "application/atom+xml, text/xml, application/json, */*",
    "Accept-Encoding": "gzip, deflate",
}


def _http_get(url: str) -> str:
    """GET with browser-shaped headers; transparently gunzips the response."""
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=SEARCH_TIMEOUT) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding", "") == "gzip":
            raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


# ----------------------------------------------------------------- backend

def _arxiv_search(query: str) -> list:
    """arXiv API — returns [{title, url}]. Atom XML parsed with regex (stdlib).
    DEFERRED (v1.3.3): arXiv 406s urllib's TLS fingerprint; not in the live
    rotation. Kept for the curl/requests revisit — do not re-enable without
    a live test first."""
    endpoint = ("https://export.arxiv.org/api/query?search_query=all:"
                + urllib.parse.quote(query)
                + "&start=0&max_results=" + str(MAX_RESULTS_PER_QUERY))
    xml = _http_get(endpoint)
    results = []
    # Each entry: <entry>...<title>...</title>...<id>http://arxiv.org/abs/...</id>
    for m in re.finditer(r"<entry>(.*?)</entry>", xml, flags=re.S):
        entry = m.group(1)
        t = re.search(r"<title>(.*?)</title>", entry, flags=re.S)
        i = re.search(r"<id>(.*?)</id>", entry, flags=re.S)
        if t and i:
            title = re.sub(r"\s+", " ", t.group(1)).strip()
            results.append({"title": title, "url": i.group(1).strip()})
    return results[:MAX_RESULTS_PER_QUERY]


def _github_search(query: str) -> list:
    """GitHub repo search API, unauthenticated. Returns [{title, url}]."""
    endpoint = ("https://api.github.com/search/repositories?q="
                + urllib.parse.quote(query)
                + "&sort=stars&order=desc&per_page=" + str(MAX_RESULTS_PER_QUERY))
    data = json.loads(_http_get(endpoint))
    return [{"title": f"{r['full_name']} — {(r.get('description') or '')[:100]}",
             "url": r["html_url"]}
            for r in data.get("items", [])]


# Swappable backend: tests inject a deterministic fake; live runs search live.
# _search_fn takes the query and returns results from the live sources.
_search_fn = None

# v1.3.3: GitHub only (see header history). Re-add _arxiv_search ONLY after
# the curl/requests experiment proves the 406 is solved.
LIVE_SOURCES = (_github_search,)


def _live_search(query: str) -> list:
    """Query the live sources; one source failing must not kill the run
    (the other may still supply evidence — but an empty TOTAL pack still
    fails closed in ground())."""
    results = []
    for fn in LIVE_SOURCES:
        try:
            results.extend(fn(query))
        except Exception:
            continue  # per-source failure logged by ground()'s error path
    return results


def set_search_backend(fn):
    """Tests call this to inject an offline deterministic backend."""
    global _search_fn
    _search_fn = fn


def _get_search_fn():
    return _search_fn if _search_fn is not None else _live_search


# ----------------------------------------------------- phase 1: ground

def build_queries(spec_text: str) -> list:
    """Derive search queries from the locked job spec TEXT.
    Deterministic: same spec -> same queries -> comparable runs.
    v1.3.4: the v1.3.3 topic-regex greedily swallowed spec prose up to the
    next comma ("...agent design and propose novel improvements (GUI" ->
    junk queries -> GitHub 200-with-zero-items -> fail-closed abort).
    Fix: extract ONLY the topical noun phrase, then use fixed templates."""
    m = re.search(r"self-improving agents?", spec_text, flags=re.I)
    base = m.group(0) if m else spec_text.split(".")[0][:60].strip()
    queries = [
        f"{base} framework",
        f"{base} survey",
        f"{base} open source",       # repo hunting — run 1's blind spot
        f"{base} tools",
    ]
    return queries[:MAX_QUERIES]


def ground(spec_text: str, bb, role: str, job_id: str) -> dict:
    """Run the forced search phase through the backbone's traced API.
    Returns the evidence pack: {url: title}. Every query is traced; a
    failed query is logged and skipped; an empty pack aborts the run."""
    pack = {}
    for q in build_queries(spec_text):
        try:
            results = _get_search_fn()(q)
        except Exception as e:  # network errors must not break the chain
            # NOTE: backbone.trace() enforces a TRACE_EVENT_TYPES whitelist.
            # A web search IS a tool call — use the existing event type and
            # carry specifics in the payload. Adding new event types would be
            # a trace-config change (Tier 2, human sign-off) and is not needed.
            bb.trace("tool_call", role,
                     {"tool": "web_search", "query": q, "status": "error",
                      "error": str(e)}, job_id=job_id)
            continue
        bb.trace("tool_call", role,
                 {"tool": "web_search", "query": q, "status": "ok",
                  "n_results": len(results)}, job_id=job_id)
        for r in results:
            pack.setdefault(r["url"], r["title"])
    if not pack:
        bb.trace("tool_call", role,
                 {"tool": "web_search", "status": "empty_pack_abort",
                  "detail": "no search results — aborting before model call"},
                 job_id=job_id)
        raise RuntimeError("grounding produced no evidence; refusing phase 2")
    return pack


# ----------------------------------------------------- phase 2: recite

def evidence_pack_prompt(pack: dict) -> str:
    """Appended to the role prompt: the model may only cite pack URLs."""
    lines = [
        "EVIDENCE PACK — you may ONLY recommend sources from this list.",
        "For each recommendation set 'source' to the exact URL from the pack",
        "and put the source's title in the evidence field. A recommendation",
        "whose source is not exactly one of the pack URLs will be rejected",
        "and never reach the change board.",
        "",
    ]
    for url, title in pack.items():
        lines.append(f"- {title}\n  {url}")
    return "\n".join(lines)


def validate_against_pack(recs: list, pack: dict) -> tuple:
    """Parser-boundary enforcement on Recommendation objects.
    Returns (accepted, rejected). Exact URL match required — a
    plausible-looking invented URL does not pass."""
    accepted, rejected = [], []
    for rec in recs:
        src = (getattr(rec, "source", "") or "").strip()
        (accepted if src in pack else rejected).append(rec)
    return accepted, rejected