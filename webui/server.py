# -*- coding: utf-8 -*-
"""HTTP 服务本体。

安全姿态(即使只监听 127.0.0.1 也全部启用):
  1. Host 头校验 —— 防 DNS rebinding。恶意网页可以把 evil.com 解析到
     127.0.0.1 再用你的浏览器访问我们, 此时它是"同源"的, CORS 拦不住,
     唯一的防线就是校验 Host 头。
  2. 自定义头做 CSRF 防护 —— 所有写操作必须带 X-DLR-CSRF。跨源 fetch 一旦
     加自定义头就会触发 preflight, 而我们从不响应任何 CORS 头, preflight
     必然失败; <form> 提交又加不了自定义头。两条路都被堵死。
  3. 明确不发任何 Access-Control-Allow-* 头。页面与 API 同源本就不需要,
     而一旦发了 '*', 任何网页都能读到你的抖音 cookie 和邮箱密码。
"""

import errno
import hmac
import json
import os
import secrets
import socket
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from loguru import logger

from webui import api
from webui import config_io as C
from webui import schema as S

MAX_BODY = 1024 * 1024          # 1 MiB, cookie 再长也够
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
_STATIC = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/index.html': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/app.css': ('app.css', 'text/css; charset=utf-8'),
}
LOOPBACK = {'127.0.0.1', '::1', 'localhost', '::ffff:127.0.0.1'}


@dataclass
class Ctx:
    config_file: str = ''
    url_config_file: str = ''
    backup_dir: str = ''
    default_path: str = ''
    text_encoding: str = 'utf-8-sig'
    url_file_lock: object = None
    backup_file: object = None
    get_status: object = None
    shutdown: object = None
    version: str = ''
    host: str = '127.0.0.1'
    port: int = 8787
    token: str = ''
    lan_mode: bool = False
    lan_lock_script: bool = True
    allowed_hosts: set = field(default_factory=set)
    lan_urls: list = field(default_factory=list)


@dataclass
class Req:
    method: str
    path: str
    query: dict
    json: object
    is_lan: bool


class _Server(ThreadingHTTPServer):
    daemon_threads = True          # 进程退出时不等待请求线程
    allow_reuse_address = True     # 避免 TIME_WAIT 导致重启失败


