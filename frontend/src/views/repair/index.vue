<template>
  <section class="page" data-module="repair">
    <header class="page-head">
      <div>
        <h2>修复施工管理</h2>
        <p class="page-desc">维护修复单，围绕修复单号、关联缺陷、修复方式、承接单位做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记修复单</button>
        <button class="btn" type="button" @click="exportRows">导出修复施工清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>修复单号</span>
        <input v-model="keyword" placeholder="按修复单号检索" />
      </label>
      <label class="filter-item">
        <span>修复状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="loading" class="page-tip">修复单加载中…</p>
    <p v-else-if="loadError" class="error-text">{{ loadError }}</p>

    <table v-else class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <RouterLink v-if="column === '修复单号'" class="link" :to="`/repair/${row.id}`">
              {{ row[column] ?? '—' }}
            </RouterLink>
            <template v-else>{{ row[column] || '—' }}</template>
          </td>
          <td class="row-actions">
            <template v-if="primaryAction(row.status)">
              <button
                v-if="primaryAction(row.status) !== '提交验收'"
                class="link"
                type="button"
                :disabled="busyId === row.id"
                @click="runQuickAction(primaryAction(row.status) as RepairAction, row)"
              >
                {{ primaryAction(row.status) }}
              </button>
              <button
                v-else
                class="link"
                type="button"
                :disabled="busyId === row.id"
                @click="openAccept(row, '首次')"
              >
                提交验收
              </button>
              <button
                v-if="row.status === '待验收'"
                class="link"
                type="button"
                :disabled="busyId === row.id"
                @click="openAccept(row, '覆盖')"
              >
                更新验收资料
              </button>
            </template>
            <span v-else class="muted-text">无（已完工）</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条修复施工记录</span>
      <span v-if="actionMessage" :class="actionOk ? 'ok-text' : 'error-text'">{{ actionMessage }}</span>
    </footer>

    <AcceptDialog
      :open="acceptOpen"
      :row="acceptRow"
      :mode="acceptMode"
      @close="acceptOpen = false"
      @done="onAcceptDone"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  NetworkError,
  REPAIR_STATUSES,
  fetchRepairList,
  fetchRepairStats,
  runRepairAction,
  type RepairAction,
  type RepairRow,
  type RepairStats,
} from './api'
import AcceptDialog from './AcceptDialog.vue'

const ENDPOINT = '/api/repair'
const columns = ['修复单号', '关联缺陷', '修复方式', '承接单位', '开挖范围', '完成日期', '监理人员', '修复状态']
const statuses = REPAIR_STATUSES

const rows = ref<RepairRow[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref('')
const keyword = ref('')
const statusFilter = ref('')
const actionMessage = ref('')
const actionOk = ref(false)
const stats = ref<RepairStats>({ 待开工: 0, 施工中: 0, 本月完工: 0 })
const busyId = ref<number | null>(null)

const acceptOpen = ref(false)
const acceptRow = ref<RepairRow | null>(null)
const acceptMode = ref<'首次' | '覆盖'>('首次')

const statCards = computed(() => [
  { label: '待开工修复', value: stats.value.待开工 },
  { label: '施工中单据', value: stats.value.施工中 },
  { label: '本月完工数', value: stats.value.本月完工 },
])

const hasFilter = computed(() => Boolean(keyword.value.trim() || statusFilter.value))

const emptyText = computed(() =>
  hasFilter.value
    ? '没有符合当前查询条件的修复单，请放宽关键字或状态后重试'
    : '暂无修复施工数据，可先登记修复单',
)

function primaryAction(status: unknown): RepairAction | '' {
  switch (status) {
    case '待开工':
      return '确认开工'
    case '施工中':
      return '提交验收'
    case '待验收':
      return '确认完工'
    default:
      return ''
  }
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  actionMessage.value = '修复单登记入口尚未接入审批流'
  actionOk.value = false
}

function openAccept(row: RepairRow, mode: '首次' | '覆盖') {
  acceptRow.value = row
  acceptMode.value = mode
  actionMessage.value = ''
  acceptOpen.value = true
}

async function onAcceptDone(entry: RepairRow, message: string) {
  acceptOpen.value = false
  acceptRow.value = null
  actionMessage.value = message
  actionOk.value = true
  await Promise.all([reload(), loadStats()])
  void entry
}

async function runQuickAction(action: RepairAction, row: RepairRow) {
  actionMessage.value = ''
  busyId.value = row.id
  try {
    const result = await runRepairAction(row.id, action)
    actionMessage.value = result.message
    actionOk.value = result.ok
    if (result.ok) await Promise.all([reload(), loadStats()])
  } catch (error) {
    actionOk.value = false
    actionMessage.value = error instanceof Error ? error.message : '修复施工操作失败，请稍后重试'
  } finally {
    busyId.value = null
  }
}

async function reload() {
  loading.value = true
  loadError.value = ''
  try {
    const payload = await fetchRepairList({
      keyword: keyword.value.trim() || undefined,
      status: statusFilter.value || undefined,
    })
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    rows.value = []
    total.value = 0
    if (error instanceof NetworkError) {
      loadError.value = `列表加载失败：网络中断，无法读取最新状态，请检查网络后重试（${error.message}）`
    } else {
      loadError.value = error instanceof Error ? error.message : '修复施工列表读取失败'
    }
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    stats.value = await fetchRepairStats()
  } catch {
    // 卡片读不到时保留上次的值，不打断主流程
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>
