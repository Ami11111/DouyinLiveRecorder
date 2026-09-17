# -*- coding: utf-8 -*-
"""URL_config.ini 的解析与写回。

行格式(见 main.py:1981-2030):
    [清晰度,]URL[,主播: 名字]
行首 '#' 表示停用。长度 < 18 的行被 main.py 直接跳过, 可以安全地当作分组注释。

>>> 最关键的一条: '#' 必须紧贴 URL, 中间不能有空格。<<<
main.py:2007 是 line.lstrip('#') 而不是 lstrip('# ')。写成 "# https://..."
时解析出的 url 会带一个前导空格并进入 url_comments; 而录制线程里的 record_url
没有空格, main.py:459 的 `record_url in url_comments` 是列表精确匹配, 永远为
False —— 结果就是停用功能静默失效, ffmpeg 不会停。
"""

import hashlib
import os
import re
from dataclasses import dataclass, field

from webui.config_io import ENC, _atomic_write   # 复用同一套原子写

# 合法清晰度。注意 config.ini 里那个 key 名 "原画|超清|高清|标清|流畅" 漏写了
# "蓝光", 但 main.py:2017 的校验里是有的, 共 6 个。
QUALITY = ('原画', '蓝光', '超清', '高清', '标清', '流畅')

# main.py:1988 `if len(line) < 18: continue`
MIN_LINE_LEN = 18


class RoomsConflict(Exception):
    """文件在我们读取之后被改动过(多半是 main.py 自己改的)。"""


class RoomsError(Exception):
    """校验失败。"""


@dataclass
class Room:
    idx: int
    raw: str                 # 原始整行, 不含换行符
    kind: str                # 'room' 可解析 | 'other' 分组注释/空行/过短行
    enabled: bool = True
    quality: str = ''        # '' 表示跟随全局默认
    url: str = ''
    name: str = ''           # 不含 '主播: ' 前缀
    dirty: bool = False      # 只有被编辑过的行才重新序列化

    def to_json(self) -> dict:
        return {'idx': self.idx, 'kind': self.kind, 'raw': self.raw,
                'enabled': self.enabled, 'quality': self.quality,
                'url': self.url, 'name': self.name}


def parse_line(idx: int, body: str) -> Room:
    line = body.strip()
    # 与 main.py 的跳过规则保持一致: 过短的行它根本不解析, 我们也原样保留
    if len(line) < MIN_LINE_LEN:
        return Room(idx, body, 'other')

    enabled = not line.startswith('#')
    core = line.lstrip('#').strip() if not enabled else line

    parts = re.split('[,，]', core) if re.search('[,，]', core) else [core, '']
    if len(parts) == 1:
        quality, url, name = '', parts[0], ''
    elif len(parts) == 2:
        if _contains_url(parts[0]):
            quality, url, name = '', parts[0], parts[1]
        else:
            quality, url, name = parts[0], parts[1], ''
    else:
        quality, url, name = parts[0], parts[1], ','.join(parts[2:])

    quality = quality.strip()
    if quality and quality not in QUALITY:
        quality = ''          # 非法值当作"跟随全局"(main.py 会静默回落到原画)

    name = name.strip()
    if name.startswith('主播:'):
        name = name.split('主播:', 1)[1].strip()

    url = url.strip()
    if not _contains_url(url):
        return Room(idx, body, 'other')

    return Room(idx, body, 'room', enabled, quality, url, name)


def _contains_url(s: str) -> bool:
    # 与 main.py:1975 的 contains_url 同义
    return re.search(r'(https?://)?(www\.)?[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+(:\d+)?(/.*)?',
                     s.strip()) is not None


def serialize(r: Room) -> str:
    """未编辑过的行原样吐出 raw —— 这是往返无损的根本保证。"""
    if not r.dirty or r.kind != 'room':
        return r.raw
    return render(r.enabled, r.quality, r.url, r.name)


def render(enabled: bool, quality: str, url: str, name: str) -> str:
    seg = ([quality] if quality else []) + [url]
    s = ','.join(seg)
    if name:
        s += f',主播: {name}'
    # '#' 紧贴, 绝不加空格 —— 见模块 docstring
    return s if enabled else '#' + s


def validate(quality: str, url: str, name: str) -> tuple:
    """返回 (quality, url, name) 归一化结果; 不合法则抛 RoomsError。"""
    quality = (quality or '').strip()
    if quality and quality not in QUALITY:
        raise RoomsError(f'清晰度只能是 {"/".join(QUALITY)} 之一, 或留空表示跟随全局')

    url = (url or '').strip()
    if not url:
        raise RoomsError('直播间地址不能为空')
    if not url.startswith(('http://', 'https://')):
        raise RoomsError('地址必须以 http:// 或 https:// 开头')
    if re.search(r'[\s,，#]', url):
        raise RoomsError('地址里不能包含空格、逗号或 #')

    name = (name or '').strip()
    if re.search(r'[,，#\r\n]', name):
        raise RoomsError('主播名里不能包含逗号、# 或换行(会破坏行格式)')

    # 启用态的行长度必须 >= 18, 否则 main.py 会直接跳过这一行, 静默不录
    if len(render(True, quality, url, name)) < MIN_LINE_LEN:
        raise RoomsError(f'这一行太短(不足 {MIN_LINE_LEN} 字符), 程序会跳过它。'
                         f'请补上主播名, 或使用完整的直播间地址')
    return quality, url, name


