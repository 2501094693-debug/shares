from pathlib import Path

needle = "hot_feed"
for p in Path(".").glob("_tmp_stock-discussion*.js"):
    t = p.read_text(encoding="utf-8", errors="replace")
    i = t.find(needle)
    print(p.name, "len", len(t), "find", i, "count", t.count("lgt/post"))
    if i < 0:
        i = t.find("forum/content")
        print("  forum/content", i)
    if i >= 0:
        print(t[max(0, i - 250) : i + 400].replace("\n", " "))
        print("---")
