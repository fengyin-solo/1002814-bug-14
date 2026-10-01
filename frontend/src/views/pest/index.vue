<template>
  <section class="page" data-module="pest">
    <header class="page-head">
      <div>
        <h2>病虫害防治管理</h2>
        <p class="page-desc">维护防治记录，围绕防治编号、受害植物、病虫种类、危害等级做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记防治记录</button>
        <button class="btn" type="button" @click="exportRows">导出病虫害防治清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="search">
      <label class="filter-item">
        <span>防治编号</span>
        <input v-model="filters.keyword" placeholder="按防治编号检索" />
      </label>
      <label class="filter-item">
        <span>受害植物</span>
        <input v-model="filters.plant" placeholder="按受害植物检索" />
      </label>
      <label class="filter-item">
        <span>病虫种类</span>
        <input v-model="filters.species" placeholder="按病虫种类检索" />
      </label>
      <label class="filter-item">
        <span>防治状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <form class="filter-bar" @submit.prevent="recompute">
      <label class="filter-item">
        <span>判定标准·严重起(亩)</span>
        <input v-model.number="thresholds.severe_at" type="number" min="0" />
      </label>
      <label class="filter-item">
        <span>重起(亩)</span>
        <input v-model.number="thresholds.heavy_at" type="number" min="0" />
      </label>
      <label class="filter-item">
        <span>中起(亩)</span>
        <input v-model.number="thresholds.medium_at" type="number" min="0" />
      </label>
      <button class="btn" type="submit" :disabled="recomputing">
        {{ recomputing ? '重算中…' : '按标准重算危害等级' }}
      </button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">当前条件下没有防治记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条病虫害防治记录</span>
      <nav class="pager">
        <button class="btn" type="button" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
        <span>第 {{ page }} / {{ totalPages }} 页</span>
        <button class="btn" type="button" :disabled="page >= totalPages" @click="goPage(page + 1)">下一页</button>
      </nav>
    </footer>

    <section class="missing-block">
      <h3>缺防治药剂记录（共 {{ missingTotal }} 条，单独列出，翻页不丢）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in missingRows" :key="String(row.id)">
            <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!missingRows.length">
            <td :colspan="columns.length" class="empty-state">当前条件下没有缺防治药剂的记录</td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span v-if="message" class="error-text">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type PagePayload = { items?: Row[]; total?: number | null; page?: number; size?: number }

const ENDPOINT = '/api/pest'
const PAGE_SIZE = 5
const columns = ['防治编号', '受害植物', '病虫种类', '危害等级', '发生面积', '防治药剂', '防治日期', '防治状态']
const actions = ['安排防治', '开始防治', '安排复查']
const statuses = ['待防治', '防治中', '已防治', '需复查']

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const missingRows = ref<Row[]>([])
const missingTotal = ref(0)
const message = ref('')
const recomputing = ref(false)

const filters = reactive<Record<string, string>>({ keyword: '', plant: '', species: '', status: '' })
const thresholds = reactive({ severe_at: 50, heavy_at: 20, medium_at: 5 })

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const stats = computed(() => [
  { label: '符合条件记录', value: total.value },
  { label: '缺防治药剂记录', value: missingTotal.value },
  { label: '当前页 / 总页数', value: `${page.value} / ${totalPages.value}` },
])

// 同一查询条件的在途请求只保留一个：重复提交直接复用同一个 Promise。
const inflight = new Map<string, Promise<void>>()
let refreshSeq = 0

function filterParams(): Record<string, string> {
  const params: Record<string, string> = {}
  for (const [key, value] of Object.entries(filters)) {
    if (value.trim()) params[key] = value.trim()
  }
  return params
}

function listQuery(includePage: boolean): string {
  const params = new URLSearchParams(filterParams())
  if (includePage) {
    params.set('page', String(page.value))
    params.set('size', String(PAGE_SIZE))
  }
  return params.toString()
}