def _make_handler(ctx: Ctx):

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        server_version = 'DLRWebUI'
        sys_version = ''
        timeout = 30

        # 默认实现会往 stderr 打访问日志, 而 main.py 的 display_info() 每 5 秒
        # os.system('clear') 清一次屏, 两者会打架刷屏。改成只进日志文件。
        def log_message(self, fmt, *args):
            logger.debug('webui %s - %s' % (self.address_string(), fmt % args))

        def log_error(self, fmt, *args):
            logger.debug('webui %s - %s' % (self.address_string(), fmt % args))

        # -------------------------------------------------- 入口
        def do_GET(self):
            self._handle('GET')

        def do_POST(self):
            self._handle('POST')

        def do_HEAD(self):
            self._handle('GET', head_only=True)

        def _handle(self, method, head_only=False):
            try:
                self._dispatch(method, head_only)
            except Exception:
                logger.exception('webui 请求处理异常')
                try:
                    self._json(500, {'error': '服务器内部错误'})
                except Exception:
                    pass

        def _dispatch(self, method, head_only=False):
            parsed = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(parsed.path)
            query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}

            if not self._check_host():
                return self._json(421, {'error': 'Host 头不被接受'})

            peer = (self.client_address[0] or '').strip('[]')
            is_lan = peer not in LOOPBACK

            if not self._check_token(query, is_lan, path):
                return

            if method == 'POST' and path.startswith('/api/'):
                if self.headers.get('X-DLR-CSRF') != '1':
                    return self._json(403, {'error': '缺少 X-DLR-CSRF 头'})
                origin = self.headers.get('Origin')
                if origin and not self._same_origin(origin):
                    return self._json(403, {'error': '跨站请求被拒绝'})

            if method == 'GET' and path in _STATIC:
                return self._static(path, head_only)

            handler = api.ROUTES.get((method, path))
            if not handler:
                return self._json(404, {'error': '没有这个接口'})

            body = None
            if method == 'POST':
                try:
                    body = self._read_json()
                except ValueError as e:
                    return self._json(400, {'error': str(e)})

            req = Req(method, path, query, body, is_lan)
            try:
                status, payload = handler(ctx, req)
            except api.ApiError as e:
                return self._json(e.status, {'error': e.message, 'detail': e.detail})
            return self._json(status, payload)

        # -------------------------------------------------- 安全
        def _check_host(self) -> bool:
            raw = (self.headers.get('Host') or '').strip()
            if not raw:
                return True                      # HTTP/1.0 客户端
            host = raw.rsplit(':', 1)[0] if raw.count(':') == 1 else raw
            if raw.startswith('['):              # IPv6 字面量
                host = raw.split(']')[0].lstrip('[')
            return host.strip('[]').casefold() in ctx.allowed_hosts

        def _same_origin(self, origin: str) -> bool:
            try:
                h = urllib.parse.urlsplit(origin).hostname or ''
            except ValueError:
                return False
            return h.casefold() in ctx.allowed_hosts

        def _check_token(self, query, is_lan, path) -> bool:
            if not ctx.token:
                return True
            supplied = (self.headers.get('X-DLR-Token')
                        or query.get('token')
                        or self._cookie('dlr_token') or '')
            if hmac.compare_digest(supplied, ctx.token):
                # 首次带 ?token= 访问页面时种 Cookie, 之后手机上就不用再带了
                if query.get('token') and path in _STATIC:
                    self.send_response(302)
                    self.send_header('Location', '/')
                    self.send_header('Set-Cookie',
                                     'dlr_token=%s; Path=/; HttpOnly; SameSite=Strict; '
                                     'Max-Age=2592000' % ctx.token)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return False
                return True
            time.sleep(0.5)                      # 粗暴但有效地压制暴力破解
            self._json(401, {'error': '访问令牌不正确'})
            return False

        def _cookie(self, name):
            raw = self.headers.get('Cookie') or ''
            for part in raw.split(';'):
                k, _, v = part.strip().partition('=')
                if k == name:
                    return v
            return None

        # -------------------------------------------------- IO
        def _read_json(self):
            try:
                length = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                raise ValueError('Content-Length 不合法')
            if length > MAX_BODY:
                raise ValueError('请求体过大')
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ValueError('请求体不是合法 JSON')

        def _static(self, path, head_only=False):
            name, ctype = _STATIC[path]
            full = os.path.join(STATIC_DIR, name)
            try:
                with open(full, 'rb') as f:
                    data = f.read()
            except OSError:
                return self._json(404, {'error': '页面文件缺失'})
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            # script-src 保持严格('self', 无 unsafe-inline), 页面里没有任何内联脚本。
            # style-src 放开 inline 是为了 JS 直接设 el.style.*; 因为我们全程用
            # createElement + textContent 构造 DOM, 从不拼 HTML 字符串, 所以没有
            # 注入面。frame-ancestors none 顺带挡掉点击劫持。
            self.send_header('Content-Security-Policy',
                             "default-src 'none'; script-src 'self'; "
                             "style-src 'self' 'unsafe-inline'; "
                             "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
                             "form-action 'none'; frame-ancestors 'none'")
            self.end_headers()
            if not head_only:
                self.wfile.write(data)

        def _json(self, status, obj):
            data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

    return Handler


# ------------------------------------------------------------------ 启动

