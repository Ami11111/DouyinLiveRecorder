# -*- coding: utf-8 -*-
"""配置项描述表 —— 前后端共用的单一事实来源。

config.ini 的 key 名里塞满了奇怪字符(`原画|超清|高清|标清|流畅`、
`language(zh_cn/en)`、`视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频`),
绝不能直接拿 key 当界面标签, 所以这里为每一项单独给出 label。

布尔值在文件里是中文 是/否 (main.py:1787 options = {"是": True, "否": False})。
"""

from dataclasses import dataclass, field as _f

SECTION_RECORD = '录制设置'
SECTION_PUSH = '推送配置'
SECTION_COOKIE = 'Cookie'
SECTION_AUTH = 'Authorization'
SECTION_ACCOUNT = '账号密码'
SECTION_WEBUI = '网页界面'

BOOL_TRUE, BOOL_FALSE = '是', '否'


@dataclass(frozen=True)
class Field:
    section: str
    key: str                       # config.ini 里的原名, 匹配时一律 casefold
    label: str                     # 界面显示用
    type: str                      # bool|select|multiselect|int|float|text|password|path|csv|textarea
    group: str = '常规'
    default: str = ''
    choices: tuple = ()            # ((value, label), ...)
    minv: float = None
    maxv: float = None
    secret: bool = False           # 列表接口里遮蔽, 需主动"显示"才拉明文
    help: str = ''
    warn: str = ''                 # 橙色提示
    placeholder: str = ''
    depends: tuple = ()            # (key, expected) expected 为 True 或子串
    restart: bool = False          # 保存后需要重启程序
    next_only: bool = False        # 只影响"下一次开始录制", 不打断当前录制

    def to_json(self) -> dict:
        d = {'section': self.section, 'key': self.key, 'label': self.label,
             'type': self.type, 'group': self.group, 'default': self.default,
             'choices': [list(c) for c in self.choices], 'secret': self.secret,
             'help': self.help, 'warn': self.warn, 'placeholder': self.placeholder,
             'depends': list(self.depends), 'restart': self.restart,
             'next_only': self.next_only}
        if self.minv is not None:
            d['minv'] = self.minv
        if self.maxv is not None:
            d['maxv'] = self.maxv
        return d


_YES_NO = ((BOOL_TRUE, '是'), (BOOL_FALSE, '否'))

# ------------------------------------------------------------------ 录制设置

