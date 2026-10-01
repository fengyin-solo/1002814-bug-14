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

    <section class="grade-panel">
      <div class="grade-head">
        <span>危害等级判定标准（按发生面积）</span>
        <button class="link" type="button" @click="showGradeForm = !showGradeForm">
          {{ showGradeForm ? '收起' : '调整等级标准' }}
        </button>
      </div>
      <p class="grade-desc">
        当前：发生面积 ≥ {{ gradeRules.severe_threshold }} 判「重度」，≥ {{ gradeRules.moderate_threshold }} 判「中度」，其余判「轻度」。调整后已有记录会全部重算。
      </p>
      <form v-if="showGradeForm" class="grade-form" @submit.prevent="saveGradeRules">
        <label class="filter-item">
          <span>重度阈值（亩）</span>
          <input v-model.number="gradeDraft.severe_threshold" type="number" min="0" step="0.1" />
        </label>
        <label class="filter-item">
          <span>中度阈值（亩）</span>
          <input v-model.number="gradeDraft.moderate_threshold" type="number" min="0" step="0.1" />
        </label>
        <button class="btn primary" type="submit">保存并重算</button>
      </form>
    </section>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>防治编号</span>
        <input v-model="filters.keyword" placeholder="按防治编号检索" />
      </label>
      <label class="filter-item">
        <span>受害植物</span>
        <input v-model="filters.plant" placeholder="按受害植物名称检索" />
      </label>
      <label class="filter-item">
        <span>病虫种类</span>
        <select v-model="filters.species">
          <option value="">全部种类</option>
          <option v-for="species in speciesOptions" :key="species" :value="species">{{ species }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>防治状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item filter-check">
        <input v-model="filters.missing_chemical" type="checkbox" />
        <span>只看缺防治药剂</span>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">
            {{ column }}<em v-if="column === '危害等级'" class="sort-hint">（高→低）</em>
          </th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '防治药剂' && isEmpty(row[column])" class="missing-tag">未填药剂</span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
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
      <div class="pager">
        <button class="btn" type="button" :disabled="page <= 1" @click="goToPage(page - 1)">上一页</button>
        <span>第 {{ page }} / {{ totalPages }} 页</span>
        <button class="btn" type="button" :disabled="page >= totalPages" @click="goToPage(page + 1)">下一页</button>
        <label class="size-item">
          每页
          <select v-model.number="size" @change="applyFilters">
            <option :value="5">5</option>
            <option :value="10">10</option>
            <option :value="20">20</option>
          </select>
          条
        </label>
      </div>
      <span>共 {{ total }} 条病虫害防治记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section class="missing-panel">
      <div class="grade-head">
        <span>缺防治药剂记录（{{ missingRows.length }} 条）</span>
        <button class="link" type="button" @click="reloadMissing">刷新</button>
      </div>
      <p class="grade-desc">以下记录尚未登记防治药剂，单独列出便于补录；排序与主清单一致，不会因翻页丢失。</p>
      <table class="data-table">
        <thead>
          <tr><th v-for="column in columns" :key="column">{{ column }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in missingRows" :key="String(row.id)">
            <td v-for="column in columns" :key="column">
              <span v-if="column === '防治药剂'" class="missing-tag">未填药剂</span>
              <template v-else>{{ row[column] ?? '—' }}</template>
            </td>
          </tr>
          <tr v-if="!missingRows.length">
            <td :colspan="columns.length" class="empty-state">暂无缺药剂记录</td>
          </tr>
        </tbody>
      </table>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/pest'
const columns = ["防治编号", "受害植物", "病虫种类", "危害等级", "发生面积", "防治药剂", "防治日期", "防治状态"]
const actions = ["安排防治", "开始防治", "安排复查"]
const statuses = ["待防治", "防治中", "已防治", "需复查"]
const stats = [{ "label": "待防治记录", "value": 0 }, { "label": "防治中记录", "value": 0 }, { "label": "需复查记录", "value": 0 }]

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const missingRows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(10)
const errorMessage = ref('')
const speciesOptions = ref<string[]>([])
const showGradeForm = ref(false)
const gradeRules = reactive({ severe_threshold: 50, moderate_threshold: 20 })
const gradeDraft = reactive({ severe_threshold: 50, moderate_threshold: 20 })

const filters = reactive({
  keyword: '',
  plant: '',
  species: '',
  status: '',
  missing_chemical: false,
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size.value)))

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || String(value).trim() === ''
}

// 把查询条件同步到地址栏：翻页、刷新、从详情回来都能带回已选条件
function syncUrl(nextPage = page.value) {
  const query: Record<string, string> = { page: String(nextPage), size: String(size.value) }
  if (filters.keyword.trim()) query.keyword = filters.keyword.trim()
  if (filters.plant.trim()) query.plant = filters.plant.trim()
  if (filters.species) query.species = filters.species
  if (filters.status) query.status = filters.status
  if (filters.missing_chemical) query.missing_chemical = '1'
  void router.replace({ query })
}

function readUrl() {
  filters.keyword = String(route.query.keyword ?? '')
  filters.plant = String(route.query.plant ?? '')
  filters.species = String(route.query.species ?? '')
  filters.status = String(route.query.status ?? '')
  filters.missing_chemical = route.query.missing_chemical === '1'
  page.value = Math.max(Number(route.query.page) || 1, 1)
  size.value = Number(route.query.size) || 10
}

