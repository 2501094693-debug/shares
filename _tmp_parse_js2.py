import re
from pathlib import Path

t = Path("_tmp_mobile_main.js").read_text(encoding="utf-8", errors="replace")
html = Path("_tmp_m_guba.html").read_text(encoding="utf-8", errors="replace")

print("HTML chunk refs:")
for m in re.findall(r"community-scenes/static/[^\"']+", html):
    print(" ", m)

print("JS chunk refs:")
chunks = sorted(set(re.findall(r"static/js/[^\"']+\.js", t)))
print("count", len(chunks))
for c in chunks[:80]:
    print(" ", c)

print("interesting strings:")
for pat in [
    r"['\"](/[a-zA-Z0-9_./?-]{8,80})['\"]",
    r"['\"](https?://[^'\"]{8,100})['\"]",
]:
    hits = sorted(set(re.findall(pat, t)))
    keep = [
        h
        for h in hits
        if any(
            k in h.lower()
            for k in (
                "circle",
                "guba",
                "post",
                "comment",
                "feed",
                "sns",
                "community",
                "lgt",
                "dong",
                "api",
                "10jqka",
                "m/",
                "wap",
            )
        )
    ]
    print("pat keep", len(keep), "/", len(hits))
    for h in keep[:80]:
        print(" ", h)
