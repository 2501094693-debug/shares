"""Level-2 接入层：只保留私有 TCP 通道占位。

链路：

    connect() → handshake() → subscribe() → recv_ticks() → on_tick()

当前 ``CaptureTransport`` 只负责建立 TCP 连接并把原始字节交给 ``decode`` 回调；
真实鉴权帧、订阅帧、心跳和 ``decode_frame`` 需要根据 PC 端抓包结果补齐。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, Optional, Protocol

from company.detail.level2 import (
    Level2CaptureClient,
    Level2Tick,
    REALTIME_CBAS_REQUEST,
    decode_frame,
    parse_frame,
)


TickHandler = Callable[[Level2Tick], None]
FrameDecoder = Callable[[bytes], list[Level2Tick]]


class Level2Error(RuntimeError):
    """接入层错误。"""


class Level2Transport(Protocol):
    """接入层最小协议。"""

    def connect(self) -> None: ...

    def handshake(self) -> None: ...

    def subscribe(self, codes: Iterable[str]) -> None: ...

    def recv_ticks(self) -> Iterator[Level2Tick]: ...

    def close(self) -> None: ...


@dataclass
class CaptureTransport:
    """私有 TCP 通道占位 transport。

    已能连接 ``Level2CaptureClient``，但只吐原始帧；真实解码需要在 ``decode``
    回调里实现 ``level2.decode_frame``。

    TODO（按抓包补齐）：
    - ``handshake``：发送登录/鉴权帧并校验应答；
    - ``subscribe``：发送股票订阅帧；
    - ``recv_ticks``：处理心跳、粘包/半包与消息分发。
    """

    host: str
    port: int
    decode: FrameDecoder = decode_frame
    timeout: float = 5.0
    _client: Optional[Level2CaptureClient] = field(default=None, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _codes: list[str] = field(default_factory=list, init=False, repr=False)
    _challenge: Optional[dict] = field(default=None, init=False, repr=False)

    def connect(self) -> None:
        self._closed = False
        self._client = Level2CaptureClient(self.host, self.port, timeout=self.timeout)
        self._client.connect()

    def handshake(self) -> None:
        if self._client is None:
            raise Level2Error("connect() 未调用")
        # 发送抓包得到的 realtimecbas.dat 请求帧，服务器应答签名质询。
        self._client.send(REALTIME_CBAS_REQUEST)
        response = self._client.recv()
        try:
            frame = parse_frame(response)
            self._challenge = frame.headers
        except ValueError:
            self._challenge = {"raw": response.hex()}

    def subscribe(self, codes: Iterable[str]) -> None:
        if self._client is None:
            raise Level2Error("connect() 未调用")
        self._codes = [str(code) for code in codes]
        # TODO: 发送抓包得到的订阅帧，例如：
        # self._client.send(bytes.fromhex("..."))

    def recv_ticks(self) -> Iterator[Level2Tick]:
        if self._client is None:
            raise Level2Error("connect() 未调用")
        while not self._closed:
            data = self._client.recv()
            if not data:
                break
            for tick in self.decode(data):
                yield tick

    def close(self) -> None:
        self._closed = True
        if self._client is not None:
            self._client.close()
            self._client = None

    @property
    def challenge(self) -> Optional[dict]:
        return self._challenge


class Level2Client:
    """接入客户端：负责把 transport 的输出稳定地分发给回调。"""

    def __init__(self, transport: Level2Transport, reconnect_seconds: float = 2.0) -> None:
        self.transport = transport
        self.reconnect_seconds = reconnect_seconds
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self.last_error: Optional[BaseException] = None

    def start(self, codes: Iterable[str], on_tick: TickHandler) -> None:
        if self._worker is not None and self._worker.is_alive():
            raise Level2Error("客户端已在运行")
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._run, args=(list(codes), on_tick), daemon=True
        )
        self._worker.start()

    def _run(self, codes: list[str], on_tick: TickHandler) -> None:
        while not self._stop.is_set():
            try:
                self.transport.connect()
                self.transport.handshake()
                self.transport.subscribe(codes)
                for tick in self.transport.recv_ticks():
                    if self._stop.is_set():
                        break
                    on_tick(tick)
            except Exception as exc:  # noqa: BLE001
                self.last_error = exc
                if self._stop.wait(self.reconnect_seconds):
                    break
            finally:
                try:
                    self.transport.close()
                except Exception:
                    pass

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=timeout)
            self._worker = None


def stream(
    codes: Iterable[str],
    *,
    host: str,
    port: int,
    decode: FrameDecoder = decode_frame,
    duration_seconds: float = 5.0,
    timeout: float = 5.0,
) -> list[Level2Tick]:
    """连接一次私有通道，在 ``duration_seconds`` 内收集解码后的逐笔。"""
    code_list = [str(code) for code in codes]
    if not code_list:
        raise Level2Error("codes 不能为空")

    transport = CaptureTransport(host=host, port=port, decode=decode, timeout=timeout)
    transport.connect()
    try:
        transport.handshake()
        transport.subscribe(code_list)
        ticks: list[Level2Tick] = []
        deadline = time.monotonic() + duration_seconds
        for tick in transport.recv_ticks():
            ticks.append(tick)
            if time.monotonic() >= deadline:
                break
        return ticks
    finally:
        transport.close()


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Level-2 私有 TCP 通道探针")
    parser.add_argument("code", nargs="?", default="", help="股票代码，如 600519（握手模式可省略）")
    parser.add_argument("--host", required=True, help="抓包得到的服务器地址")
    parser.add_argument("--port", required=True, type=int, help="抓包得到的端口")
    parser.add_argument("--duration", type=float, default=5.0, help="采集秒数")
    parser.add_argument("--timeout", type=float, default=5.0, help="连接超时秒数")
    parser.add_argument("--handshake", action="store_true", help="仅执行握手并打印服务器质询")
    args = parser.parse_args()

    if args.handshake or not args.code:
        transport = CaptureTransport(host=args.host, port=args.port, timeout=args.timeout)
        transport.connect()
        try:
            transport.handshake()
            print(json.dumps(transport.challenge, ensure_ascii=False, indent=2))
        finally:
            transport.close()
    else:
        result = stream(
            [args.code],
            host=args.host,
            port=args.port,
            duration_seconds=args.duration,
            timeout=args.timeout,
        )
        print(json.dumps([tick.to_dict() for tick in result], ensure_ascii=False, indent=2))
