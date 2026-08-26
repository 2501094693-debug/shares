from pathlib import Path

needles = [
    "getComment",
    "comment/v1",
    "open/api",
    "getCommentFlow",
    "/lgt/",
]
for name in [
    "_tmp_stock-discussion-bootstrap.f022db0e.js",
    "_tmp_stock-discussion-core.bb077c12.js",
    "_tmp_stock-discussion-components.4cd18623.js",
]:
    t = Path(name).read_text(encoding="utf-8", errors="replace")
    print(f"\n==== {name} ====")
    for n in needles:
        print(f"  {n}: {t.count(n)}")
    # extract unique /lgt/ paths
    import re
    paths = sorted(set(re.findall(r"[/\w.-]*lgt[/\w.-]*", t)))
    for p in paths:
        if len(p) > 8:
            print(" ", p[:180])
