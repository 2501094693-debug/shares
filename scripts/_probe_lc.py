# -*- coding: utf-8 -*-
import re
import urllib.request

base = "http://127.0.0.1:5000"
js = urllib.request.urlopen(base + "/js/shared/line-compare.js?v=20261025-fix-encoding", timeout=10).read()
text = js.decode("utf-8")
print("js_len", len(text))
print("fffd", text.count("\ufffd"))
print("has_amp", "最大涨幅" in text)
print("lines_6_10:")
for line in text.splitlines()[5:10]:
    print(repr(line))

html = urllib.request.urlopen(base + "/company.html?code=601567", timeout=10).read().decode("utf-8", "replace")
for m in re.finditer(r'src="([^"]*line-compare[^"]*)"', html):
    print("script", m.group(1))
for m in re.finditer(r'src="([^"]*company\.js[^"]*)"', html):
    print("script", m.group(1))

# quick syntax-ish: count unbalanced double quotes outside comments is hard;
# instead look for known broken pattern
print("broken_pat", "最大涨\ufffd" in text or '涨\ufffd?,' in text)
