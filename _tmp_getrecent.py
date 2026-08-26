from pathlib import Path

for name in [
    "_tmp_stock-discussion-bootstrap.f022db0e.js",
    "_tmp_stock-discussion-components.4cd18623.js",
    "_tmp_stock-discussion-core.bb077c12.js",
]:
    t = Path(name).read_text(encoding="utf-8", errors="replace")
    for needle in ["getRecent", "hot_feed", "hotFeed", "HotFeed", "forumId", "fid"]:
        idx = 0
        n = 0
        while n < 3:
            j = t.find(needle, idx)
            if j < 0:
                break
            print(f"\n===== {name} {needle} @{j} =====")
            print(t[max(0, j - 200) : j + 500])
            idx = j + len(needle)
            n += 1