RECORD_FIELDS = [
    Field(SECTION_RECORD, 'language(zh_cn/en)', '程序语言', 'select', group='常规',
          default='zh_cn', choices=(('zh_cn', '简体中文'), ('en', 'English')),
          restart=True, help='只影响终端输出, 不影响本界面'),
    Field(SECTION_RECORD, '是否跳过代理检测(是/否)', '跳过启动时的代理检测', 'bool',
          group='常规', default='否', restart=True,
          help='启动时会访问一次 google.com 判断能否直连, 约需 15 秒。跳过可让程序秒启动'),
    Field(SECTION_RECORD, '是否显示循环秒数', '终端显示循环倒计时', 'bool', group='常规', default='否'),
    Field(SECTION_RECORD, '是否显示直播源地址', '终端显示直播源地址', 'bool', group='常规', default='否'),

    Field(SECTION_RECORD, '直播保存路径(不填则默认)', '直播保存路径', 'path', group='存储',
          placeholder='留空则保存到 程序目录/downloads', next_only=True,
          help='正在录制的文件不会搬家, 下次开录时才用新路径'),
    Field(SECTION_RECORD, '保存文件夹是否以作者区分', '按主播分文件夹', 'bool', group='存储',
          default='是', next_only=True),
    Field(SECTION_RECORD, '保存文件夹是否以时间区分', '按日期分文件夹', 'bool', group='存储',
          default='否', next_only=True),
    Field(SECTION_RECORD, '保存文件夹是否以标题区分', '按直播标题分文件夹', 'bool', group='存储',
          default='否', next_only=True),
    Field(SECTION_RECORD, '保存文件名是否包含标题', '文件名包含直播标题', 'bool', group='存储',
          default='否', next_only=True),
    Field(SECTION_RECORD, '是否去除名称中的表情符号', '去除名称里的 Emoji', 'bool', group='存储',
          default='是', next_only=True, help='有些文件系统对 Emoji 支持不好, 建议开启'),
    Field(SECTION_RECORD, '录制空间剩余阈值(gb)', '磁盘剩余告警 (GB)', 'float', group='存储',
          default='1.0', minv=0, maxv=10000,
          warn='磁盘剩余低于此值、且当前没有任何录制任务时, 程序会直接退出'),

    Field(SECTION_RECORD, '视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频', '视频保存格式', 'select',
          group='画质', default='ts', next_only=True,
          choices=(('ts', 'TS  (最稳, 推荐)'), ('mkv', 'MKV'), ('flv', 'FLV'), ('mp4', 'MP4'),
                   ('mp3音频', 'MP3  纯音频'), ('m4a音频', 'M4A  纯音频')),
          warn='部分平台运行期会强制改写: 抖音/TikTok 的 H.265 FLV 源 → TS; '
               'Shopee/花椒 → FLV; 猫耳FM/Look → 纯音频。概览页显示的是真实生效值'),
    Field(SECTION_RECORD, '原画|超清|高清|标清|流畅', '默认录制清晰度', 'select', group='画质',
          default='原画', next_only=True,
          choices=(('原画', '原画'), ('蓝光', '蓝光'), ('超清', '超清'),
                   ('高清', '高清'), ('标清', '标清'), ('流畅', '流畅')),
          help='在"直播间"里给单个直播间单独指定的清晰度优先级更高'),

    Field(SECTION_RECORD, '分段录制是否开启', '开启分段录制', 'bool', group='分段',
          default='否', next_only=True,
          help='把一场直播切成多个文件, 避免单个文件过大。与"生成时间字幕文件"互斥'),
    Field(SECTION_RECORD, '视频分段时间(秒)', '每段时长 (秒)', 'int', group='分段',
          default='1800', minv=60, maxv=86400, next_only=True,
          depends=('分段录制是否开启', True),
          warn='程序本身对这一项没有任何校验, 填错会让 ffmpeg 直接启动失败。'
               '这里的 60~86400 范围限制由本界面强制'),

    Field(SECTION_RECORD, '是否使用代理ip(是/否)', '使用代理', 'bool', group='网络', default='是'),
    Field(SECTION_RECORD, '代理地址', '代理地址', 'text', group='网络',
          placeholder='http://127.0.0.1:7890', depends=('是否使用代理ip(是/否)', True),
          help='留空则使用系统代理'),
    Field(SECTION_RECORD, '同一时间访问网络的线程数', '并发请求线程数', 'int', group='网络',
          default='3', minv=1, maxv=32,
          warn='运行中会被程序按错误率每 5 秒动态调节, 概览页的"当前生效值"可能与这里不同'),
    Field(SECTION_RECORD, '循环时间(秒)', '开播检测间隔 (秒)', 'int', group='网络',
          default='120', minv=10, maxv=3600,
          help='每隔多久检查一次直播间是否开播。调小能更快发现开播, 但请求更频繁'),
    Field(SECTION_RECORD, '排队读取网址时间(秒)', '逐个读取地址的间隔 (秒)', 'int', group='网络',
          default='0', minv=0, maxv=600, help='0 表示不排队'),
    Field(SECTION_RECORD, '是否强制启用https录制', '强制使用 HTTPS 录制', 'bool',
          group='网络', default='否', next_only=True),
    Field(SECTION_RECORD, '使用代理录制的平台(逗号分隔)', '走代理的平台', 'csv', group='网络',
          help='这些平台的录制会走代理。逗号分隔, 中英文逗号都接受'),
    Field(SECTION_RECORD, '额外使用代理录制的平台(逗号分隔)', '额外走代理的平台', 'csv', group='网络'),

    Field(SECTION_RECORD, '录制完成后自动转为mp4格式', '录完自动转 MP4', 'bool', group='后处理',
          default='否', help='只对 TS 格式生效'),
    Field(SECTION_RECORD, 'mp4格式重新编码为h264', '转 MP4 时重新编码为 H.264', 'bool',
          group='后处理', default='否', depends=('录制完成后自动转为mp4格式', True),
          warn='重新编码非常吃 CPU 且耗时很久。不开启时只做封装转换(秒级完成)'),
    Field(SECTION_RECORD, '追加格式后删除原文件', '转换成功后删除原文件', 'bool', group='后处理',
          default='否', depends=('录制完成后自动转为mp4格式', True)),
    Field(SECTION_RECORD, '生成时间字幕文件', '生成时间字幕文件', 'bool', group='后处理',
          default='否', help='与分段录制互斥, 开启分段时这一项不生效'),

    Field(SECTION_RECORD, '是否录制完成后执行自定义脚本', '录完执行自定义脚本', 'bool',
          group='脚本', default='否',
          warn='这是任意命令执行入口。开启局域网访问时强烈建议保持关闭'),
    Field(SECTION_RECORD, '自定义脚本执行命令', '脚本命令', 'textarea', group='脚本',
          depends=('是否录制完成后执行自定义脚本', True),
          placeholder='例: /usr/local/bin/notify.sh',
          warn='程序会把主播名、文件路径、保存格式等作为参数追加到命令后面'),
]