def _revision(raw: str) -> str:
    return hashlib.sha1(raw.encode('utf-8', 'replace')).hexdigest()[:12]


def load(path: str) -> tuple:
    """返回 (rev, rooms, eol)。"""
    if not os.path.isfile(path):
        return _revision(''), [], '\n'
    with open(path, 'r', encoding=ENC, errors='ignore', newline='') as f:
        raw = f.read()
    eol = '\r\n' if raw.count('\r\n') else '\n'
    rooms = [parse_line(i, ln.rstrip('\r\n'))
             for i, ln in enumerate(raw.splitlines(keepends=True))]
    return _revision(raw), rooms, eol


def dump(rooms, eol: str) -> str:
    lines = [serialize(r) for r in rooms]
    return ''.join(ln + eol for ln in lines)


def mutate(path: str, lock, rev, fn, backup=None, backup_dir=None) -> tuple:
    """在锁内做 读-改-原子写。fn(rooms) 就地修改列表。

    lock 就是 main.py:76 的 file_update_lock。注意它不可重入, 而
    main.py 的 update_file()/delete_line() 自己会去 acquire 它 ——
    所以我们持锁期间绝不能调用那两个函数, 只做自己的读写。
    临界区是一个 1KB 文件的读写, 亚毫秒级, 不会拖慢主循环。
    """
    with lock:
        cur_rev, rooms, eol = load(path)
        if rev is not None and rev != cur_rev:
            raise RoomsConflict('文件已被录制程序改动, 请刷新后重试')
        fn(rooms)
        text = dump(rooms, eol)
        if backup and backup_dir and os.path.isfile(path):
            try:
                backup(path, backup_dir)
            except Exception:
                pass
        _atomic_write(path, text)
        return load(path)[:2]


# ---------------------------------------------------------------- 具体操作

def _find(rooms, url: str) -> Room:
    for r in rooms:
        if r.kind == 'room' and r.url == url:
            return r
    raise RoomsError(f'找不到这个直播间: {url}')


def op_add(quality: str, url: str, name: str):
    quality, url, name = validate(quality, url, name)

    def fn(rooms):
        for r in rooms:
            if r.kind == 'room' and r.url == url:
                raise RoomsError('这个直播间已经在列表里了')
        rooms.append(Room(len(rooms), render(True, quality, url, name), 'room',
                          True, quality, url, name, dirty=True))
    return fn


def op_update(url: str, quality: str, new_url: str, name: str):
    quality, new_url, name = validate(quality, new_url or url, name)

    def fn(rooms):
        r = _find(rooms, url)
        if new_url != url:
            for other in rooms:
                if other is not r and other.kind == 'room' and other.url == new_url:
                    raise RoomsError('已经有另一个直播间用了这个地址')
        r.quality, r.url, r.name, r.dirty = quality, new_url, name, True
    return fn


def op_delete(url: str):
    def fn(rooms):
        r = _find(rooms, url)
        rooms.remove(r)
    return fn


def op_toggle(url: str, enabled: bool):
    def fn(rooms):
        r = _find(rooms, url)
        if r.enabled == enabled:
            return
        r.enabled = enabled
        # 纯前缀增删, 其余字节保持不变, 所以不设 dirty
        r.raw = r.raw.lstrip('#').strip() if enabled else '#' + r.raw.strip().lstrip('#').strip()
    return fn


def op_toggle_all(enabled: bool):
    def fn(rooms):
        for r in rooms:
            if r.kind != 'room' or r.enabled == enabled:
                continue
            r.enabled = enabled
            r.raw = r.raw.lstrip('#').strip() if enabled else '#' + r.raw.strip().lstrip('#').strip()
    return fn


def op_reorder(order):
    """order: URL 数组, 表示期望的新顺序。

    'other' 行(分组注释 #douyin / 空行)保持吸附在它下方第一个直播间之前。
    """
    def fn(rooms):
        pos = {u: i for i, u in enumerate(order)}
        blocks, pending = [], []
        for r in rooms:
            if r.kind == 'room':
                blocks.append((pos.get(r.url, 10 ** 6), pending, r))
                pending = []
            else:
                pending.append(r)
        blocks.sort(key=lambda b: b[0])
        out = []
        for _, lead, r in blocks:
            out.extend(lead)
            out.append(r)
        out.extend(pending)          # 文件末尾的孤立注释行
        rooms[:] = out
    return fn