function buildQuery(nextPage: number, nextSize = size.value): string {
  const params = new URLSearchParams()
  params.set('page', String(nextPage))
  params.set('size', String(nextSize))
  if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
  if (filters.plant.trim()) params.set('plant', filters.plant.trim())
  if (filters.species) params.set('species', filters.species)
  if (filters.status) params.set('status', filters.status)
  if (filters.missing_chemical) params.set('missing_chemical', 'true')
  return params.toString()
}

// 与清单同一份筛选条件，不带分页参数，供 /count 重新取总数使用
function buildFilterQuery(): string {
  const params = new URLSearchParams()
  if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
  if (filters.plant.trim()) params.set('plant', filters.plant.trim())
  if (filters.species) params.set('species', filters.species)
  if (filters.status) params.set('status', filters.status)
  if (filters.missing_chemical) params.set('missing_chemical', 'true')
  return params.toString()
}

async function reload() {
  errorMessage.value = ''
  syncUrl()
  try {
    const response = await request(`${ENDPOINT}?${buildQuery(page.value)}`)
    if (!response.ok) {
      throw new Error('防治记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    // 总数取不到时按同一份条件重新取一次，避免页脚条数与实际不符
    if (typeof payload.total !== 'number') {
      const retried = await fetchTotalWithRetry()
      total.value = retried ?? rows.value.length
    } else {
      total.value = payload.total
    }
    if (page.value > totalPages.value) {
      goToPage(totalPages.value)
    }
    await reloadMissing()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '病虫害防治列表读取失败'
  }
}

async function fetchTotalWithRetry(): Promise<number | null> {
  // 按同一份筛选条件重新取一次总数；仍取不到则交回调用方兜底
  const suffix = buildFilterQuery()
  for (const attempt of [1, 2]) {
    try {
      const response = await request(`${ENDPOINT}/count${suffix ? `?${suffix}` : ''}`)
      if (response.ok) {
        const payload = await response.json()
        if (typeof payload.total === 'number') return payload.total
      }
    } catch {
      // 第一次失败不提示，再试一次；两次都失败由调用方兜底
    }
    if (attempt === 1) continue
  }
  return null
}

async function reloadMissing() {
  try {
    const params = new URLSearchParams()
    if (filters.plant.trim()) params.set('plant', filters.plant.trim())
    if (filters.species) params.set('species', filters.species)
    const suffix = params.toString()
    const response = await request(`${ENDPOINT}/missing-chemical${suffix ? `?${suffix}` : ''}`)
    if (response.ok) {
      const payload = await response.json()
      missingRows.value = payload.items ?? []
    }
  } catch {
    // 缺药剂区只是辅助清单，失败时不打断主清单
  }
}

async function loadGradeRules() {
  try {
    const response = await request(`${ENDPOINT}/grade-rules`)
    if (response.ok) {
      const payload = await response.json()
      gradeRules.severe_threshold = payload.severe_threshold
      gradeRules.moderate_threshold = payload.moderate_threshold
      gradeDraft.severe_threshold = payload.severe_threshold
      gradeDraft.moderate_threshold = payload.moderate_threshold
    }
  } catch {
    // 等级标准读取失败时保留默认值，不阻断页面
  }
}

async function saveGradeRules() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/grade-rules`, {
      method: 'PUT',
      body: JSON.stringify({
        values: {
          severe_threshold: gradeDraft.severe_threshold,
          moderate_threshold: gradeDraft.moderate_threshold,
        },
      }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '等级标准更新失败')
    }
    gradeRules.severe_threshold = gradeDraft.severe_threshold
    gradeRules.moderate_threshold = gradeDraft.moderate_threshold
    showGradeForm.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '等级标准更新失败'
  }
}

function applyFilters() {
  page.value = 1
  void reload()
}

function resetFilters() {
  filters.keyword = ''
  filters.plant = ''
  filters.species = ''
  filters.status = ''
  filters.missing_chemical = false
  page.value = 1
  void reload()
}

function goToPage(next: number) {
  if (next < 1 || next > totalPages.value || next === page.value) return
  page.value = next
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export?${buildQuery(1, 10000)}`, '_blank')
}

function openCreate() {
  errorMessage.value = '防治记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('病虫害防治动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '病虫害防治操作失败'
  }
}

onMounted(async () => {
  readUrl()
  // 病虫种类下拉直接取当前数据里出现过的种类，避免选了查不到
  try {
    const probe = await request(`${ENDPOINT}?page=1&size=200`)
    if (probe.ok) {
      const payload = await probe.json()
      speciesOptions.value = [...new Set(
        (payload.items as Row[]).map((item) => String(item['病虫种类'] ?? '').trim()).filter(Boolean),
      )].sort()
    }
  } catch {
    // 下拉选项取不到时仍可手工输入查询（种类输入框退化为下拉时忽略）
  }
  await loadGradeRules()
  await reload()
})
</script>

<style scoped>
.grade-panel,
.missing-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.grade-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
}
.grade-desc {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 12px;
}
.grade-form {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-end;
  margin-top: 10px;
}
.filter-check {
  display: flex;
  align-items: center;
  gap: 4px;
}
.filter-check span {
  font-size: 12px;
  color: var(--muted);
}
.sort-hint {
  font-style: normal;
  color: var(--muted);
  font-weight: 400;
  font-size: 12px;
}
.missing-tag {
  color: #b42318;
  font-weight: 600;
}
.pager {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pager .btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.size-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.missing-panel {
  margin-top: 16px;
}
</style>