# ------------------------------------------------------------------ 推送配置

PUSH_CHANNELS = (('微信', '微信 (息知)'), ('钉钉', '钉钉'), ('邮箱', '邮箱'),
                 ('tg', 'Telegram'), ('bark', 'Bark'), ('ntfy', 'ntfy'),
                 ('pushplus', 'PushPlus'))

PUSH_FIELDS = [
    Field(SECTION_PUSH, '直播状态推送渠道', '启用的推送渠道', 'multiselect', group='总开关',
          choices=PUSH_CHANNELS, help='可多选, 留空表示不推送'),
    Field(SECTION_PUSH, '开播推送开启(是/否)', '开播时推送', 'bool', group='总开关', default='是'),
    Field(SECTION_PUSH, '关播推送开启(是/否)', '关播时推送', 'bool', group='总开关', default='否'),
    Field(SECTION_PUSH, '只推送通知不录制(是/否)', '只推送通知, 不录制', 'bool', group='总开关',
          default='否', warn='开启后所有直播间都只做开播提醒, 不会录制任何内容'),
    Field(SECTION_PUSH, '直播推送检测频率(秒)', '推送检测间隔 (秒)', 'int', group='总开关',
          default='1800', minv=10, maxv=86400),
    Field(SECTION_PUSH, '自定义推送标题', '推送标题', 'text', group='总开关'),
    Field(SECTION_PUSH, '自定义开播推送内容', '开播推送内容', 'text', group='总开关'),
    Field(SECTION_PUSH, '自定义关播推送内容', '关播推送内容', 'text', group='总开关'),

    Field(SECTION_PUSH, '微信推送接口链接', '息知推送链接', 'password', group='微信',
          secret=True, depends=('直播状态推送渠道', '微信')),

    Field(SECTION_PUSH, '钉钉推送接口链接', '钉钉机器人 Webhook', 'password', group='钉钉',
          secret=True, depends=('直播状态推送渠道', '钉钉')),
    Field(SECTION_PUSH, '钉钉通知@对象(填手机号)', '@ 指定手机号', 'text', group='钉钉',
          depends=('直播状态推送渠道', '钉钉')),
    Field(SECTION_PUSH, '钉钉通知@全体(是/否)', '@ 全体成员', 'bool', group='钉钉',
          default='否', depends=('直播状态推送渠道', '钉钉')),

    Field(SECTION_PUSH, 'tgapi令牌', 'Telegram Bot Token', 'password', group='Telegram',
          secret=True, depends=('直播状态推送渠道', 'tg')),
    Field(SECTION_PUSH, 'tg聊天id(个人或者群组id)', 'Telegram Chat ID', 'text',
          group='Telegram', depends=('直播状态推送渠道', 'tg')),

    Field(SECTION_PUSH, 'bark推送接口链接', 'Bark 推送链接', 'password', group='Bark',
          secret=True, depends=('直播状态推送渠道', 'bark')),
    Field(SECTION_PUSH, 'bark推送中断级别', 'Bark 中断级别', 'select', group='Bark',
          default='active', depends=('直播状态推送渠道', 'bark'),
          choices=(('active', 'active  立即亮屏'), ('timeSensitive', 'timeSensitive  时效性'),
                   ('passive', 'passive  静默'), ('critical', 'critical  重要警告'))),
    Field(SECTION_PUSH, 'bark推送铃声', 'Bark 铃声', 'text', group='Bark',
          placeholder='bell', depends=('直播状态推送渠道', 'bark')),

    Field(SECTION_PUSH, 'ntfy推送地址', 'ntfy 推送地址', 'text', group='ntfy',
          placeholder='https://ntfy.sh/your-topic', depends=('直播状态推送渠道', 'ntfy')),
    Field(SECTION_PUSH, 'ntfy推送标签', 'ntfy 标签', 'text', group='ntfy',
          depends=('直播状态推送渠道', 'ntfy')),
    Field(SECTION_PUSH, 'ntfy推送邮箱', 'ntfy 转发邮箱', 'text', group='ntfy',
          depends=('直播状态推送渠道', 'ntfy')),

    Field(SECTION_PUSH, 'pushplus推送token', 'PushPlus Token', 'password', group='PushPlus',
          secret=True, depends=('直播状态推送渠道', 'pushplus')),

    Field(SECTION_PUSH, 'smtp邮件服务器', 'SMTP 服务器', 'text', group='邮箱',
          placeholder='smtp.qq.com', depends=('直播状态推送渠道', '邮箱')),
    Field(SECTION_PUSH, 'SMTP邮件服务器端口', 'SMTP 端口', 'int', group='邮箱',
          minv=1, maxv=65535, depends=('直播状态推送渠道', '邮箱')),
    Field(SECTION_PUSH, '是否使用SMTP服务SSL加密(是/否)', '使用 SSL 加密', 'bool', group='邮箱',
          default='是', depends=('直播状态推送渠道', '邮箱'), help='留空时按"是"处理'),
    Field(SECTION_PUSH, '邮箱登录账号', '邮箱登录账号', 'text', group='邮箱',
          depends=('直播状态推送渠道', '邮箱')),
    Field(SECTION_PUSH, '发件人密码(授权码)', '发件人密码 / 授权码', 'password', group='邮箱',
          secret=True, depends=('直播状态推送渠道', '邮箱')),
    Field(SECTION_PUSH, '发件人邮箱', '发件人邮箱', 'text', group='邮箱',
          depends=('直播状态推送渠道', '邮箱')),
    Field(SECTION_PUSH, '发件人显示昵称', '发件人昵称', 'text', group='邮箱',
          depends=('直播状态推送渠道', '邮箱')),
    Field(SECTION_PUSH, '收件人邮箱', '收件人邮箱', 'text', group='邮箱',
          depends=('直播状态推送渠道', '邮箱')),
]

