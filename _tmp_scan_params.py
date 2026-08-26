from pathlib import Path

# How are E/_ used after definition? Search for typical axios/get patterns near forum content
files = list(Path(".").glob("_tmp_*.js")) + list(Path(".").glob("_tmp_*.txt"))
needles = [
    "forum/content/v1/recent",
    "forum/content/v1/hot_feed",
    "forumId",
    "hot_feed",
    "cursor",
    "last_id",
    "page_size",
    "pageSize",
    "getRecent",
    "getHotFeed",
]
for p in files:
    if p.stat().st_size > 5_000_000:
        continue
    t = p.read_text(encoding="utf-8", errors="replace")
    hits = []
    for n in needles:
        c = t.count(n)
        if c:
            hits.append(f"{n}:{c}")
    if hits:
        print(p.name, p.stat().st_size, hits)

print("\n=== bootstrap usages of exported recent/hot ===")
t = Path("_tmp_stock-discussion-bootstrap.f022db0e.js").read_text(encoding="utf-8", errors="replace")
# module export names: t:function(){return E}  -- look at n.d exports near the constants
i = t.find('E="/lgt/post/open/api/forum/content/v1/recent"')
# find the module id wrapping these constants
print("module snippet start:")
print(t[max(0,i-3500):i-1400][:800])
