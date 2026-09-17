# -*- coding: utf-8 -*-
"""config.ini 的安全读写。

为什么不用 configparser 写回:
  configparser.write() 会吃掉所有注释行, 并把 key 全部小写化。
  当前 config.ini 里有 "# 可选微信|钉钉|tg|邮箱|bark|ntfy|pushplus 可填多个"
  这类注释, 以及 "SMTP邮件服务器" 这种大写 key, 全都会被毁掉。

本模块改为逐行文本替换: 只替换命中行的"值"那一段, 其余字节原封不动
(包括 key 的原始拼写、'=' 前后的空格数、行尾 \\r\\n / \\n)。

三条硬约束, 违反任何一条都会出真 bug:
  * 值里的 '%' 绝不转义。main.py 用的是 RawConfigParser(无插值),
    转义会把抖音 cookie 里大量的 %7C 写成 %%7C。
    (src/utils.py:105 那句 replace('%','%%') 是针对带插值的 ConfigParser 写的,
     与本项目的读取方式不匹配, 属于上游 bug。)
  * 值里的 '#' / ';' 也原样保留 —— configparser 默认 inline_comment_prefixes=None,
    行内 '#' 属于值的一部分。
  * 编码读写两端都必须是 utf-8-sig(带 BOM), 与 main.py 的 text_encoding 一致。
    混用会导致双 BOM 或丢 BOM。
"""

import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

ENC = 'utf-8-sig'

# 这把锁只保护"我们自己"的写入。config.ini 在上游是完全无锁的:
# main.py:1782 的默认值回填、src/utils.py:103 的 cookie 回写都是裸写。
# 对策见 ensure_defaults() 的 docstring。
_WRITE_LOCK = threading.RLock()

SEC_RE = re.compile(r'^\s*\[(?P<name>[^]]+)\]\s*$')
OPT_RE = re.compile(r'^(?P<pre>\s*)(?P<key>[^\s:=][^:=]*?)(?P<sep>\s*[:=]\s*)(?P<val>.*)$')


class ConfigWriteError(Exception):
    """配置文件写入失败(通常是被其他进程占用)。"""


@dataclass
class _Rec:
    kind: str                       # 'section' | 'option' | 'raw'
    text: str = ''                  # 原始整行, 含行尾换行符
    section: str = ''               # 所属 section 的原名
    key: str = ''
    pre: str = ''
    sep: str = ''
    val: str = ''
    eol: str = '\n'
    cont: list = field(default_factory=list)   # option 的续行, 含换行符


def _is_comment(body: str) -> bool:
    s = body.lstrip()
    return s[:1] in ('#', ';')


def _detect_eol(raw: str) -> str:
    crlf = raw.count('\r\n')
    return '\r\n' if crlf and crlf >= (raw.count('\n') - crlf) else '\n'


def _scan(raw: str) -> tuple:
    """把文件切成有序的记录列表。返回 (records, eol)。"""
    eol = _detect_eol(raw)
    lines = raw.splitlines(keepends=True)
    recs, cur, i = [], '', 0

    while i < len(lines):
        ln = lines[i]
        body = ln.rstrip('\r\n')
        line_eol = ln[len(body):] or eol
        i += 1

        if not body.strip() or _is_comment(body):
            recs.append(_Rec('raw', ln))
            continue

        m = SEC_RE.match(body)
        if m:
            cur = m.group('name')
            recs.append(_Rec('section', ln, section=cur))
            continue

        m = OPT_RE.match(body)
        if m and cur:
            # 吃掉该 option 的续行: 以空白开头的非空、非注释行,
            # configparser 视之为值的一部分。
            cont = []
            while i < len(lines):
                nxt = lines[i]
                nbody = nxt.rstrip('\r\n')
                if not nbody.strip() or nbody[:1] not in (' ', '\t') or _is_comment(nbody):
                    break
                cont.append(nxt)
                i += 1
            recs.append(_Rec('option', ln, section=cur, key=m.group('key'),
                             pre=m.group('pre'), sep=m.group('sep'), val=m.group('val'),
                             eol=line_eol, cont=cont))
            continue

        recs.append(_Rec('raw', ln))

    return recs, eol