# ------------------------------------------------------------------ 账号密码 / Authorization

ACCOUNT_FIELDS = [
    Field(SECTION_ACCOUNT, 'sooplive账号', 'SOOP 账号', 'text', group='SOOP'),
    Field(SECTION_ACCOUNT, 'sooplive密码', 'SOOP 密码', 'password', group='SOOP', secret=True),
    Field(SECTION_ACCOUNT, 'flextv账号', 'FlexTV 账号', 'text', group='FlexTV'),
    Field(SECTION_ACCOUNT, 'flextv密码', 'FlexTV 密码', 'password', group='FlexTV', secret=True),
    Field(SECTION_ACCOUNT, 'popkontv账号', 'PopkonTV 账号', 'text', group='PopkonTV'),
    Field(SECTION_ACCOUNT, 'popkontv密码', 'PopkonTV 密码', 'password', group='PopkonTV', secret=True),
    Field(SECTION_ACCOUNT, 'partner_code', 'PopkonTV Partner Code', 'text', group='PopkonTV',
          placeholder='P-00001'),
    Field(SECTION_ACCOUNT, 'twitcasting账号类型', 'TwitCasting 登录方式', 'select',
          group='TwitCasting', default='normal',
          choices=(('normal', '普通账号'), ('twitter', 'Twitter 账号'))),
    Field(SECTION_ACCOUNT, 'twitcasting账号', 'TwitCasting 账号', 'text', group='TwitCasting'),
    Field(SECTION_ACCOUNT, 'twitcasting密码', 'TwitCasting 密码', 'password',
          group='TwitCasting', secret=True),
    Field(SECTION_AUTH, 'popkontv_token', 'PopkonTV Token', 'password', group='令牌',
          secret=True, warn='登录成功后程序会自动覆写这一项'),
]

