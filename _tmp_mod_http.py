from pathlib import Path

t = Path("_tmp_stock-discussion-bootstrap.f022db0e.js").read_text(encoding="utf-8", errors="replace")

# module 81305 exports - search for 81305:function
j = t.find("81305:function")
print("81305 at", j)
if j >= 0:
    print(t[j:j+1800])

print("\n\n======== module 79355 ========")
j = t.find("79355:function")
print("79355 at", j)
if j >= 0:
    print(t[j:j+2000])

print("\n\n======== module 9986 getData ========")
j = t.find("9986:function")
print("9986 at", j)
if j >= 0:
    print(t[j:j+2500])
