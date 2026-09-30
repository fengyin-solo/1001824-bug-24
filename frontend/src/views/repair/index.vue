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
      <article v-for="item in stats" :key="item.label" class="stat-card">
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

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button v-if="column === '修复单号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
            <button
              v-if="nextActionFor(row)"
              class="link"
              type="button"
              @click="dispatchAction(nextActionFor(row), row)"
            >
              {{ nextActionFor(row) }}
            </button>
            <span v-else class="muted-text">已到终态</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyHint }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条修复施工记录</span>
      <span v-if="successMessage" class="success-text">{{ successMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 提交验收：完成日期、监理人员在这里填写；提交失败时弹窗保留，内容不丢、可原样重试 -->
    <div v-if="acceptVisible" class="modal-mask" @click.self="closeAccept">
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-head">
          <h3>提交验收</h3>
          <button class="btn ghost" type="button" @click="closeAccept">关闭</button>
        </div>
        <p class="modal-desc">
          修复单 {{ acceptForm.修复单号 }} 当前为「{{ acceptForm.currentStatus }}」。
          提交后进入待验收；若网络中断，重新打开仍会保留本次填写内容，可直接重试，不会产生重复验收记录。
        </p>
        <div class="form-item">
          <label for="accept-date">完成日期 <span class="error-text">*</span></label>
          <input id="accept-date" v-model="acceptForm.完成日期" type="date" />
        </div>
        <div class="form-item">
          <label for="accept-supervisor">监理人员 <span class="error-text">*</span></label>
          <input
            id="accept-supervisor"
            v-model="acceptForm.监理人员"
            type="text"
            placeholder="请输入监理人员姓名"
          />
        </div>
        <p v-if="acceptError" class="error-text">{{ acceptError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" :disabled="acceptLoading" @click="closeAccept">取消</button>
          <button class="btn primary" type="button" :disabled="acceptLoading" @click="submitAcceptance">
            {{ acceptLoading ? '提交中…' : '确认提交验收' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 详情：状态直接来自后端 status，和列表是同一份数据，重开页面也不会不一致 -->
    <div v-if="detailVisible" class="modal-mask" @click.self="closeDetail">
      <div class="modal modal-lg" role="dialog" aria-modal="true">
        <div class="modal-head">
          <h3>修复单详情</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </div>
        <p v-if="detailError" class="error-text">{{ detailError }}</p>
        <template v-else-if="detail">
          <table class="detail-table">
            <tbody>
              <tr v-for="column in detailColumns" :key="column">
                <th>{{ column }}</th>
                <td>{{ detail[column] ?? '—' }}</td>
              </tr>
            </tbody>
          </table>

          <h4 class="detail-subhead">验收记录</h4>
          <template v-if="acceptanceRecord">
            <table class="detail-table">
              <tbody>
                <tr>
                  <th>完成日期</th>
                  <td>{{ acceptanceRecord['完成日期'] }}</td>
                </tr>
                <tr>
                  <th>监理人员</th>
                  <td>{{ acceptanceRecord['监理人员'] }}</td>
                </tr>
                <tr>
                  <th>最近提交时间</th>
                  <td>{{ acceptanceRecord['提交时间'] }}</td>
                </tr>
              </tbody>
            </table>
            <p class="muted-text">每张修复单只保留一条验收记录，重新提交会覆盖而不是新增。</p>
          </template>
          <p v-else class="muted-text">{{ acceptanceEmptyHint }}</p>

          <div class="modal-actions">
            <button
              v-if="detailNextAction"
              class="btn primary"
              type="button"
              :disabled="detailLoading"
              @click="dispatchAction(detailNextAction, detail)"
            >
              {{ detailLoading ? '执行中…' : detailNextAction }}
            </button>
            <span v-else class="muted-text">该修复单已完工，没有可继续执行的动作。</span>
          </div>
        </template>
        <p v-else class="muted-text">详情加载中…</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type AcceptanceRecord = { 完成日期: string; 监理人员: string; 提交时间: string }

const ENDPOINT = '/api/repair'
const columns = ['修复单号', '关联缺陷', '修复方式', '承接单位', '开挖范围', '完成日期', '监理人员', '修复状态']
const statuses = ['待开工', '施工中', '待验收', '已完工']
const NEXT_ACTIONS: Record<string, string> = {
  待开工: '确认开工',
  施工中: '提交验收',
  待验收: '确认完工',
}
const STAT_LABELS: Record<string, string> = {
  待开工: '待开工修复',
  施工中: '施工中单据',
  待验收: '待验收单据',
  已完工: '已完工单据',
  本月完工数: '本月完工数',
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const stats = ref<{ label: string; value: number }[]>(
  ['待开工', '施工中', '本月完工数'].map((key) => ({ label: STAT_LABELS[key], value: 0 })),
)

const acceptVisible = ref(false)
const acceptLoading = ref(false)
const acceptError = ref('')
const acceptForm = reactive({
  id: 0,
  修复单号: '',
  currentStatus: '',
  完成日期: '',
  监理人员: '',
})

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detail = ref<Row | null>(null)

const detailColumns = columns
const acceptanceRecord = computed<AcceptanceRecord | null>(() => {
  const record = detail.value?.['验收记录'] as unknown
  return record && typeof record === 'object' ? (record as AcceptanceRecord) : null
})
const detailNextAction = computed(() => (detail.value ? NEXT_ACTIONS[String(detail.value.status ?? '')] : ''))
const acceptanceEmptyHint = computed(() => {
  const status = String(detail.value?.status ?? '')
  if (status === '待开工') {
    return '暂无验收记录：修复单还在待开工，请先确认开工，再在施工中提交验收。'
  }
  if (status === '施工中') {
    return '暂无验收记录：该修复单尚未提交验收，请在下方点击「提交验收」填写完成日期与监理人员。'
  }
  return '暂无验收记录：系统未查询到该修复单的验收数据，请联系管理员核对。'
})
const hasFilter = computed(() => Boolean(keyword.value.trim() || statusFilter.value))
const emptyHint = computed(() =>
  hasFilter.value
    ? '没有符合当前筛选条件的修复单，请调整关键字或状态后重新查询'
    : '暂无修复施工数据，可先登记修复单',
)

function nextActionFor(row: Row): string {
  return NEXT_ACTIONS[String(row.status ?? '')] ?? ''
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
  errorMessage.value = '修复单登记入口尚未接入审批流'
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      throw new Error('概览卡片读取失败')
    }
    const payload = (await response.json()) as Record<string, number>
    stats.value = ['待开工', '施工中', '本月完工数'].map((key) => ({
      label: STAT_LABELS[key],
      value: payload[key] ?? 0,
    }))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '概览卡片读取失败'
  }
}

async function reload() {
  errorMessage.value = ''
  successMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value.trim()) {
    params.set('keyword', keyword.value.trim())
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  const query = params.toString()
  try {
    const response = await request(`${ENDPOINT}${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error('修复单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await loadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '修复施工列表读取失败'
  }
}

async function readActionResult(response: Response): Promise<{ ok: boolean; message: string; entry: Row | null }> {
  let payload: { ok?: boolean; message?: string; entry?: Row | null } = {}
  try {
    payload = await response.json()
  } catch {
    payload = {}
  }
  if (!response.ok) {
    const detail = payload.message || `服务暂不可用（HTTP ${response.status}），请稍后重试`
    throw new Error(String(detail))
  }
  return {
    ok: Boolean(payload.ok),
    message: String(payload.message ?? ''),
    entry: payload.entry ?? null,
  }
}

function openAcceptance(row: Row) {
  acceptForm.id = Number(row.id)
  acceptForm.修复单号 = String(row['修复单号'] ?? '')
  acceptForm.currentStatus = String(row.status ?? row['修复状态'] ?? '')
  // 优先带出已保存过的内容：即便上次提示失败，完成日期与监理人员也不会丢。
  acceptForm.完成日期 = String(row['完成日期'] ?? '')
  acceptForm.监理人员 = String(row['监理人员'] ?? '')
  acceptError.value = ''
  acceptVisible.value = true
}

function closeAccept() {
  if (acceptLoading.value) {
    return
  }
  acceptVisible.value = false
}

async function submitAcceptance() {
  acceptError.value = ''
  if (!acceptForm.完成日期 || !acceptForm.监理人员.trim()) {
    acceptError.value = '请先填写完成日期与监理人员后再提交'
    return
  }
  acceptLoading.value = true
  try {
    const response = await request(`${ENDPOINT}/${acceptForm.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          action: '提交验收',
          完成日期: acceptForm.完成日期,
          监理人员: acceptForm.监理人员.trim(),
        },
      }),
    })
    const result = await readActionResult(response)
    if (!result.ok) {
      // 业务校验未过或服务端判定不能提交：弹窗保留，已填内容原样保留，允许继续重试。
      acceptError.value = result.message || '提交验收未生效，请检查后重试'
      return
    }
    acceptVisible.value = false
    successMessage.value = result.message || '修复单已提交验收'
    if (detailVisible.value && detail.value?.id === result.entry?.id) {
      detail.value = result.entry
    }
    await reload()
  } catch (error) {
    // 网络中断等传输层失败：数据可能已在服务端生效，弹窗不关闭，用户可直接重试，
    // 服务端按幂等处理，重试成功即说明已生效，不会产生重复验收记录。
    acceptError.value = `${
      error instanceof Error ? error.message : '提交验收失败'
    }（本次填写内容已保留，可直接点击重试；服务端不会重复建立验收记录）`
  } finally {
    acceptLoading.value = false
  }
}

async function openDetail(row: Row) {
  detailVisible.value = true
  detail.value = null
  detailError.value = ''
  await fetchDetail(Number(row.id))
}

function closeDetail() {
  if (detailLoading.value) {
    return
  }
  detailVisible.value = false
  detail.value = null
  detailError.value = ''
}

async function fetchDetail(entryId: number) {
  detailError.value = ''
  detailLoading.value = true
  try {
    const response = await request(`${ENDPOINT}/${entryId}`)
    if (!response.ok) {
      let detail = `修复单 ${entryId} 详情读取失败`
      try {
        const payload = await response.json()
        if (payload?.detail) {
          detail = String(payload.detail)
        }
      } catch {
        // 响应体不是 JSON 时沿用兜底提示。
      }
      throw new Error(detail)
    }
    detail.value = (await response.json()) as Row
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : `修复单 ${entryId} 详情读取失败`
  } finally {
    detailLoading.value = false
  }
}

async function runSimpleAction(action: string, row: Row): Promise<boolean> {
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = await readActionResult(response)
    if (!result.ok) {
      errorMessage.value = result.message || `${action}未生效，请稍后重试`
      return false
    }
    successMessage.value = result.message || `修复单已${action}`
    return true
  } catch (error) {
    errorMessage.value = `${
      error instanceof Error ? error.message : `${action}失败`
    }（如已生效请刷新列表确认，可安全重试，不会重复记录）`
    return false
  }
}

async function dispatchAction(action: string, row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  if (action === '提交验收') {
    // 从列表或详情发起都走同一个弹窗，保证已填内容可复用、可重试。
    if (!acceptVisible.value) {
      openAcceptance(row)
    }
    return
  }
  const ok = await runSimpleAction(action, row)
  if (ok) {
    if (detailVisible.value && detail.value?.id === row.id) {
      await fetchDetail(Number(row.id))
    }
    await reload()
  }
}

onMounted(reload)
</script>