# ------------------------------------------------------------------ Cookie

COOKIE_LABEL = {
    '抖音cookie': '抖音', 'b站cookie': 'B 站', '快手cookie': '快手', '虎牙cookie': '虎牙',
    '斗鱼cookie': '斗鱼', '小红书cookie': '小红书', 'yy_cookie': 'YY',
    'tiktok_cookie': 'TikTok', 'youtube_cookie': 'YouTube', 'twitch_cookie': 'Twitch',
    'bigo_cookie': 'Bigo', 'blued_cookie': 'Blued', 'sooplive_cookie': 'SOOP',
    'netease_cookie': '网易 CC', '千度热播_cookie': '千度热播', 'pandatv_cookie': 'PandaTV',
    '猫耳fm_cookie': '猫耳 FM', 'winktv_cookie': 'WinkTV', 'flextv_cookie': 'FlexTV',
    'look_cookie': 'Look 直播', 'twitcasting_cookie': 'TwitCasting', 'baidu_cookie': '百度',
    'weibo_cookie': '微博', 'kugou_cookie': '酷狗', 'liveme_cookie': 'LiveMe',
    'huajiao_cookie': '花椒', 'liuxing_cookie': '流星', 'showroom_cookie': 'SHOWROOM',
    'acfun_cookie': 'AcFun', 'changliao_cookie': '畅聊', 'yinbo_cookie': '音播',
    'yingke_cookie': '映客', 'zhihu_cookie': '知乎', 'chzzk_cookie': 'CHZZK',
    'haixiu_cookie': '嗨秀', 'vvxqiu_cookie': 'VV 星球', '17live_cookie': '17LIVE',
    'langlive_cookie': 'LangLive', 'pplive_cookie': 'PP 直播', '6room_cookie': '六间房',
    'lehaitv_cookie': '乐嗨', 'huamao_cookie': '花猫', 'shopee_cookie': 'Shopee',
    'taobao_cookie': '淘宝', 'jd_cookie': '京东', 'faceit_cookie': 'FACEIT',
    'migu_cookie': '咪咕', 'lianjie_cookie': '连接直播', 'laixiu_cookie': '来秀',
    'picarto_cookie': 'Picarto',
}

COOKIE_TOP = ('抖音cookie', 'b站cookie', '快手cookie', '虎牙cookie', '斗鱼cookie', '小红书cookie')


