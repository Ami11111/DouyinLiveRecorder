# -*- coding: utf-8 -*-
"""JSON API 的各个处理函数。

约定: 每个 handler 形如 handler(ctx, req) -> (status_code, payload_obj)。
抛出 ApiError 会被 server 转成对应状态码的 JSON 错误。
"""

import os
import shutil

from webui import config_io as C
from webui import platforms
from webui import rooms_io as R
from webui import schema as S


# 前后端共用的复合 key 分隔符。用 chr(31) 在运行时构造, 避免源码里出现
# 字面控制字符(那会让 .py 文件变成非法源码)。
KEYSEP = chr(31)


def f_key(section: str, key: str) -> str:
    return section + KEYSEP + key


class ApiError(Exception):
    def __init__(self, status: int, message: str, detail=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.detail = detail


# ------------------------------------------------------------------ 只读接口

def h_meta(ctx, req):
    status = _safe_status(ctx)
    save_path = (status.get('effective', {}) or {}).get('video_save_path') or ctx.default_path
    return 200, {
        'version': ctx.version,
        'config_file': os.path.abspath(ctx.config_file),
        'url_config_file': os.path.abspath(ctx.url_config_file),
        'backup_dir': os.path.abspath(ctx.backup_dir),
        'host': ctx.host, 'port': ctx.port,
        'lan_enabled': ctx.lan_mode,
        'lan_urls': ctx.lan_urls,
        'token_required': bool(ctx.token),
        'is_lan_request': req.is_lan,
        'lan_lock_script': ctx.lan_lock_script,
        'readonly_keys': ([list(k) for k in S.LAN_READONLY_KEYS]
                          if (req.is_lan and ctx.lan_lock_script) else []),
        'disk': _disk(save_path),
        'save_path': save_path,
        'tabs': S.TABS,
    }


def h_status(ctx, req):
    st = _safe_status(ctx)
    save_path = (st.get('effective', {}) or {}).get('video_save_path') or ctx.default_path
    st['disk'] = _disk(save_path)
    try:
        st['rooms_rev'] = R.load(ctx.url_config_file)[0]
    except Exception:
        st['rooms_rev'] = None
    return 200, st


def _safe_status(ctx) -> dict:
    """主程序还没跑完第一轮时, get_status 里的某些全局变量可能还不存在。"""
    try:
        return ctx.get_status() or {}
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}', 'recording': [],
                'monitoring': 0, 'running': [], 'effective': {}}


def _disk(path: str) -> dict:
    probe = path or '.'
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        usage = shutil.disk_usage(probe or '.')
        return {'ok': True, 'path': probe, 'exists': os.path.isdir(path or ''),
                'total': usage.total, 'free': usage.free, 'used': usage.used}
    except Exception as e:
        return {'ok': False, 'path': probe, 'exists': False, 'error': str(e)}


def h_schema(ctx, req):
    fields = _fields(ctx)
    return 200, {'fields': [f.to_json() for f in fields], 'tabs': S.TABS}


def _fields(ctx):
    cookie_keys = C.read_section_keys(ctx.config_file, S.SECTION_COOKIE)
    return S.all_fields(cookie_keys)


def h_config_get(ctx, req):
    values = C.read_all(ctx.config_file)
    out = {}
    for f in _fields(ctx):
        raw = values.get((f.section.casefold(), f.key.casefold()), {}).get('value', '')
        kk = f_key(f.section, f.key)
        out[kk] = S.mask(raw) if f.secret else S.from_file_value(f, raw)
    return 200, {'values': out}


def h_config_reveal(ctx, req):
    """单个 secret 的明文。一次只给一个, 避免误操作时整屏凭据被截图/录屏。"""
    section = req.query.get('section', '')
    key = req.query.get('key', '')
    idx = S.index_by_key(_fields(ctx))
    f = idx.get((section.casefold(), key.casefold()))
    if not f:
        raise ApiError(404, '没有这个配置项')
    if not f.secret:
        raise ApiError(400, '这一项本来就不是密文')
    raw = C.read_all(ctx.config_file).get(
        (f.section.casefold(), f.key.casefold()), {}).get('value', '')
    return 200, {'section': f.section, 'key': f.key, 'value': raw}


# ------------------------------------------------------------------ 配置写入

