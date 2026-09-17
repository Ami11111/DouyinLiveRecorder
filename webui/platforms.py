# -*- coding: utf-8 -*-
"""平台域名白名单 —— 从 main.py 拷贝的纯数据, 只用于界面上的软提示。

来源: main.py 里的 platform_host / overseas_platform_host 两个列表
(本文件生成时对应 main.py:2036-2104)。

用途: 新增直播间时, 如果域名不在这份名单里就给一个"程序可能会自动把这行
注释掉"的警告 —— 只警告不拦截, 因为上游随时会加新平台。
上游更新后如果加了新平台, 这里需要人工对齐, 否则只是提示不准, 不影响功能。
"""

PLATFORM_HOST = (
    'live.douyin.com',
    'v.douyin.com',
    'www.douyin.com',
    'live.kuaishou.com',
    'www.huya.com',
    'www.douyu.com',
    'www.yy.com',
    'live.bilibili.com',
    'www.redelight.cn',
    'www.xiaohongshu.com',
    'xhslink.com',
    'www.bigo.tv',
    'slink.bigovideo.tv',
    'app.blued.cn',
    'cc.163.com',
    'qiandurebo.com',
    'fm.missevan.com',
    'look.163.com',
    'twitcasting.tv',
    'live.baidu.com',
    'weibo.com',
    'fanxing.kugou.com',
    'fanxing2.kugou.com',
    'mfanxing.kugou.com',
    'www.huajiao.com',
    'www.7u66.com',
    'wap.7u66.com',
    'live.acfun.cn',
    'm.acfun.cn',
    'live.tlclw.com',
    'wap.tlclw.com',
    'live.ybw1666.com',
    'wap.ybw1666.com',
    'www.inke.cn',
    'www.zhihu.com',
    'www.haixiutv.com',
    'www.lang.live',
    'www.lehaitv.com',
    'h.catshow168.com',
    'e.tb.cn',
    'huodong.m.taobao.com',
    '3.cn',
    'eco.m.jd.com',
    'www.miguvideo.com',
    'm.miguvideo.com',
    'show.lailianjie.com',
    'www.imkktv.com',
    'www.picarto.tv',
)

OVERSEAS_PLATFORM_HOST = (
    'www.tiktok.com',
    'play.sooplive.co.kr',
    'm.sooplive.co.kr',
    'www.sooplive.com',
    'm.sooplive.com',
    'www.pandalive.co.kr',
    'www.winktv.co.kr',
    'www.flextv.co.kr',
    'www.ttinglive.com',
    'www.popkontv.com',
    'www.twitch.tv',
    'www.liveme.com',
    'www.showroom-live.com',
    'chzzk.naver.com',
    'm.chzzk.naver.com',
    'live.shopee.',
    '.shp.ee',
    'www.youtube.com',
    'youtu.be',
    'www.faceit.com',
)

ALL_HOSTS = PLATFORM_HOST + OVERSEAS_PLATFORM_HOST


def is_known(url: str) -> bool:
    """域名是否属于已知平台。注意名单里有 'live.shopee.' / '.shp.ee'
    这类片段, 所以用子串匹配而不是相等比较 —— 与 main.py 的判断方式一致。"""
    try:
        host = url.split("://", 1)[-1].split("/")[0]
    except Exception:
        return False
    return any(h in host or h in url for h in ALL_HOSTS)

# ---------------------------------------------------------------- 平台识别
# 片段 -> 显示名。片段抄自 main.py 里 `record_url.find("...") > -1` 的那条
# if/elif 链(与 ALL_HOSTS 是两套东西: 那个用于判断"是不是已知平台",
# 这个用于判断"是哪个平台")。上游新增平台后需人工对齐, 对不上只会显示成
# "其他平台", 不影响任何功能。
PLATFORM_RULES = (
    ('douyin.com/', '抖音'), ('tiktok.com/', 'TikTok'),
    ('live.kuaishou.com/', '快手'), ('huya.com/', '虎牙'), ('douyu.com/', '斗鱼'),
    ('yy.com/', 'YY'), ('live.bilibili.com/', 'B站'),
    ('xiaohongshu.com/', '小红书'), ('xhslink.com/', '小红书'),
    ('bigo.tv/', 'Bigo'), ('slink.bigovideo.tv/', 'Bigo'),
    ('app.blued.cn/', 'Blued'),
    ('sooplive.co.kr/', 'SOOP'), ('sooplive.com/', 'SOOP'),
    ('cc.163.com/', '网易CC'), ('look.163.com/', 'Look直播'),
    ('qiandurebo.com/', '千度热播'), ('pandalive.co.kr/', 'PandaTV'),
    ('fm.missevan.com/', '猫耳FM'), ('winktv.co.kr/', 'WinkTV'),
    ('flextv.co.kr/', 'FlexTV'), ('ttinglive.com/', 'FlexTV'),
    ('popkontv.com/', 'PopkonTV'), ('twitcasting.tv/', 'TwitCasting'),
    ('live.baidu.com/', '百度'), ('weibo.com/', '微博'), ('kugou.com/', '酷狗'),
    ('twitch.tv/', 'Twitch'), ('liveme.com/', 'LiveMe'),
    ('huajiao.com/', '花椒'), ('7u66.com/', '流星'),
    ('showroom-live.com/', 'SHOWROOM'),
    ('live.acfun.cn/', 'AcFun'), ('m.acfun.cn/', 'AcFun'),
    ('live.tlclw.com/', '畅聊'), ('ybw1666.com/', '音播'), ('inke.cn/', '映客'),
    ('zhihu.com/', '知乎'), ('chzzk.naver.com/', 'CHZZK'),
    ('haixiutv.com/', '嗨秀'), ('vvxqiu.com/', 'VV星球'),
    ('17.live/', '17LIVE'), ('lang.live/', '浪Live'),
    ('m.pp.weimipopo.com/', '漂漂'), ('.6.cn/', '六间房'),
    ('lehaitv.com/', '乐嗨'), ('h.catshow168.com/', '花猫'),
    ('live.shopee', 'Shopee'), ('shp.ee/', 'Shopee'),
    ('youtube.com/', 'YouTube'), ('youtu.be/', 'YouTube'),
    ('tb.cn', '淘宝'), ('m.jd.com', '京东'), ('3.cn', '京东'),
    ('faceit.com/', 'FACEIT'), ('miguvideo.com', '咪咕'),
    ('show.lailianjie.com', '连接'), ('imkktv.com', '来秀'),
    ('picarto.tv', 'Picarto'),
)

# 长片段优先, 免得 '3.cn' 这种短片段抢走本该归别家的地址
_SORTED_RULES = tuple(sorted(PLATFORM_RULES, key=lambda kv: -len(kv[0])))

OTHER = '其他平台'


def platform_of(url: str) -> str:
    """返回直播间地址所属平台的显示名; 认不出来就是"其他平台"。"""
    u = (url or '').casefold()
    for frag, name in _SORTED_RULES:
        if frag.casefold() in u:
            return name
    return OTHER