def _local_ips() -> list:
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('223.5.5.5', 80))       # 不发包, 只为取出口网卡地址
            ips.append(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith('127.'):
                ips.append(ip)
    except OSError:
        pass
    return ips


def _env_or(cfg_value, env_name, cast=str):
    raw = os.environ.get(env_name)
    if raw is None or raw == '':
        return cfg_value
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return cfg_value


def _truthy(v) -> bool:
    return str(v).strip().casefold() in ('是', 'true', '1', 'yes', 'on')


def _bind(host: str, port: int, handler):
    last = None
    for p in range(port, port + 10):
        try:
            return _Server((host, p), handler)
        except OSError as e:
            last = e
            if e.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
    logger.error(f'WebUI 端口 {port}~{port + 9} 都被占用, 界面未启动 (录制不受影响): {last}')
    return None


def start_webui(config_file, url_config_file, backup_dir, default_path,
                text_encoding='utf-8-sig', url_file_lock=None, backup_file=None,
                get_status=None, shutdown=None, version=''):
    """在后台线程里起 HTTP 服务。任何异常都不应影响录制, 调用方已包了 try。"""

    # 先把自己的配置项补进 config.ini —— 必须走我们自己的写入器。
    # 若指望 main.py 的 read_config_value 去补, 它会 configparser.write() 整体
    # 回写, 一下子就把用户配置里的注释全抹掉、key 全部小写化。
    try:
        C.ensure_defaults(config_file, S.WEBUI_DEFAULTS)
    except Exception as e:
        logger.warning(f'WebUI 写入默认配置失败: {e}')

    values = C.read_all(config_file)

    def cv(key, default=''):
        return values.get((S.SECTION_WEBUI.casefold(), key.casefold()),
                          {}).get('value', default)

    enabled = _truthy(_env_or(cv('是否启用网页界面(是/否)', '是'), 'DLR_WEBUI_ENABLE'))
    if not enabled:
        logger.info('WebUI 已在配置中关闭')
        return None

    host = str(_env_or(cv('网页界面监听地址', '127.0.0.1'), 'DLR_WEBUI_HOST')).strip() or '127.0.0.1'
    try:
        port = int(_env_or(cv('网页界面端口', '8787'), 'DLR_WEBUI_PORT', int))
    except (TypeError, ValueError):
        port = 8787
    token = str(_env_or(cv('网页界面访问令牌', ''), 'DLR_WEBUI_TOKEN')).strip()
    lan_mode = host not in ('127.0.0.1', 'localhost', '::1')
    lan_lock_script = _truthy(cv('LAN模式下禁止修改自定义脚本(是/否)', '是'))

    # 对外监听时强制要求令牌 —— 这个界面能读写全部 cookie 与账号密码
    if lan_mode and not token:
        token = secrets.token_urlsafe(24)
        try:
            C.apply_changes(config_file,
                            [(S.SECTION_WEBUI, '网页界面访问令牌', token)])
            logger.warning('WebUI 监听地址不是本机, 已自动生成访问令牌并写入配置')
        except Exception as e:
            logger.error(f'WebUI 令牌写入失败, 为安全起见退回仅本机监听: {e}')
            host, lan_mode, token = '127.0.0.1', False, ''

    ips = _local_ips() if lan_mode else []
    allowed = {'127.0.0.1', 'localhost', '::1'}
    allowed.add(host.casefold())
    allowed.update(ip.casefold() for ip in ips)

    ctx = Ctx(config_file=config_file, url_config_file=url_config_file,
              backup_dir=backup_dir, default_path=default_path,
              text_encoding=text_encoding, url_file_lock=url_file_lock or threading.Lock(),
              backup_file=backup_file, get_status=get_status or (lambda: {}),
              shutdown=shutdown,
              version=version, host=host, port=port, token=token,
              lan_mode=lan_mode, lan_lock_script=lan_lock_script,
              allowed_hosts=allowed)

    httpd = _bind(host, port, _make_handler(ctx))
    if httpd is None:
        return None
    ctx.port = httpd.server_address[1]
    ctx.lan_urls = [f'http://{ip}:{ctx.port}/' + (f'?token={token}' if token else '')
                    for ip in ips]

    t = threading.Thread(target=httpd.serve_forever, name='webui', daemon=True)
    t.start()

    local_url = f'http://127.0.0.1:{ctx.port}/'
    print(f'网页管理界面: {local_url}')
    if lan_mode:
        print('  局域网访问已开启 —— 本界面可读写全部 Cookie 与账号密码, 且为明文 HTTP 传输')
        for u in ctx.lan_urls:
            print(f'  手机/其他设备: {u}')
    logger.info(f'WebUI 已启动于 {host}:{ctx.port} (lan={lan_mode}, token={"有" if token else "无"})')

    if _truthy(cv('网页界面自动打开浏览器(是/否)', '否')):
        try:
            import webbrowser
            threading.Timer(1.0, webbrowser.open, args=(local_url,)).start()
        except Exception:
            pass

    return ctx


# 供 main.py 可选地替换掉 src/utils.update_config, 修掉上游的 %% 转义 bug
start_webui.safe_update_config = C.safe_update_config