def h_config_set(ctx, req):
    changes = (req.json or {}).get('changes')
    if not isinstance(changes, list) or not changes:
        raise ApiError(400, '没有需要保存的改动')

    idx = S.index_by_key(_fields(ctx))
    resolved, errors = [], {}
    for item in changes:
        if not isinstance(item, dict):
            continue
        section = str(item.get('section', ''))
        key = str(item.get('key', ''))
        kk = (section.casefold(), key.casefold())
        f = idx.get(kk)
        if not f:
            errors[f_key(section, key)] = '没有这个配置项'
            continue
        if req.is_lan and ctx.lan_lock_script and kk in S.LAN_READONLY_KEYS:
            errors[f_key(section, key)] = '局域网访问时这一项被锁定为只读'
            continue
        try:
            resolved.append((f.section, f.key, S.to_file_value(f, item.get('value'))))
        except S.ValidationError as e:
            errors[f_key(section, key)] = str(e)

    if errors:
        raise ApiError(422, '有 %d 项没能通过校验' % len(errors), detail=errors)

    try:
        C.apply_changes(ctx.config_file, resolved,
                        backup=ctx.backup_file, backup_dir=ctx.backup_dir)
    except C.ConfigWriteError as e:
        raise ApiError(503, str(e))
    except ValueError as e:
        raise ApiError(422, str(e))

    # 回读校验: 万一 main.py 的默认值回填恰好在这一瞬间把文件整体覆盖了
    after = C.read_all(ctx.config_file)
    drifted = [f'{s}.{k}' for s, k, v in resolved
               if after.get((s.casefold(), k.casefold()), {}).get('value', '') != v]
    return 200, {'saved': len(resolved), 'drifted': drifted,
                 'restart_required': _needs_restart(idx, resolved)}


def _needs_restart(idx, resolved) -> list:
    out = []
    for s, k, _ in resolved:
        f = idx.get((s.casefold(), k.casefold()))
        if f and f.restart:
            out.append(f.label)
    return out


# ------------------------------------------------------------------ 直播间

def h_rooms_get(ctx, req):
    rev, rooms, _ = R.load(ctx.url_config_file)
    st = _safe_status(ctx)
    running = set(st.get('running') or [])
    not_record = set(st.get('not_record') or [])
    # recording 里的 key 是 "序号N 主播名", 没有 URL, 所以录制中状态按 running 判断
    items = []
    for r in rooms:
        if r.kind != 'room':
            continue
        d = r.to_json()
        d['known_platform'] = platforms.is_known(r.url)
        d['running'] = r.url in running
        d['skipped'] = r.url in not_record
        items.append(d)
    return 200, {'rev': rev, 'rooms': items,
                 'default_quality': (st.get('effective') or {}).get('video_record_quality') or '原画',
                 'qualities': list(R.QUALITY)}


def _build(make_op):
    """op_add/op_update 在构造闭包时就会校验参数, 这里把校验异常转成 422,
    否则它会绕过 _mutate 的 except 直接冒泡成 500。"""
    try:
        return make_op()
    except R.RoomsError as e:
        raise ApiError(422, str(e))


def _mutate(ctx, req, fn):
    rev = (req.json or {}).get('rev')
    try:
        new_rev, rooms = R.mutate(ctx.url_config_file, ctx.url_file_lock, rev, fn,
                                  backup=ctx.backup_file, backup_dir=ctx.backup_dir)
    except R.RoomsConflict as e:
        raise ApiError(409, str(e))
    except R.RoomsError as e:
        raise ApiError(422, str(e))
    except C.ConfigWriteError as e:
        raise ApiError(503, str(e))
    return h_rooms_get(ctx, req)


def h_room_add(ctx, req):
    b = req.json or {}
    url = str(b.get('url', '')).strip()
    warn = None if platforms.is_known(url) else \
        '这个域名不在已知平台列表里, 录制程序可能会自动把它注释掉'
    op = _build(lambda: R.op_add(str(b.get('quality', '')), url, str(b.get('name', ''))))
    status, payload = _mutate(ctx, req, op)
    payload['warning'] = warn
    return status, payload


def h_room_update(ctx, req):
    b = req.json or {}
    op = _build(lambda: R.op_update(
        str(b.get('url', '')), str(b.get('quality', '')),
        str(b.get('new_url', '') or b.get('url', '')), str(b.get('name', ''))))
    return _mutate(ctx, req, op)


