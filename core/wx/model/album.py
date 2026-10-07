"""WeChat Official Account album (合集) collector.

合集文章列表来自公开接口 ``mp/appmsgalbum?action=getalbum``，无需登录
（公众平台后台 token / 微信读书 Cookie），也不受公众号后台文章列表接口
风控（-2041 / 200013 / free_publish 404）影响。适合回补"已群发"文章历史。

已知边界（2026-09 实测）:
- 该接口已对任意账号开放；文章列表分页由 ``begin_msgid / begin_itemidx``
  游标驱动（``begin`` 偏移不可用），每页最多 20 条。
- 合集中的文章可能给出 ``mp.weixin.qq.com/s?__biz=...&mid=...`` 形式链接
  （不带 /s/ 短 token），需按 mid/idx 构造稳定 aid。
- 只收录"已群发并入合集"的文章；订阅前已删除/未入合集的不在此列。
"""

import hashlib
import html
import re
import time
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from core.print import print_info, print_warning
from core.wx.base import WxGather


ALBUM_API = "https://mp.weixin.qq.com/mp/appmsgalbum"


def _to_int(value, default=0):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def extract_aid(url: str) -> str:
    """从文章链接推导稳定的 aid。

    优先取 /s/ 短 token；合集接口返回的 ``s?__biz=..&mid=..&idx=..`` 形式
    则用 ``mid_idx`` 保证稳定与唯一。
    """
    url = html.unescape(str(url or ""))
    m = re.search(r"mp\.weixin\.qq\.com/s/([A-Za-z0-9_\-]+)", url)
    if m:
        return m.group(1)
    q = parse_qs(urlparse(url).query)
    mid = (q.get("mid") or [""])[0]
    idx = (q.get("idx") or ["0"])[0]
    if mid:
        return f"{mid}_{idx}"
    sn = (q.get("sn") or [""])[0]
    if sn:
        return f"sn_{sn[:16]}"
    return f"album_{hashlib.md5(url.encode('utf-8')).hexdigest()[:10]}"


def normalize_album_item(item: dict) -> dict:
    """把 getalbum_resp.article_list 条目标准化为 FillBack 数据结构。"""
    url = html.unescape(str(item.get("url") or ""))
    create_time = _to_int(item.get("create_time"))
    item_show_type = _to_int(item.get("item_show_type"))
    return {
        "aid": extract_aid(url),
        "title": str(item.get("title") or ""),
        "link": url,
        "cover": str(item.get("cover_img_1_1") or item.get("cover_img_1_1_show") or ""),
        "digest": "",
        "content": "",
        "create_time": create_time,
        "update_time": create_time,
        "publish_type": 101,
        "art_type": item_show_type,
        "show_type": item_show_type,
        "item_show_type": item_show_type,
    }


def parse_album_info_list(html_text: str) -> list:
    """从文章页 HTML 提取所属合集列表（老式 ``album_info_list`` 语法）。"""
    albums = []
    m = re.search(r"album_info_list\s*=\s*\[", html_text or "", re.S)
    if not m:
        return albums
    j = m.end() - 1
    depth, quote, k = 0, None, j
    while k < len(html_text):
        ch = html_text[k]
        if quote:
            if ch == "\\":
                k += 1
            elif ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                break
        k += 1
    block = html_text[j:k + 1]
    if not block:
        return albums
    for link in re.finditer(r"link\s*:\s*['\"]([^'\"]+)['\"]", block):
        link_url = html.unescape(link.group(1))
        album_id = re.search(r"album_id=(\d+)", link_url)
        if not album_id:
            continue
        nearby = block[max(0, link.start() - 400):link.start()]
        title = re.search(r"title\s*:\s*['\"]([^'\"]{1,60})['\"]", nearby, re.S)
        size = re.search(r"size\s*:\s*['\"\s]*(\d+)", nearby, re.S)
        albums.append({
            "album_id": album_id.group(1),
            "title": title.group(1) if title else "合集",
            "size": int(size.group(1)) if size else 0,
            "link": link_url,
        })
    return albums


def parse_cgi_album_info(html_text: str) -> list:
    """从文章页 HTML 提取所属合集（新式 ``window.cgiDataNew.appmsgalbuminfo``）。"""
    albums = []
    for block in re.findall(r"appmsgalbuminfo\s*[:=]\s*(\{.*?\})\s*[,;}[]", html_text or "", re.S):
        album_id = re.search(r"['\"]?album_id['\"]?\s*:\s*(?:JsDecode\('(\d+)'\)|['\"](\d+)['\"]|(\d+))", block)
        title = re.search(r"['\"]?title['\"]?\s*:\s*(?:JsDecode\('([^']+)'\)|['\"]([^'\"]+)['\"]|([^,}]+))", block)
        link = re.search(r"['\"]?link['\"]?\s*:\s*(?:JsDecode\('([^']+)'\)|['\"]([^'\"]+)['\"])", block)
        album_id_val = next((g for g in album_id.groups() if g), "") if album_id else ""
        if not album_id_val:
            m = re.search(r"album_id=(\d+)", block)
            if m:
                album_id_val = m.group(1)
        if not album_id_val:
            continue
        title_val = next((g for g in title.groups() if g), "合集") if title else "合集"
        link_url = next((g for g in link.groups() if g), "") if link else ""
        if not link_url:
            m = re.search(r"album_id=(\d+)", block)
            link_url = f"https://mp.weixin.qq.com/mp/appmsgalbum?__biz=&action=getalbum&album_id={album_id_val}"
        albums.append({
            "album_id": album_id_val,
            "title": html.unescape(title_val).strip(),
            "size": 0,
            "link": html.unescape(link_url),
        })
    return albums


