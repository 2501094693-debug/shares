"""Level-2 私有 TCP 通道探索骨架。

同花顺 PC/手机端的 Level-2 数据走私有二进制协议，协议未公开。本模块只提供
TCP 连接、收发与十六进制预览原语；真实握手、鉴权、心跳、订阅与帧解码需要
根据自行抓包结果实现（见 ``decode_frame`` 占位）。
"""

from __future__ import annotations

import base64
import socket
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Level2Tick:
    """一条解码后的逐笔成交。"""

    code: str
    time: str
    price: float
    volume: int  # 股
    side: str  # buy / sell / neutral
    order_id: Optional[int] = None
    trade_id: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


class Level2CaptureClient:
    """Level-2 私有通道探索用 TCP 客户端。

    这里只负责连接与原始字节收发，不猜测协议；握手/鉴权/订阅/解码在
    ``company.detail.ths_level2_client.CaptureTransport`` 中按抓包结果补齐。
    """

    def __init__(self, host: str, port: int, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)

    def send(self, payload: bytes) -> int:
        if self.sock is None:
            raise RuntimeError("socket 未连接")
        return self.sock.send(payload)

    def recv(self, size: int = 4096) -> bytes:
        if self.sock is None:
            raise RuntimeError("socket 未连接")
        return self.sock.recv(size)

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    @staticmethod
    def hex_preview(data: bytes, limit: int = 64) -> str:
        return data[:limit].hex(" ")


MAGIC = b"\xfd\xfd\xfd\xfd"

# 抓包得到的 realtimecbas.dat 请求帧（Level-2 订阅/握手的第一步）。
REALTIME_CBAS_REQUEST = bytes.fromhex(
    "fdfdfdfd3030303030306432090016000000001200f5000100000000000000bc000000"
    "66696c656e616d653d7265616c74696d65636261732e6461740d0a66696c65636c6173"
    "733d4331300d0a656e636f64653d200d0a7261776c656e3d3131320d0a726177646174"
    "6136343d5577414941565146346d704e51556c4f526c4a425455556f4c5445734d5377"
    "734b53355465584e305a5731545a5852306157356e4b4377784c4c2b71752f7258314d"
    "623074712f58744d7973583872484b53356a623235305a5868304b4345774d444d774e"
    "444d734e4441354e696b3d0d0a"
)


def split_frames(buf: bytes) -> list[bytes]:
    """按 4 字节魔数 ``fd fd fd fd`` 切分 TCP 字节流。"""
    frames: list[bytes] = []
    pos = buf.find(MAGIC)
    while pos != -1:
        nxt = buf.find(MAGIC, pos + len(MAGIC))
        frames.append(buf[pos:] if nxt == -1 else buf[pos:nxt])
        pos = nxt
    return frames


# 已抓到的 9603 心跳帧：fd fd fd fd + "00000004" + 09 00 00 00 00，客户端回 1 字节 00。
_HEARTBEAT = bytes.fromhex("fd fd fd fd 30 30 30 30 30 30 30 34 09 00 00 00 00")


def is_heartbeat(frame: bytes) -> bool:
    return frame == _HEARTBEAT


@dataclass
class Level2Frame:
    """一个已切分的私有协议帧。"""

    magic: bytes
    length: int
    body: bytes
    binary_header: bytes
    headers: dict
    raw: bytes  # rawdata64 解码后的字节（若有）


def parse_frame(frame: bytes) -> Level2Frame:
    """解析 ``fd fd fd fd`` 帧：8 位十六进制长度 + 二进制头 + key=value 文本头。"""
    if not frame.startswith(MAGIC):
        raise ValueError("帧魔数不匹配")
    if len(frame) < 12:
        raise ValueError("帧过短")
    length = int(frame[4:12], 16)
    body = frame[12 : 12 + length]
    marker = None
    for cand in (b"filename=", b"signvalid=", b"signhost=", b"signdate=", b"encode="):
        idx_cand = body.find(cand)
        if idx_cand != -1 and (marker is None or idx_cand < marker[1]):
            marker = (cand, idx_cand)
    if marker is None:
        binary_header, text = body, b""
    else:
        binary_header, text = body[: marker[1]], body[marker[1] :]
    headers: dict[str, str] = {}
    for line in text.split(b"\r\n"):
        if not line or b"=" not in line:
            continue
        key, value = line.split(b"=", 1)
        headers[key.decode("ascii", "replace")] = value.decode("ascii", "replace")
    raw = b""
    if headers.get("rawdata64"):
        try:
            raw = base64.b64decode(headers["rawdata64"])
        except Exception:  # noqa: BLE001
            raw = b""
    return Level2Frame(MAGIC, length, body, binary_header, headers, raw)


def decode_frame(data: bytes) -> list[Level2Tick]:
    """私有帧解码入口。

    目前只识别心跳帧并跳过；行情帧结构仍待按抓包结果实现。
    """
    ticks: list[Level2Tick] = []
    for frame in split_frames(data):
        if is_heartbeat(frame):
            continue
        try:
            parsed = parse_frame(frame)
        except ValueError:
            continue
        # TODO: 根据 parsed.headers / parsed.raw 解析逐笔并 append。
    return ticks
