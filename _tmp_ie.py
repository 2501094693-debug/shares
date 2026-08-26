from pathlib import Path

t = Path("_tmp_stock-discussion-bootstrap.f022db0e.js").read_text(encoding="utf-8", errors="replace")

# Find n.d exports that include IE and j$
for needle in [
    "IE:function",
    "j$:function",
    "HD:function",
    "key:\"IE\"",
    ",IE:",
]:
    j = t.find(needle)
    print(needle, j)

print("\n=== search n.d with IE ===")
idx = 0
n = 0
while n < 10:
    j = t.find("IE:function(){return", idx)
    if j < 0:
        j = t.find("IE:function(){", idx)
    if j < 0:
        break
    print(t[max(0, j - 400) : j + 200])
    print("---")
    idx = j + 10
    n += 1

# Find function that uses u.t or the recent path constant E
print("\n=== uses of content/v1/recent via exported t ===")
# The constants module exports: t:function(){return E} for recent
# consumers might be (0, xxx.t) or u.t
for needle in ["u.t,", "u.t)", "s.t,", "l.t,", "n.t(", ".t("]:
    pass

# Search around getRecentPostDataList caller: (0,l.IE)
print("\n=== l.IE definition via HD/IE/j$ nearby functions ===")
for needle in ["function IE", "IE=function", "getRecentPost"]:
    j = t.find(needle)
    print(needle, j)
    if j >= 0:
        print(t[max(0,j-100):j+600])
        print("---")
