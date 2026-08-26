from pathlib import Path

t = Path("_tmp_stock-discussion-bootstrap.f022db0e.js").read_text(encoding="utf-8", errors="replace")

# full export map of constants module (81305)
j = t.find('y="".concat(i,"/lgt/cache/open/api/forum/v2/index")')
# go backwards to n.d
k = t.rfind("n.d(e,{", j-2000)
print("=== constants n.d ===")
print(t[k:k+900])

print("\n\n=== bQ definition ===")
# search all js files
for name in [
    "_tmp_stock-discussion-bootstrap.f022db0e.js",
    "_tmp_stock-discussion-core.bb077c12.js",
    "_tmp_stock-discussion-components.4cd18623.js",
]:
    s = Path(name).read_text(encoding="utf-8", errors="replace")
    for needle in ["bQ:function(){return", "bQ:function(", "Z5:", "function bQ"]:
        idx = 0
        n = 0
        while n < 2:
            p = s.find(needle, idx)
            if p < 0:
                break
            print(f"\n--- {name} {needle} @{p} ---")
            print(s[max(0,p-120):p+700])
            idx = p + len(needle)
            n += 1