def h_room_delete(ctx, req):
    return _mutate(ctx, req, R.op_delete(str((req.json or {}).get('url', ''))))


def h_room_toggle(ctx, req):
    b = req.json or {}
    return _mutate(ctx, req, R.op_toggle(str(b.get('url', '')), bool(b.get('enabled'))))


def h_room_toggle_all(ctx, req):
    return _mutate(ctx, req, R.op_toggle_all(bool((req.json or {}).get('enabled'))))


def h_room_reorder(ctx, req):
    order = (req.json or {}).get('order')
    if not isinstance(order, list):
        raise ApiError(400, 'order 必须是一个地址数组')
    return _mutate(ctx, req, R.op_reorder([str(u) for u in order]))


# ------------------------------------------------------------------ 日志与备份

def h_logs(ctx, req):
    path = os.path.join(os.path.dirname(os.path.abspath(ctx.config_file)),
                        '..', 'logs', 'streamget.log')
    path = os.path.normpath(path)
    try:
        n = min(int(req.query.get('lines', 200)), 2000)
    except ValueError:
        n = 200
    if not os.path.isfile(path):
        return 200, {'path': path, 'lines': [], 'missing': True}
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = min(size, 256 * 1024)
            f.seek(size - block)
            text = f.read().decode('utf-8', 'replace')
        lines = text.splitlines()[-n:]
    except OSError as e:
        raise ApiError(500, f'读取日志失败: {e}')
    return 200, {'path': path, 'lines': lines, 'missing': False}


def h_backups(ctx, req):
    d = ctx.backup_dir
    if not os.path.isdir(d):
        return 200, {'backups': []}
    out = []
    for name in os.listdir(d):
        p = os.path.join(d, name)
        if not os.path.isfile(p):
            continue
        try:
            stat = os.stat(p)
        except OSError:
            continue
        target = 'config.ini' if name.startswith('config.ini') else (
            'URL_config.ini' if name.startswith('URL_config.ini') else '')
        if not target:
            continue
        out.append({'name': name, 'target': target,
                    'size': stat.st_size, 'mtime': int(stat.st_mtime)})
    out.sort(key=lambda x: x['mtime'], reverse=True)
    return 200, {'backups': out}


def h_restore(ctx, req):
    name = str((req.json or {}).get('name', ''))
    # 只接受 backups 列出来的文件名, 杜绝路径穿越
    allowed = {b['name']: b for b in h_backups(ctx, req)[1]['backups']}
    if name not in allowed:
        raise ApiError(404, '没有这个备份文件')
    src = os.path.join(ctx.backup_dir, name)
    dst = ctx.config_file if allowed[name]['target'] == 'config.ini' else ctx.url_config_file

    with open(src, 'r', encoding=C.ENC, errors='ignore', newline='') as f:
        text = f.read()
    try:
        ctx.backup_file(dst, ctx.backup_dir)     # 还原之前先把当前状态也备份一份
    except Exception:
        pass
    if dst == ctx.url_config_file:
        with ctx.url_file_lock:
            C._atomic_write(dst, text)
    else:
        C._atomic_write(dst, text)
    return 200, {'restored': name, 'target': os.path.basename(dst)}


ROUTES = {
    ('GET', '/api/meta'): h_meta,
    ('GET', '/api/status'): h_status,
    ('GET', '/api/schema'): h_schema,
    ('GET', '/api/config'): h_config_get,
    ('GET', '/api/config/reveal'): h_config_reveal,
    ('POST', '/api/config'): h_config_set,
    ('GET', '/api/rooms'): h_rooms_get,
    ('POST', '/api/rooms/add'): h_room_add,
    ('POST', '/api/rooms/update'): h_room_update,
    ('POST', '/api/rooms/delete'): h_room_delete,
    ('POST', '/api/rooms/toggle'): h_room_toggle,
    ('POST', '/api/rooms/toggle_all'): h_room_toggle_all,
    ('POST', '/api/rooms/reorder'): h_room_reorder,
    ('GET', '/api/logs'): h_logs,
    ('GET', '/api/backups'): h_backups,
    ('POST', '/api/restore'): h_restore,
}
