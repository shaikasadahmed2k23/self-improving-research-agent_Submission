"""Deterministic citation check (runs before the LLM critic).

For every significant number in the draft that is followed by a citation [n], verify that the
number appears in the text the agent actually saw for source n (snippet and/or fetched page).
Numbers produced by the calculator tool, or given in the task itself, count as verified.
Also flags unit mismatches, e.g. a claim says "$0.095 / GB" but the source says "$0.095 per 1M dimensions".
"""
import re
from urllib.parse import urlparse

from agent.nodes.writer import _CITATION, _ids

_NUM = re.compile(r"(?<![\w.])(\$)?(\d+(?:,\d{3})*(?:\.\d+)?)(?!\d)")
_ADJACENT = re.compile(r"[\s,;|]*")  # text between citation groups like "[1][3]" or "[1], [3]"
_UNITS = {  # units whose confusion changes a price's meaning
    "GB": re.compile(r"\b[gt]b\b|gigabyte|terabyte", re.I),
    "dimensions": re.compile(r"\bdim", re.I),
    "hour": re.compile(r"\bhours?\b|\bhr\b|-hour|/h\b", re.I),
}
UNIT_WINDOW = 30
FAIL_STATUSES = {"not_in_source", "unit_mismatch", "unknown_citation", "no_citations"}


def _value(num: str) -> float:
    return float(num.replace(",", ""))


def _decimals(num: str) -> int:
    return len(num.split(".", 1)[1]) if "." in num else 0


def _is_significant(dollar: str | None, num: str) -> bool:
    """Skip list markers, small counts and years; keep prices, decimals and larger figures."""
    v = _value(num)
    if dollar or "." in num:
        return True
    return v >= 10 and not (1900 <= v <= 2100)


def _numbers(text: str) -> list[tuple[float, int]]:
    """All numbers in text as (value, end offset)."""
    return [(_value(m.group(2)), m.end()) for m in _NUM.finditer(text)]


def _units(window: str) -> set[str]:
    return {name for name, rx in _UNITS.items() if rx.search(window)}