def _render(recs: Iterable) -> str:
    out = []
    for r in recs:
        out.append(r.text)
        if r.kind == 'option':
            out.extend(r.cont)
    return ''.join(out)


def sanitize_value(v) -> str:
    """校验并归一化一个配置值。绝不对 '%' 做任何转义。"""
    v = '' if v is None else str(v)
    if '\n' in v or '\r' in v:
        raise ValueError('配置值里不能包含换行符')
    return v.strip()


def _atomic_write(path: str, text: str) -> None:
    """写临时文件 + os.replace。临时文件必须与目标同目录, 否则 replace 不原子。"""
    directory = os.path.dirname(os.path.abspath(path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=directory,
                               prefix='.' + os.path.basename(path) + '.', suffix='.tmp')
    try:
        # newline='' 让我们完全掌控行尾, 不做任何自动转换
        with os.fdopen(fd, 'w', encoding=ENC, newline='') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        for _ in range(6):
            try:
                os.replace(tmp, path)   # 同文件系统 -> 真原子
                tmp = None
                break
            except PermissionError:
                # Windows 上目标被其他进程打开时会这样
                time.sleep(0.15)
        else:
            raise ConfigWriteError('配置文件正被占用, 写入失败, 请稍后重试')
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def read_all(path: str) -> dict:
    """读出全部配置项。

    返回 {(section_cf, key_cf): {'section','key','value'}},
    key 用 casefold 做索引 —— 因为 configparser 会把 key 小写化,
    文件里可能是 'SMTP邮件服务器' 也可能是 'smtp邮件服务器'。
    """
    if not os.path.isfile(path):
        return {}
    with open(path, 'r', encoding=ENC, newline='') as f:
        raw = f.read()
    recs, _ = _scan(raw)
    result = {}
    for r in recs:
        if r.kind != 'option':
            continue
        # 续行也是值的一部分, 拼进来(strip 掉缩进)
        value = r.val
        if r.cont:
            value = '\n'.join([value] + [c.rstrip('\r\n').strip() for c in r.cont])
        result[(r.section.casefold(), r.key.casefold())] = {
            'section': r.section, 'key': r.key, 'value': value,
        }
    return result


def read_section_keys(path: str, section: str) -> list:
    """按文件顺序列出某个 section 下的 key 原名。给 Cookie 那 50 项做动态发现用。"""
    if not os.path.isfile(path):
        return []
    with open(path, 'r', encoding=ENC, newline='') as f:
        recs, _ = _scan(f.read())
    want = section.casefold()
    return [r.key for r in recs if r.kind == 'option' and r.section.casefold() == want]


def apply_changes(path: str, changes, backup: Callable = None, backup_dir: str = None) -> int:
    """把 changes 写进 config.ini, 只改命中的行。

    changes: 可迭代的 (section, key, value)
    返回实际写入的项数。
    """
    pending = {}
    for section, key, value in changes:
        pending[(section.casefold(), key.casefold())] = (section, key, sanitize_value(value))
    if not pending:
        return 0

    with _WRITE_LOCK:
        with open(path, 'r', encoding=ENC, newline='') as f:
            raw = f.read()
        recs, eol = _scan(raw)

        hit = set()
        for r in recs:
            if r.kind != 'option':
                continue
            kk = (r.section.casefold(), r.key.casefold())
            if kk in pending:
                hit.add(kk)
                r.val = pending[kk][2]
                r.text = r.pre + r.key + r.sep + r.val + r.eol
                r.cont = []          # 值被整体替换, 旧续行作废

        missing = [v for k, v in pending.items() if k not in hit]
        if missing:
            recs = _insert_missing(recs, missing, eol)

        text = _render(recs)
        if text == raw:
            return len(pending)

        if backup and backup_dir:
            try:
                backup(path, backup_dir)
            except Exception:
                pass     # 备份失败不能挡住保存
        _atomic_write(path, text)
        return len(pending)


def _insert_missing(recs: list, missing: list, eol: str, comments: dict = None) -> list:
    """把文件里不存在的 key 插进对应 section; section 不存在则追加到文件末尾。"""
    comments = comments or {}
    by_section = {}
    for section, key, value in missing:
        by_section.setdefault(section, []).append((section, key, value))

    existing = {r.section.casefold() for r in recs if r.kind == 'section'}

    for section, items in by_section.items():
        new_recs = []
        for section_name, key, value in items:
            cmt = comments.get((section_name.casefold(), key.casefold()))
            if cmt:
                new_recs.append(_Rec('raw', cmt.rstrip('\r\n') + eol))
            line = f'{key} = {value}{eol}'
            new_recs.append(_Rec('option', line, section=section_name, key=key,
                                 pre='', sep=' = ', val=value, eol=eol))

        if section.casefold() in existing:
            # 插到该 section 最后一个 option(含其续行)之后
            last = -1
            for idx, r in enumerate(recs):
                if r.kind == 'option' and r.section.casefold() == section.casefold():
                    last = idx
            if last < 0:   # section 存在但一项都没有 -> 插在 section 头之后
                for idx, r in enumerate(recs):
                    if r.kind == 'section' and r.section.casefold() == section.casefold():
                        last = idx
                        break
            recs = recs[:last + 1] + new_recs + recs[last + 1:]
        else:
            tail = []
            if recs and not recs[-1].text.endswith(('\n', '\r')):
                recs[-1].text += eol
            tail.append(_Rec('raw', eol))
            tail.append(_Rec('section', f'[{section}]{eol}', section=section))
            recs = recs + tail + new_recs
            existing.add(section.casefold())

    return recs


def ensure_defaults(path: str, defaults) -> int:
    """缺哪补哪, 已存在的一律不动。幂等。

    defaults: 可迭代的 (section, key, value, comment); comment 可为 ''

    为什么必须走我们自己的写入器, 而不是让 main.py 的 read_config_value 去补:
    read_config_value 在读不到 key 时会 config_parser.write(f) 整体回写
    (main.py:1782), 那一下就会把用户 config.ini 里的全部注释抹掉、key 全部小写化。
    先把 key 补全, 那条分支就永远不会被触发。
    """
    if not os.path.isfile(path):
        with open(path, 'w', encoding=ENC, newline='') as f:
            f.write('')

    with _WRITE_LOCK:
        with open(path, 'r', encoding=ENC, newline='') as f:
            raw = f.read()
        recs, eol = _scan(raw)
        have = {(r.section.casefold(), r.key.casefold())
                for r in recs if r.kind == 'option'}

        missing, comments = [], {}
        for section, key, value, comment in defaults:
            kk = (section.casefold(), key.casefold())
            if kk in have:
                continue
            missing.append((section, key, sanitize_value(value)))
            if comment:
                comments[kk] = comment
            have.add(kk)

        if not missing:
            return 0

        text = _render(_insert_missing(recs, missing, eol, comments))
        _atomic_write(path, text)
        return len(missing)


def safe_update_config(file_path: str, section: str, key: str, new_value: str) -> None:
    """src/utils.py:update_config 的替代品, 签名保持一致。

    修掉上游那个版本的三个毛病:
      1. new_value.replace('%','%%') —— 对 RawConfigParser 来说是错的, 会写坏 cookie
      2. configparser.write() 抹掉注释、小写化 key
      3. 与界面的写入互踩(没有任何锁)
    """
    try:
        apply_changes(file_path, [(section, key, new_value)])
    except Exception:
        from loguru import logger
        logger.exception(f'写入配置失败: [{section}] {key}')