class MpsAlbum(WxGather):
    """公众号合集采集器（公开接口，无需登录态）。"""

    def discover_albums(self, article_url: str) -> list:
        """抓取文章页并解析其所属合集。"""
        html_text = self._fetch_article_page(article_url)
        if not html_text:
            return []
        albums = parse_album_info_list(html_text)
        if not albums:
            albums = parse_cgi_album_info(html_text)
        return albums

    def _fetch_article_page(self, url: str) -> str:
        try:
            headers = self.fix_header(url)
            resp = self.session.get(url, headers=headers, verify=False, timeout=(10, 30))
            if resp.status_code == 200 and "当前环境异常" not in resp.text:
                return resp.text
            print_warning("文章页被要求验证或不可访问，无法解析合集")
        except Exception as e:
            print_warning(f"文章页请求异常: {e}")
        return ""

    def get_Articles(
        self,
        faker_id: str = None,
        Mps_id: str = None,
        Mps_title: str = "",
        CallBack=None,
        album_id: str = None,
        interval: int = 1,
        start_page: int = 0,
        MaxPage: int = 1000,
        Item_Over_CallBack=None,
        Over_CallBack=None,
        backfill: bool = False,
    ):
        """按 album_id 分页拉取合集全部文章并回调入库。

        不需要公众平台后台登录态/微信读书 Cookie；``faker_id`` 即 __biz。
        """
        self.articles = []
        self.get_token()
        if not faker_id and Mps_id:
            faker_id = self._feed_faker_id(Mps_id)
        if not album_id:
            self.Error("合集采集需要 album_id")
            return

        count = 20
        print_info(f"合集采集模式, {'全量回补' if backfill else '增量'}: [{Mps_title}] album_id={album_id}")
        begin_msgid = ""
        begin_itemidx = ""
        page = start_page
        total = 0
        while True:
            if page >= MaxPage:
                print_warning(f"合集采集达到页数上限({MaxPage})，停止")
                break
            params = {
                "action": "getalbum",
                "__biz": faker_id or "",
                "album_id": album_id,
                "count": str(count),
                "is_reverse": "0",
                "f": "json",
            }
            if begin_msgid:
                params["begin_msgid"] = str(begin_msgid)
                params["begin_itemidx"] = str(begin_itemidx)
            if page > start_page:
                time.sleep(max(1, int(interval)))
            try:
                resp = self.session.get(
                    ALBUM_API,
                    params=params,
                    headers=self.fix_header(ALBUM_API),
                    verify=False,
                    timeout=(10, 30),
                )
                msg = resp.json()
            except Exception as e:
                print_warning(f"合集[{album_id}]第{page + 1}页请求异常: {e}")
                break

            br = msg.get("base_resp", {})
            ret = br.get("ret", -1)
            if ret != 0:
                err = br.get("err_msg", "")
                print_warning(f"合集[{album_id}]返回错误 ret={ret} err={err}")
                if ret == 10004:
                    print_warning("album_id 无效或不存在")
                super().Error(f"合集接口错误: ret={ret} {err}")
                break

            gr = msg.get("getalbum_resp") or {}
            article_list = gr.get("article_list") or []
            if not article_list:
                print_info(f"合集[{album_id}]第{page + 1}页无数据，结束")
                break

            for item in article_list:
                art = normalize_album_item(item)
                art["mp_id"] = Mps_id
                art["id"] = art["aid"]
                if CallBack is not None:
                    super().FillBack(
                        CallBack=CallBack,
                        data=art,
                        Ext_Data={"mp_title": Mps_title, "mp_id": Mps_id},
                    )
                    total += 1

            last = article_list[-1]
            begin_msgid = last.get("msgid", "")
            begin_itemidx = last.get("itemidx", "")
            page += 1
            if str(gr.get("continue_flag", "0")) != "1":
                print_info(f"合集[{album_id}]翻页结束")
                break

        print_info(f"合集[{album_id}] [{Mps_title}] 采集完成：{page} 页 / {total} 条")
        super().Over(CallBack=Over_CallBack)

    def _probe_count(self, album_id: str, feed_id: str = None) -> int:
        """探集合集文章总数（第一页 base_info.article_count），失败返回 0。"""
        try:
            faker_id = self._feed_faker_id(feed_id) if feed_id else ""
            params = {
                "action": "getalbum",
                "__biz": faker_id or "",
                "album_id": album_id,
                "count": "1",
                "is_reverse": "0",
                "f": "json",
            }
            resp = self.session.get(
                ALBUM_API, params=params, headers=self.fix_header(ALBUM_API),
                verify=False, timeout=(10, 30),
            )
            msg = resp.json()
            if msg.get("base_resp", {}).get("ret", -1) != 0:
                return 0
            return _to_int(msg.get("getalbum_resp", {}).get("base_info", {}).get("article_count"))
        except Exception:
            return 0

    def _feed_faker_id(self, mp_id: str) -> str:
        try:
            from core.db import DB
            from core.models.feed import Feed
            session = DB.get_session()
            feed = session.query(Feed).filter(Feed.id == mp_id).first()
            if feed:
                return feed.faker_id or ""
        except Exception as e:
            print_warning(f"读取公众号 faker_id 失败: {e}")
        return ""