def cookie_fields(keys_in_file) -> list:
    """按文件里实际存在的 key 生成 Cookie 字段, 未知 key 也照样生成(不隐藏任何东西)。"""
    top_cf = {k.casefold() for k in COOKIE_TOP}
    ordered = ([k for k in COOKIE_TOP if k.casefold() in {x.casefold() for x in keys_in_file}]
               + [k for k in keys_in_file if k.casefold() not in top_cf])
    out = []
    for k in ordered:
        label = COOKIE_LABEL.get(k.casefold(), k)
        out.append(Field(SECTION_COOKIE, k, label, 'password',
                         group='常用平台' if k.casefold() in top_cf else '其他平台',
                         secret=True,
                         placeholder='粘贴浏览器 F12 里的完整 Cookie',
                         help='录制抖音必填' if k.casefold() == '抖音cookie' else ''))
    return out


# ------------------------------------------------------------------ 网页界面(本界面自身)

WEBUI_FIELDS = [
    Field(SECTION_WEBUI, '是否启用网页界面(是/否)', '启用网页界面', 'bool', group='服务',
          default='是', restart=True),
    Field(SECTION_WEBUI, '网页界面端口', '端口', 'int', group='服务', default='8787',
          minv=1, maxv=65535, restart=True, help='被占用时会自动向后顺延最多 9 个'),
    Field(SECTION_WEBUI, '网页界面监听地址', '监听地址', 'select', group='服务',
          default='127.0.0.1', restart=True,
          choices=(('127.0.0.1', '127.0.0.1  仅本机 (推荐)'),
                   ('0.0.0.0', '0.0.0.0  局域网可访问')),
          warn='改成 0.0.0.0 后同一 Wi-Fi 下的其他设备都能访问本界面。'
               '本界面可以读写你所有平台的 Cookie 和账号密码, 且是明文 HTTP 传输。'
               '务必先读下面的风险说明'),
    Field(SECTION_WEBUI, '网页界面访问令牌', '访问令牌', 'password', group='服务',
          secret=True, restart=True,
          help='留空且仅本机监听时不鉴权; 改为局域网监听时会自动生成一个'),
    Field(SECTION_WEBUI, '网页界面自动打开浏览器(是/否)', '启动时自动打开浏览器', 'bool',
          group='服务', default='否', restart=True),
    Field(SECTION_WEBUI, 'LAN模式下禁止修改自定义脚本(是/否)', '局域网访问时锁定自定义脚本', 'bool',
          group='服务', default='是',
          help='开启后, 通过局域网访问时"自定义脚本"相关配置为只读。'
               '自定义脚本等同于任意命令执行, 强烈建议保持开启'),
]

# ensure_defaults 用: (section, key, value, comment)
WEBUI_DEFAULTS = [
    (SECTION_WEBUI, '是否启用网页界面(是/否)', '是',
     '# ---- 本地网页管理界面 (fork 新增, 上游没有这一段) ----'),
    (SECTION_WEBUI, '网页界面端口', '8787', '# 被占用时自动向后顺延最多 9 个'),
    (SECTION_WEBUI, '网页界面监听地址', '127.0.0.1',
     '# 127.0.0.1 = 仅本机(推荐); 0.0.0.0 = 局域网可访问, 此时必须配合访问令牌'),
    (SECTION_WEBUI, '网页界面访问令牌', '',
     '# 留空 = 不鉴权(仅限本机监听); 改为局域网监听时会自动生成'),
    (SECTION_WEBUI, '网页界面自动打开浏览器(是/否)', '否', ''),
    (SECTION_WEBUI, 'LAN模式下禁止修改自定义脚本(是/否)', '是',
     '# 自定义脚本等同于任意命令执行, 局域网访问时建议锁定'),
]

# 局域网访问时强制只读的字段(自定义脚本 = 任意命令执行)
LAN_READONLY_KEYS = {
    (SECTION_RECORD.casefold(), '是否录制完成后执行自定义脚本'.casefold()),
    (SECTION_RECORD.casefold(), '自定义脚本执行命令'.casefold()),
}

