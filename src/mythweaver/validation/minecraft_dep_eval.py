"""Conservative Minecraft version bound checks for fabric.mod.json depends entries."""

from __future__ import annotations

import re
from typing import Any


def _mc_tuple_from_string(v: str) -> tuple[int, ...] | None:
    if not v or not isinstance(v, str):
        return None
    nums = [int(x) for x in re.findall(r"\d+", v)]
    if not nums:
        return None
    if len(nums) == 1:
        return (nums[0], 0, 0)
    if len(nums) == 2:
        return (nums[0], nums[1], 0)
    return tuple(nums[:4])


def _compare_mc(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    max_len = max(len(a), len(b))
    ap = list(a) + [0] * (max_len - len(a))
    bp = list(b) + [0] * (max_len - len(b))
    for x, y in zip(ap, bp, strict=False):
        if x < y:
            return -1
        if x > y:
            return 1
    return 0


def minecraft_dep_supported(spec: Any, *, target_mc: str) -> str:
    """
    Returns one of:
    - 'supported'
    - 'unsupported' (clearly excludes target)
    - 'unknown' (cannot decide from string/intersection semantics)
    """
    target_t = _mc_tuple_from_string(target_mc)
    if not target_t:
        return "unknown"

    specs: list[str] = []
    if spec is None or spec == "":
        return "unknown"
    if isinstance(spec, str):
        specs.append(spec.strip())
    elif isinstance(spec, list):
        for item in spec:
            specs.extend(_flatten_dep_values(item))
    elif isinstance(spec, dict):
        # rare object form — stringify values
        for value in spec.values():
            specs.extend(_flatten_dep_values(value))
    else:
        return "unknown"

    joined = " ".join(specs).lower()

    # Open upper bound exclusions: ">1.20.1" means not 1.20.1
    m_gt = re.search(r">\s*(?:minecraft\s*)?([\d.]+)", joined.replace("minecraft", ""))
    if m_gt:
        low = _mc_tuple_from_string(m_gt.group(1))
        if low and _compare_mc(target_t, low) <= 0:
            return "unsupported"

    # ">= X" implies minimum supported X
    for m_ge in re.finditer(r">=\s*([\d.]+)", joined):
        low = _mc_tuple_from_string(m_ge.group(1))
        if low and _compare_mc(target_t, low) < 0:
            return "unsupported"

    # "~1.20.4" style caret/tilde on modern fabric uses >= lower patch
    for m_tilde in re.finditer(r"[~^]\s*([\d.]+)", joined):
        low = _mc_tuple_from_string(m_tilde.group(1))
        if low and _compare_mc(target_t, low) < 0:
            return "unsupported"

    # explicit 1.21+ style
    if re.search(r"(^|\s)1\.21(\.|\b)", joined) and "1.20.1" not in joined and "1.20" not in joined.replace("1.20.1", ""):
        if _compare_mc(target_t, (1, 21, 0)) < 0:
            return "unsupported"

    if "*" in joined or joined in {"", "any", "*"}:
        return "supported"

    # If we only see an exact single version like "1.20.1" -> supported if match
    m_exact = re.fullmatch(r"[\d.]+", joined.strip())
    if m_exact:
        exact = _mc_tuple_from_string(joined.strip())
        if exact and _compare_mc(target_t, exact) == 0:
            return "supported"

    return "unknown"


def _flatten_dep_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for v in value:
            out.extend(_flatten_dep_values(v))
        return out
    if isinstance(value, dict):
        return _flatten_dep_values(list(value.values()))
    return [str(value)]
