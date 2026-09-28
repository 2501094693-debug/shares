from pathlib import Path
import re

root = Path(r"c:\Users\Administrator\Desktop\test\frontend")
for path in root.rglob("*.html"):
    text = path.read_text(encoding="utf-8")
    new = re.sub(r'nav\.js\?v=[^"]+', "nav.js?v=mine-20260928", text)
    new = re.sub(r'orbit-prefetch\.js\?v=[^"]+', "orbit-prefetch.js?v=mine-20260928", new)
    if new != text:
        path.write_text(new, encoding="utf-8")
        print("updated", path)