TABS = [
    {'id': 'record', 'label': '录制设置', 'sections': [SECTION_RECORD]},
    {'id': 'push', 'label': '推送', 'sections': [SECTION_PUSH]},
    {'id': 'creds', 'label': '凭据', 'sections': [SECTION_COOKIE, SECTION_ACCOUNT, SECTION_AUTH]},
    {'id': 'webui', 'label': '界面设置', 'sections': [SECTION_WEBUI]},
]


def all_fields(cookie_keys=()) -> list:
    return (RECORD_FIELDS + PUSH_FIELDS + cookie_fields(cookie_keys)
            + ACCOUNT_FIELDS + WEBUI_FIELDS)


def index_by_key(fields) -> dict:
    return {(f.section.casefold(), f.key.casefold()): f for f in fields}


# ------------------------------------------------------------------ 校验

class ValidationError(Exception):
    pass


def to_file_value(f: Field, value) -> str:
    """把界面传来的 JSON 值转成写进 ini 的字符串。不合法则抛 ValidationError。"""
    t = f.type

    if t == 'bool':
        if isinstance(value, str):
            value = value.strip() in (BOOL_TRUE, 'true', 'True', '1')
        if not isinstance(value, bool):
            raise ValidationError(f'{f.label}: 需要一个开关值')
        return BOOL_TRUE if value else BOOL_FALSE

    if t == 'select':
        v = str(value).strip()
        allowed = [c[0] for c in f.choices]
        if v and v not in allowed:
            raise ValidationError(f'{f.label}: 只能是 {"、".join(allowed)} 之一')
        return v

    if t == 'multiselect':
        items = value if isinstance(value, list) else \
            [x.strip() for x in str(value).replace('，', ',').split(',')]
        items = [x for x in (str(i).strip() for i in items) if x]
        allowed = {c[0].casefold() for c in f.choices}
        bad = [x for x in items if x.casefold() not in allowed]
        if bad:
            raise ValidationError(f'{f.label}: 不认识的选项 {"、".join(bad)}')
        return ','.join(items)

    if t in ('int', 'float'):
        v = str(value).strip()
        if v == '':
            return ''
        try:
            num = int(v) if t == 'int' else float(v)
        except ValueError:
            raise ValidationError(f'{f.label}: 需要填一个{"整数" if t == "int" else "数字"}')
        if f.minv is not None and num < f.minv:
            raise ValidationError(f'{f.label}: 不能小于 {_fmt(f.minv)}')
        if f.maxv is not None and num > f.maxv:
            raise ValidationError(f'{f.label}: 不能大于 {_fmt(f.maxv)}')
        return str(num)

    if t == 'csv':
        items = value if isinstance(value, list) else \
            [x.strip() for x in str(value).replace('，', ',').split(',')]
        return ', '.join(x for x in (str(i).strip() for i in items) if x)

    v = str(value)
    if '\n' in v or '\r' in v:
        if t != 'textarea':
            raise ValidationError(f'{f.label}: 不能包含换行')
        v = v.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
    return v.strip()


def _fmt(n) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


def from_file_value(f: Field, raw: str):
    """把 ini 里的字符串转成界面用的 JSON 值。"""
    raw = '' if raw is None else raw
    if f.type == 'bool':
        if raw.strip() == '':
            return f.default == BOOL_TRUE
        return raw.strip() == BOOL_TRUE
    if f.type == 'multiselect':
        return [x.strip() for x in raw.replace('，', ',').split(',') if x.strip()]
    if f.type == 'csv':
        return [x.strip() for x in raw.replace('，', ',').split(',') if x.strip()]
    return raw


def mask(raw: str) -> dict:
    """secret 字段的遮蔽表示: 只给长度和前若干字符, 不给明文。"""
    raw = raw or ''
    if not raw:
        return {'masked': True, 'empty': True, 'hint': '', 'length': 0}
    head = raw[:12]
    return {'masked': True, 'empty': False, 'length': len(raw),
            'hint': f'{head}…（共 {len(raw)} 字符）' if len(raw) > 12 else raw}
