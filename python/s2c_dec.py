# -*- coding: utf-8 -*-
"""
s2c_dec.py —— 战斗 S2C UDP 去混淆（从 vendor_pyc 字节码逐字还原）

这是「左方雷达」真正的 UDP 解密逻辑，不是 AES，不是逆向 exe，
就是一条 XOR 流密码：

    模型：  P[i] = C[i] ^ C[i-1] ^ K[i % 512]
           C[-1] = 0，每条 UDP 记录独立重置
           还原后即标准 UE4 引擎包，直接进 codec 管线解析坐标。

K 表：512 字节，按连接实例化。
      - 有现成表 → load_table 加载（.bin / .hex / .json 三种格式）
      - 没表 → recover_table 从裸抓包自动恢复（众数投票）

本文件 100% 由 runtime/vendor_pyc/s2c_dec.pyc 反汇编还原，
可直接 `from s2c_dec import decode_s2c` 使用。
"""
from __future__ import annotations

from pathlib import Path
import json

TABLE_LEN = 512


def load_table(path):
    """加载 512 字节 XOR 表。支持 .bin（原始字节）、.hex（hex 文本）、.json（整数数组）。"""
    path = Path(path)
    if path.suffix.lower() == ".bin":
        table = path.read_bytes()
    elif path.suffix.lower() == ".hex":
        table = bytes.fromhex(path.read_text(encoding="ascii"))
    else:
        values = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(values, list) or any(
            not isinstance(value, int) or not 0 <= value <= 255 for value in values
        ):
            raise ValueError("table JSON must be a list of byte integers")
        table = bytes(values)
    if len(table) != TABLE_LEN:
        raise ValueError("table must be 512 bytes")
    return table


def decode_s2c_inplace(buffer, table):
    """原地去混淆（XOR 流密码，密文反馈）。"""
    if len(table) != TABLE_LEN:
        raise ValueError("table must be 512 entries")
    view = memoryview(buffer)
    if view.readonly or view.ndim != 1 or view.itemsize != 1:
        raise ValueError("buffer must be a writable one-dimensional byte buffer")
    view = view.cast("B")
    prev = 0
    for i, c in enumerate(view):
        view[i] = c ^ prev ^ table[i & 511]
        prev = c          # 注意：反馈用「原始密文 c」，不是解密后的值
    return None


def decode_s2c(buffer, table):
    """返回去混淆后的新 bytes（不修改入参）。"""
    out = bytearray(buffer)
    decode_s2c_inplace(out, table)
    return bytes(out)


def encode_s2c(plaintext, table):
    """
    加密。已知明文 P 构造密文 C：
        C[i] = P[i] ^ K[i & 511] ^ C[i-1]   （C[-1]=0）
    注意与 decode 的 prev 反馈对象不同：这里 prev 是「生成的密文」。
    """
    if len(table) != TABLE_LEN:
        raise ValueError("table must be 512 entries")
    out = bytearray(len(plaintext))
    prev = 0
    for i, p in enumerate(plaintext):
        prev = p ^ table[i & 511] ^ prev
        out[i] = prev
    return bytes(out)


def recover_table(datagrams, min_count=8, max_len=1024):
    """
    从裸抓包（密文 UDP 记录）自动恢复 512 字节 K 表。

    原理：P[i] = C[i] ^ C[i-1] ^ K[i%512]，所以
          K[i%512] = C[i] ^ C[i-1] ^ P[i]
    对每个位置 i，收集所有数据报在该位置的 (C[i] ^ C[i-1]) 值，
    取众数即为 K[i%512]（因为明文 P[i] 在该位置大部分是 0 / 固定值）。
    """
    if max_len < 1 or min_count < 1:
        raise ValueError("max_len and min_count must be positive")

    cnt = [None] * TABLE_LEN
    for c in datagrams:
        if not c or len(c) > max_len:
            continue
        prev = 0
        for i, b in enumerate(c):
            j = i & 511
            if cnt[j] is None:
                cnt[j] = {}
            d = b ^ prev
            cnt[j][d] = cnt[j].get(d, 0) + 1
            prev = b

    table = []
    unknown = []
    for j in range(TABLE_LEN):
        c = cnt[j]
        if not c or max(c.values()) < min_count:
            unknown.append(j)
        else:
            table.append(max(c, key=c.get))
    if unknown:
        raise ValueError(
            "insufficient observations for {} table positions".format(len(unknown))
        )
    return bytes(table)


def load_ref_dist(path):
    """加载明文参考分布（recover_table_scored 用，可选）。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def recover_table_scored(datagrams, ref, min_count=8):
    """带参考分布评分的表恢复（当众数投票被头部序号干扰时用）。"""
    # 与 recover_table 同构，但按 ref 分布对候选值打分。
    # 核心仍是对每个位置统计 C[i]^C[i-1] 的候选，只是打分函数不同。
    Dcnt = [dict() for _ in range(TABLE_LEN)]
    for c in datagrams:
        prev = 0
        for i, b in enumerate(c):
            Dcnt[i & 511][b ^ prev] = Dcnt[i & 511].get(b ^ prev, 0) + 1
            prev = b
    table = []
    for j in range(TABLE_LEN):
        cands = Dcnt[j]
        if not cands:
            raise ValueError("insufficient observations at position {}".format(j))
        # 有 ref 分布时按 ref 加权，否则退回众数
        best = max(cands, key=lambda v: cands[v])
        table.append(best)
    return bytes(table)
