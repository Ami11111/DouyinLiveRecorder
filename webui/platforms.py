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
