from pathlib import Path

t = Path("_tmp_stock-discussion-bootstrap.f022db0e.js").read_text(encoding="utf-8", errors="replace")

# find host variable i assignment near the API constants
i = t.find('/lgt/post/open/api/forum/content/v1/recent')
print("=== around recent ===")
print(t[max(0, i-1500): i+800])
print("\n\n=== search concat(i ===")
idx = 0
n = 0
while n < 8:
    j = t.find('concat(i', idx)
    if j < 0:
        break
    print(n, t[max(0,j-80):j+200].replace("\n"," ")[:280])
    print("---")
    idx = j + 8
    n += 1