async function fetchPage(url: string, retried = false): Promise<PagePayload> {
  const response = await request(url)
  if (!response.ok) {
    throw new Error('防治记录列表读取失败')
  }
  const payload = (await response.json()) as PagePayload
  // 总数取不到时按同一条件重新取一次，仍取不到就退回当前页条数。
  if (payload.total === null || payload.total === undefined) {
    if (!retried) {
      return fetchPage(url, true)
    }
    payload.total = (payload.items ?? []).length
  }
  return payload
}

async function reload(force = false) {
  message.value = ''
  // 强制刷新（动作、重算后）换一个去重键；普通提交按查询条件去重。
  const cacheKey = force ? `__refresh_${refreshSeq++}` : listQuery(true)
  const pending = inflight.get(cacheKey)
  if (pending) return pending

  const listUrl = `${ENDPOINT}?${listQuery(true)}`
  const missingUrl = `${ENDPOINT}/missing-pesticide?${listQuery(false)}`

  const task = (async () => {
    // 主清单与缺药剂清单共用同一套筛选条件，并行取数。
    const [listPayload, missingPayload] = await Promise.all([
      fetchPage(listUrl),
      fetchPage(missingUrl),
    ])
    rows.value = listPayload.items ?? []
    total.value = Number(listPayload.total ?? 0)
    const maxPage = Math.max(1, Math.ceil(total.value / PAGE_SIZE))
    if (page.value > maxPage) {
      page.value = maxPage
      syncUrl()
    }
    missingRows.value = missingPayload.items ?? []
    missingTotal.value = Number(missingPayload.total ?? 0)
  })()

  inflight.set(cacheKey, task)
  try {
    await task
  } catch (error) {
    message.value = error instanceof Error ? error.message : '病虫害防治列表读取失败'
  } finally {
    inflight.delete(cacheKey)
  }
}

function syncUrl() {
  const params = new URLSearchParams(filterParams())
  if (page.value > 1) params.set('page', String(page.value))
  const query = params.toString()
  const target = query ? `?${query}` : route.path
  if (route.fullPath !== target) {
    void router.replace(target)
  }
}

function applyRoute() {
  const q = route.query
  filters.keyword = String(q.keyword ?? '')
  filters.plant = String(q.plant ?? '')
  filters.species = String(q.species ?? '')
  filters.status = String(q.status ?? '')
  page.value = Math.max(1, Number(q.page) || 1)
}

function search() {
  page.value = 1
  const params = new URLSearchParams(filterParams())
  const query = params.toString()
  const target = query ? `?${query}` : route.path
  if (route.fullPath === target) {
    // 地址没变（同一查询条件重复提交）：路由不会回调，直接触发，由在途去重只算一次。
    void reload()
  }
  // 地址变化时由 route 监听统一刷新，避免重复请求。
  else void router.replace(target)
}

function goPage(next: number) {
  if (next < 1 || next > totalPages.value || next === page.value) return
  page.value = next
  syncUrl()
}

function resetFilters() {
  filters.keyword = ''
  filters.plant = ''
  filters.species = ''
  filters.status = ''
  page.value = 1
  search()
}

function exportRows() {
  // 导出沿用当前筛选条件，后端与列表走同一口径，条数一致。
  const query = listQuery(false)
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function openCreate() {
  message.value = '防治记录登记入口尚未接入审批流'
}

async function recompute() {
  message.value = ''
  recomputing.value = true
  try {
    const response = await request(`${ENDPOINT}/recompute-levels`, {
      method: 'POST',
      body: JSON.stringify({ values: thresholds }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    message.value = payload.message || (payload.ok ? '危害等级已重算' : '危害等级重算失败')
    if (payload.ok) {
      await reload(true)
    }
  } catch (error) {
    message.value = error instanceof Error ? error.message : '危害等级重算失败'
  } finally {
    recomputing.value = false
  }
}

async function runAction(action: string, row: Row) {
  message.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('病虫害防治动作未生效，请稍后重试')
    }
    await reload(true)
  } catch (error) {
    message.value = error instanceof Error ? error.message : '病虫害防治操作失败'
  }
}

// 浏览器前进/后退时从地址栏还原筛选条件与页码。
watch(
  () => route.fullPath,
  () => {
    applyRoute()
    void reload()
  },
)

onMounted(() => {
  applyRoute()
  void reload()
})
</script>
