import unittest

from core.wx.model.album import (
    extract_aid,
    normalize_album_item,
    parse_album_info_list,
    parse_cgi_album_info,
)


class AlbumParsingTest(unittest.TestCase):
    def test_extract_aid_short_path(self):
        self.assertEqual(
            extract_aid("https://mp.weixin.qq.com/s/ABC-DEF_123?foo=1"),
            "ABC-DEF_123",
        )

    def test_extract_aid_query_form(self):
        url = "http://mp.weixin.qq.com/s?__biz=MzY5OTQxMTc5OQ==&mid=2247483667&idx=1&sn=abc#rd"
        self.assertEqual(extract_aid(url), "2247483667_1")

    def test_extract_aid_escaped_link(self):
        url = "https://mp.weixin.qq.com/mp/appmsgalbum?__biz=MzY5OTQxMTc5OQ%3D%3D&amp;action=getalbum&amp;album_id=4643"
        aid = extract_aid(url)
        self.assertRegex(aid, r"^album_[0-9a-f]{10}$")  # 无法解析时 md5 兜底稳定值

    def test_normalize_album_item(self):
        item = {
            "title": "Hello",
            "url": "http://mp.weixin.qq.com/s?__biz=X&mid=100&idx=2&sn=s",
            "cover_img_1_1": "http://cover",
            "create_time": "1786343035",
            "item_show_type": "0",
        }
        art = normalize_album_item(item)
        self.assertEqual(art["title"], "Hello")
        self.assertEqual(art["aid"], "100_2")
        self.assertEqual(art["link"], item["url"])
        self.assertEqual(art["create_time"], 1786343035)
        self.assertEqual(art["update_time"], 1786343035)
        self.assertEqual(art["publish_type"], 101)

    def test_parse_album_info_list(self):
        html_text = """
        window.album_info_list = [ {
            title: '谷歌seo实战',
            size: '47' * 1,
            link: 'https://mp.weixin.qq.com/mp/appmsgalbum?__biz=MzY5OTQxMTc5OQ%3D%3D&amp;action=getalbum&amp;album_id=4643084617011642373#wechat_redirect',
        }, {
            title: '另一个',
            size: '3' * 1,
            link: 'https://mp.weixin.qq.com/mp/appmsgalbum?__biz=MzY5OTQxMTc5OQ%3D%3D&amp;action=getalbum&amp;album_id=111#wechat_redirect',
        } ];
        """
        albums = parse_album_info_list(html_text)
        self.assertEqual(len(albums), 2)
        self.assertEqual(albums[0]["album_id"], "4643084617011642373")
        self.assertEqual(albums[0]["title"], "谷歌seo实战")
        self.assertEqual(albums[0]["size"], 47)
        self.assertIn("album_id=4643084617011642373", albums[0]["link"])

    def test_parse_cgi_album_info(self):
        html_text = """
        var ap = arguments.length > 0 && arguments[0] !== undefined
          ? arguments[0] : window.cgiDataNew;
        var isupdating = ap.appmsgalbuminfo
          ? ap.appmsgalbuminfo.isupdating : 0;
        window.cgiDataNew = {
            appmsgalbuminfo: {
                album_id: JsDecode('1375870284640911361'),
                title: JsDecode('李想主义'),
                link: JsDecode('https://mp.weixin.qq.com/mp/appmsgalbum?__biz=X&action=getalbum&album_id=1375870284640911361#wechat_redirect'),
                isupdating: false
            }
        };
        """
        albums = parse_cgi_album_info(html_text)
        self.assertEqual(len(albums), 1)
        self.assertEqual(albums[0]["album_id"], "1375870284640911361")
        self.assertEqual(albums[0]["title"], "李想主义")


if __name__ == "__main__":
    unittest.main()