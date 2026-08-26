from pathlib import Path

t = Path("_tmp_stock-discussion-bootstrap.f022db0e.js").read_text(encoding="utf-8", errors="replace")
j = t.find("12528:function")
print("module 12528 at", j)
print(t[j:j+4500])
print("\n\n======== next module boundary ========")
# find next N:function after 12528
k = t.find("},", j+4000)
print(t[j+4500:j+7000])
