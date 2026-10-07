"""公众号合集(album)采集 API。

合集文章列表来自公开接口（无需公众平台后台登录态 / 微信读书 Cookie），
不受公众号后台文章列表接口风控（-2041 / 200013 / free_publish 404）影响，
可作为回补"已群发"文章历史的补充通道。
"""

import re
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from core.auth import get_current_user_or_ak
from core.db import DB
from core.models.feed import Feed
from core.models.album import FeedAlbum
from core.wx.model.album import MpsAlbum
from jobs.article import UpdateArticle

from .base import error_response, success_response

router = APIRouter(prefix="/albums", tags=["公众号合集"])


def _albums_to_dict(album: FeedAlbum):
    return {
        "id": album.id,
        "feed_id": album.feed_id,
        "album_id": album.album_id,
        "title": album.title,
        "link": album.link,
        "article_count": album.article_count,
        "created_at": album.created_at.isoformat() if album.created_at else None,
    }


def _extract_album_id(url: str) -> str:
    m = re.search(r"album_id=(\d+)", url or "")
    if not m:
        raise ValueError("链接中未找到 album_id")
    return m.group(1)


@router.get("", summary="公众号合集列表")
async def list_albums(
    mp_id: str = Query(None, description="公众号ID，不传则返回全部"),
    current_user: dict = Depends(get_current_user_or_ak),
):
    session = DB.get_session()
    try:
        query = session.query(FeedAlbum)
        if mp_id:
            query = query.filter(FeedAlbum.feed_id == mp_id)
        albums = query.order_by(FeedAlbum.created_at.desc()).all()
        # 合集总数可从公开接口探测，补全未登记的数字
        for album in albums:
            if not album.article_count:
                count = MpsAlbum()._probe_count(album.album_id, album.feed_id)
                if count:
                    album.article_count = count
                    session.commit()
        return success_response([_albums_to_dict(a) for a in albums])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(code=50001, message=f"获取公众号合集失败: {e}"),
        )


@router.post("", summary="添加公众号合集")
async def add_album(
    mp_id: str = Body(..., description="公众号ID（feeds.id）"),
    album_url: str = Body(None, description="合集链接或文章链接"),
    album_id: str = Body(None, description="合集ID（与 album_url 二选一）"),
    title: str = Body(None, description="合集标题"),
    current_user: dict = Depends(get_current_user_or_ak),
):
    session = DB.get_session()
    try:
        feed = session.query(Feed).filter(Feed.id == mp_id).first()
        if not feed:
            return error_response(code=40401, message="公众号不存在")

        if not album_url and not album_id:
            return error_response(code=40001, message="请提供 album_url 或 album_id")

        link = str(album_url or "").strip()
        album_id = str(album_id or "").strip()
        if not album_id:
            m = re.search(r"album_id=(\d+)", link)
            if m:
                album_id = m.group(1)
            else:
                # 给定的是公众号文章链接 → 解析其所属合集
                albums = MpsAlbum().discover_albums(link)
                if not albums:
                    return error_response(code=40002, message="无法从该链接解析出合集，请直接提供合集链接")
                if len(albums) > 1:
                    return error_response(
                        code=40003, data=albums, message="该文章属于多个合集，请指定 album_id"
                    )
                album_id = albums[0]["album_id"]
                title = title or albums[0]["title"]
                link = albums[0]["link"]

        count = MpsAlbum()._probe_count(album_id, feed.id)
        if count == 0:
            return error_response(code=40004, message="album_id 无效或合集为空，无法访问")

        existing = (
            session.query(FeedAlbum)
            .filter(FeedAlbum.feed_id == mp_id, FeedAlbum.album_id == album_id)
            .first()
        )
        if existing:
            return success_response(_albums_to_dict(existing), message="合集已存在")

        album = FeedAlbum(
            id=f"{mp_id}:{album_id}",
            feed_id=mp_id,
            album_id=album_id,
            title=title or f"合集 {album_id}",
            link=link,
            article_count=count,
            created_at=datetime.now(),
        )
        session.add(album)
        session.commit()
        return success_response(_albums_to_dict(album), message="添加合集成功")
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(code=50001, message=f"添加公众号合集失败: {e}"),
        )


@router.post("/discover", summary="解析文章链接所属合集")
async def discover_albums(
    url: str = Query(..., min_length=1, description="公众号文章链接"),
    current_user: dict = Depends(get_current_user_or_ak),
):
    try:
        albums = MpsAlbum().discover_albums(url)
        return success_response(albums)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(code=50001, message=f"解析合集失败: {e}"),
        )


@router.delete("/{album_id}", summary="删除公众号合集")
async def delete_album(
    album_id: str,
    current_user: dict = Depends(get_current_user_or_ak),
):
    session = DB.get_session()
    try:
        album = session.query(FeedAlbum).filter(FeedAlbum.id == album_id).first()
        if not album:
            return error_response(code=40401, message="合集不存在")
        session.delete(album)
        session.commit()
        return success_response({"id": album_id}, message="删除合集成功")
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(code=50001, message=f"删除公众号合集失败: {e}"),
        )


@router.post("/{album_id}/sync", summary="采集公众号合集文章")
async def sync_album(
    album_id: str,
    backfill: bool = False,
    max_page: int = Query(1000, ge=1, le=5000, description="最多翻页数"),
    interval: int = Query(1, ge=0, le=60, description="页间隔(秒)"),
    current_user: dict = Depends(get_current_user_or_ak),
):
    """同步采集该合集全部文章（无需登录态），结果写入文章库。"""
    session = DB.get_session()
    album = session.query(FeedAlbum).filter(FeedAlbum.id == album_id).first()
    if not album:
        return error_response(code=40401, message="合集不存在")

    feed = session.query(Feed).filter(Feed.id == album.feed_id).first()
    if not feed:
        return error_response(code=40401, message="公众号不存在")

    wx = MpsAlbum()
    try:
        wx.get_Articles(
            faker_id=feed.faker_id,
            Mps_id=feed.id,
            Mps_title=feed.mp_name,
            CallBack=UpdateArticle,
            album_id=album.album_id,
            interval=interval,
            MaxPage=max_page,
            backfill=backfill,
        )
        return success_response({
            "feed_id": feed.id,
            "feed_name": feed.mp_name,
            "album_id": album.album_id,
            "album_title": album.title,
            "new_articles": len(wx.articles),
        }, message="合集采集完成")
    except Exception as e:
        print(f"采集合集失败 [{feed.mp_name}]: {e}")
        return error_response(code=50002, message=f"采集合集失败: {e}")