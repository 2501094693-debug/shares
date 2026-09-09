import sys
from pathlib import Path

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


#!/usr/bin/env python3
"""快速测试 OPENAI_API_KEY 是否可用。"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"


def load_env_file() -> None:
    if not ENV.exists():
        return
    for raw in ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def mask(k: str) -> str:
    if not k or len(k) < 12:
        return "(未配置或过短)"
    return f"{k[:8]}...{k[-4:]}"


def main() -> int:
    load_env_file()

    key = os.getenv("OPENAI_API_KEY", "")
    print(f"OPENAI_API_KEY: {mask(key)}")
    print(f"OPENAI_BASE_URL: {os.getenv('OPENAI_BASE_URL') or '(默认)'}")
    print(f"LLM_MODEL: {os.getenv('LLM_MODEL') or os.getenv('OPENAI_MODEL') or '(未配置)'}")
    print(f"LLM_REQUEST_TIMEOUT: {os.getenv('LLM_REQUEST_TIMEOUT', '600')}")

    if not key or key == "sk-your-key-here":
        print("RESULT: FAIL — API Key 未配置或仍是占位符")
        return 1

    sys.path.insert(0, str(Path(__file__).parent))
    from langchain_core.messages import HumanMessage
    from agent.utils.llm import get_llm

    try:
        llm = get_llm()
        resp = llm.invoke([HumanMessage(content="只回复一个字：好")])
        text = (resp.content or "").strip()
        print("RESULT: OK — API Key 可用")
        print(f"模型回复: {text[:80]}")
        return 0
    except Exception as exc:
        print("RESULT: FAIL — API Key 不可用或网络/模型配置有误")
        print(f"错误: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
