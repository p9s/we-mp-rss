<template>
  <div class="album-management">
    <a-card>
      <template #title>
        <span>公众号合集管理</span>
        <a-tooltip content="合集文章来自公开接口，不受公众号列表接口风控影响，可用于回补历史文章">
          <icon-question-circle style="margin-left: 8px" />
        </a-tooltip>
      </template>
      <template #extra>
        <a-space>
          <a-input v-model="searchMpId" placeholder="公众号 ID (MP_WXS_...)" allow-clear style="width: 220px" />
          <a-button @click="loadAlbums">
            <template #icon>
              <icon-refresh />
            </template>
            刷新
          </a-button>
          <a-button type="primary" @click="showAddModal = true">
            <template #icon>
              <icon-plus />
            </template>
            添加合集
          </a-button>
        </a-space>
      </template>

      <a-table :data="albums" :loading="loading" row-key="id" :pagination="false" bordered>
        <a-table-column title="公众号 ID" data-index="feed_id" width="180" />
        <a-table-column title="合集标题" data-index="title" min-width="200">
          <template #cell="{ record }">
            <a-link :href="record.link" target="_blank">{{ record.title || '合集' }}</a-link>
          </template>
        </a-table-column>
        <a-table-column title="album_id" data-index="album_id" width="200" />
        <a-table-column title="文章数" data-index="article_count" width="120" align="center" />
        <a-table-column title="添加时间" data-index="created_at" width="180">
          <template #cell="{ record }">
            {{ formatTime(record.created_at) }}
          </template>
        </a-table-column>
        <a-table-column title="操作" width="180" fixed="right">
          <template #cell="{ record }">
            <a-space>
              <a-button size="mini" type="primary" status="success" :loading="syncingId === record.id" @click="handleSync(record)">
                同步
              </a-button>
              <a-popconfirm content="确定删除该合集？" @ok="handleDelete(record)">
                <a-button size="mini" status="danger">删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </a-table-column>
      </a-table>
    </a-card>

    <!-- 添加合集 -->
    <a-modal v-model:visible="showAddModal" title="添加公众号合集" :width="680" @ok="handleAdd" :ok-loading="adding">
      <a-form :model="addForm" label-align="left" auto-label-width>
        <a-form-item label="公众号 ID" field="mpId" required>
          <a-input v-model="addForm.mpId" placeholder="如 MP_WXS_3699411799" />
        </a-form-item>
        <a-form-item label="合集/文章 URL" field="albumUrl" required>
          <a-input v-model="addForm.albumUrl" placeholder="支持合集页或文章页链接（含 album_id 或可自动探测）" />
        </a-form-item>
        <a-form-item v-if="discoverList.length > 0" label="探测到的合集">
          <a-list size="small" :bordered="false">
            <a-list-item v-for="(item, idx) in discoverList" :key="idx">
              <div style="display: flex; justify-content: space-between; width: 100%; align-items: center">
                <div>
                  <div>{{ item.title }}</div>
                  <div style="font-size: 12px; color: #86909c">album_id: {{ item.album_id }}</div>
                </div>
                <a-button size="mini" type="primary" @click="applyDiscover(item)">使用此合集</a-button>
              </div>
            </a-list-item>
          </a-list>
        </a-form-item>
      </a-form>
      <div style="margin-top: 12px; display: flex; justify-content: flex-end">
        <a-button :loading="discovering" @click="handleDiscover">自动探测合集</a-button>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import { getAlbums, addAlbum, discoverAlbums, deleteAlbum, syncAlbum } from '@/api/albums'

const albums = ref<any[]>([])
const loading = ref(false)
const showAddModal = ref(false)
const adding = ref(false)
const discovering = ref(false)
const syncingId = ref('')
const searchMpId = ref('')
const discoverList = ref<any[]>([])

const addForm = reactive({
  mpId: '',
  albumUrl: ''
})

const loadAlbums = async () => {
  loading.value = true
  try {
    const res: any = await getAlbums(searchMpId.value || undefined)
    if (res.code === 0) {
      albums.value = res.data || []
    } else {
      Message.error(res.message || '获取合集列表失败')
    }
  } catch (e: any) {
    Message.error(e.message || '获取合集列表失败')
  } finally {
    loading.value = false
  }
}

const handleDiscover = async () => {
  if (!addForm.albumUrl) {
    Message.warning('请输入合集或文章 URL')
    return
  }
  discovering.value = true
  try {
    const res: any = await discoverAlbums(addForm.albumUrl)
    if (res.code === 0 && Array.isArray(res.data) && res.data.length > 0) {
      discoverList.value = res.data
      Message.success('探测成功')
    } else {
      Message.warning(res.message || '未探测到合集信息')
      discoverList.value = []
    }
  } catch (e: any) {
    Message.error(e.message || '探测失败')
  } finally {
    discovering.value = false
  }
}

const applyDiscover = (item: any) => {
  addForm.albumUrl = item.link || addForm.albumUrl
  discoverList.value = [item]
}

const handleAdd = async () => {
  if (!addForm.mpId || !addForm.albumUrl) {
    Message.warning('请填写必填项')
    return
  }
  adding.value = true
  try {
    const res: any = await addAlbum(addForm.mpId, addForm.albumUrl)
    if (res.code === 0) {
      Message.success('添加合集成功')
      showAddModal.value = false
      addForm.mpId = ''
      addForm.albumUrl = ''
      discoverList.value = []
      await loadAlbums()
    } else {
      Message.error(res.message || '添加合集失败')
    }
  } catch (e: any) {
    Message.error(e.message || '添加合集失败')
  } finally {
    adding.value = false
  }
}

const handleSync = async (record: any) => {
  syncingId.value = record.id
  try {
    const res: any = await syncAlbum(record.id)
    if (res.code === 0) {
      const d = res.data || {}
      Message.success(`同步完成，新文章 ${d.new_articles ?? 0} 篇`)
      await loadAlbums()
    } else {
      Message.error(res.message || '同步失败')
    }
  } catch (e: any) {
    Message.error(e.message || '同步失败')
  } finally {
    syncingId.value = ''
  }
}

const handleDelete = async (record: any) => {
  try {
    const res: any = await deleteAlbum(record.id)
    if (res.code === 0) {
      Message.success('删除成功')
      await loadAlbums()
    } else {
      Message.error(res.message || '删除失败')
    }
  } catch (e: any) {
    Message.error(e.message || '删除失败')
  }
}

const formatTime = (t: string) => {
  if (!t) return '-'
  try {
    return new Date(t).toLocaleString()
  } catch {
    return t
  }
}

onMounted(() => {
  loadAlbums()
})
</script>

<style scoped>
.album-management {
  padding: 16px;
}
</style>
