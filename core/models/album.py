from .base import Base, Column, String, Integer, DateTime


class FeedAlbum(Base):
    """公众号合集(album)采集登记

    合集文章列表来自公开接口 ``mp/appmsgalbum?action=getalbum``，
    一个公众号可以登记多个合集，采集时按登记的 album_id 分页拉取。
    """
    from_attributes = True
    __tablename__ = 'feed_albums'
    id = Column(String(255), primary_key=True)
    feed_id = Column(String(255), index=True)
    album_id = Column(String(64), index=True)
    title = Column(String(255))
    link = Column(String(500))
    article_count = Column(Integer, default=0)
    created_at = Column(DateTime)