from __future__ import annotations

from core.http import get_json
from world.indices.catalog import INDICES

H = {"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
HOSTS = ("https://push2.eastmoney.com", "https://push2delay.eastmoney.com")


def main() -> None:
    items = [i for b in INDICES.values() for i in b["items"]]
    for item in items:
        best = 0
        host_hit = "-"
        last = None
        for host in HOSTS:
            try:
                j = (
                    get_json(
                        f"{host}/api/qt/stock/kline/get",
                        params={
                            "secid": item["secid"],
                            "fields1": "f1,f2,f3,f4,f5,f6",
                            "fields2": "f51,f52,f53,f54,f55",
                            "klt": "101",
                            "fqt": "0",
                            "end": "20500101",
                            "lmt": "90",
                        },
                        headers=H,
                        timeout=10,
                    )
                    or {}
                )
            except Exception as exc:  # noqa: BLE001
                print(item["code"], host, type(exc).__name__, str(exc)[:60])
                continue
            data = j.get("data") or {}
            k = data.get("klines") or []
            if len(k) > best:
                best = len(k)
                host_hit = host.split("//", 1)[-1][:24]
                last = k[-1]
        print(f"{item['code']:8} n={best:3} host={host_hit} last={last}")


if __name__ == "__main__":
    main()
