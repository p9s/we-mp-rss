import http from './http'

/** 公众号合集列表 */
export async function getAlbums(mpId?: string) {
    const params = mpId ? { mp_id: mpId } : undefined
    return http.get('/wx/albums', { params })
}

/** 添加合集（album_url 可为文章页或合集页） */
export async function addAlbum(mpId: string, albumUrl: string) {
    return http.post('/wx/albums', { mp_id: mpId, album_url: albumUrl })
}

/** 根据文章 URL 探测合集 */
export async function discoverAlbums(url: string) {
    return http.post('/wx/albums/discover', {}, { params: { url } })
}

/** 删除合集 */
export async function deleteAlbum(albumId: string) {
    return http.delete(`/wx/albums/${encodeURIComponent(albumId)}`)
}

/** 同步合集（采集） */
export async function syncAlbum(albumId: string) {
    return http.post(`/wx/albums/${encodeURIComponent(albumId)}/sync`)
}