def domain(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def extract_claims(draft: str) -> list[dict]:
    """Split the draft into (text segment, cited ids) pairs: numbers before a citation belong to it."""
    body = re.split(r"\n#{1,6}\s*(sources|references)\b", draft, flags=re.I)[0]
    claims: list[dict] = []
    for line in body.splitlines():
        last_end, line_claims = 0, []
        for m in _CITATION.finditer(line):
            segment = line[last_end : m.start()]
            if line_claims and _ADJACENT.fullmatch(segment):
                line_claims[-1]["ids"].extend(_ids(m.group(1)))
            else:
                line_claims.append({"text": segment, "ids": _ids(m.group(1)), "line": line.strip()})
            last_end = m.end()
        claims.extend(line_claims)
    return claims


def check_citations(draft: str, sources: list[dict], calculations: list[dict] | None = None, task: str = "") -> list[dict]:
    """Return one check per (number, citation) pair: status verified | calculated | not_in_source | unit_mismatch | unknown_citation."""
    by_id = {s["id"]: s for s in sources}
    source_nums = {s["id"]: _numbers(f"{s.get('title', '')}\n{s.get('content', '')}") for s in sources}
    calc_results = [c["result"] for c in (calculations or [])]
    task_values = {v for v, _ in _numbers(task)}

    checks, seen = [], set()
    for claim in extract_claims(draft):
        ids = list(dict.fromkeys(claim["ids"]))
        for m in _NUM.finditer(claim["text"]):
            dollar, num = m.group(1), m.group(2)
            if not _is_significant(dollar, num):
                continue
            value = _value(num)
            key = (value, tuple(ids))
            if key in seen or value in task_values:
                continue
            seen.add(key)
            check = {"number": f"{dollar or ''}{num}", "cited": ids, "line": claim["line"][:160]}

            unknown = [i for i in ids if i not in by_id]
            if unknown and len(unknown) == len(ids):
                checks.append({**check, "status": "unknown_citation", "detail": f"cited source(s) {unknown} do not exist"})
                continue

            hits = {i: [end for v, end in source_nums[i] if abs(v - value) < 1e-9] for i in ids if i in by_id}
            hits = {i: ends for i, ends in hits.items() if ends}
            if hits:
                claim_window = claim["text"][m.end() : m.end() + UNIT_WINDOW].split("|")[0]
                claim_units = _units(claim_window)
                src_units = set()
                for i, ends in hits.items():
                    text = f"{by_id[i].get('title', '')}\n{by_id[i].get('content', '')}"
                    for end in ends:
                        src_units |= _units(text[end : end + UNIT_WINDOW + 10])
                missing = claim_units - src_units
                if missing and src_units - claim_units:
                    checks.append({**check, "status": "unit_mismatch",
                                   "detail": f"draft says {'/'.join(sorted(missing))}, source says {'/'.join(sorted(src_units - claim_units))}"})
                else:
                    checks.append({**check, "status": "verified", "detail": f"found in [{', '.join(map(str, hits))}]"})
                continue

            d = _decimals(num)
            if any(abs(round(r, d) - value) < 1e-9 for r in calc_results):
                checks.append({**check, "status": "calculated", "detail": "matches a calculator tool result"})
                continue

            found_in = [s["id"] for s in sources if any(abs(v - value) < 1e-9 for v, _ in source_nums[s["id"]])]
            where = ", ".join(f"[{i}] {domain(by_id[i]['url'])}" for i in found_in[:4])
            detail = f"not in cited {', '.join(f'[{i}] ' + domain(by_id[i]['url']) for i in ids if i in by_id)}"
            detail += f"; appears in {where}" if found_in else "; not found in any source (unsupported or computed without calculator)"
            checks.append({**check, "status": "not_in_source", "detail": detail, "found_in": found_in})

    uncited = _uncited_numbers(draft, task_values)
    checks += [{"number": n, "cited": [], "line": line[:160], "status": "uncited", "detail": "number on a line without any citation"} for n, line in uncited]
    if uncited and not any(c["cited"] for c in checks):
        checks.append({"number": "-", "cited": [], "line": "", "status": "no_citations",
                       "detail": f"the draft cites no sources at all; {len(uncited)} numbers are unsupported"})
    return checks


def _uncited_numbers(draft: str, task_values: set[float]) -> list[tuple[str, str]]:
    """Significant numbers on body lines (not headings) that carry no citation at all."""
    body = re.split(r"\n#{1,6}\s*(sources|references)\b", draft, flags=re.I)[0]
    found, seen = [], set()
    for line in body.splitlines():
        if line.lstrip().startswith("#") or _CITATION.search(line):
            continue
        for m in _NUM.finditer(line):
            dollar, num = m.group(1), m.group(2)
            if _is_significant(dollar, num) and _value(num) not in task_values and (num, line) not in seen:
                seen.add((num, line))
                found.append((f"{dollar or ''}{num}", line.strip()))
    return found


def summarize_checks(checks: list[dict], max_lines: int = 15) -> str:
    counts: dict[str, int] = {}
    for c in checks:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    n_cited = sum(1 for c in checks if c["cited"])
    head = f"Citation check: {n_cited} cited numbers - " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
    failures = [c for c in checks if c["status"] in FAIL_STATUSES]
    lines = [f"FAIL {c['status']}: {c['number']} cited {c['cited']}: {c['detail']}" for c in failures[:max_lines]]
    uncited = [c for c in checks if c["status"] == "uncited"]
    if uncited:
        sample = ", ".join(c["number"] for c in uncited[:8])
        lines.append(f"WARN {len(uncited)} numbers without any citation (e.g. {sample})")
    passes = [c for c in checks if c["status"] == "calculated"][:3]
    lines += [f"ok calculated: {c['number']} ({c['detail']})" for c in passes]
    if len(failures) > max_lines:
        lines.append(f"... and {len(failures) - max_lines} more failures")
    return head + ("\n" + "\n".join(lines) if lines else "\nAll cited numbers verified.")
