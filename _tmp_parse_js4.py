import re
from pathlib import Path

t = Path("_tmp_mobile_main.js").read_text(encoding="utf-8", errors="replace")

key = "stock-discussion-remoteEntry"
i = t.find(key)
print("context1")
print(t[max(0, i - 200) : i + 500])
print("\n==== circle-remote ====")
j = t.find("circle-remoteEntry")
print(t[max(0, j - 200) : j + 500])
print("\n==== function tt ====")
# find production version suffix
for m in re.finditer(r"remoteEntry[^\"']{0,40}", t):
    print(m.group(0), "at", m.start())
