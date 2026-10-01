<template>
  <section class="page" data-module="repair-detail">
    <header class="page-head">
      <div>
        <h2>修复单详情</h2>
        <p class="page-desc">明细、验收资料与状态均取自服务端同一份数据，与列表页保持一致。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/repair">返回列表</RouterLink>
      </div>
    </header>

    <p v-if="loading" class="page-tip">修复单加载中…</p>
    <template v-else-if="entry">
      <article class="detail-card">
        <h3 class="detail-title">
          {{ entry.修复单号 ?? `修复单 #${entry.id}` }}
          <span class="status-tag" :data-status="entry.status">{{ entry.修复状态 ?? entry.status }}</span>
        </h3>
        <dl class="detail-grid">
          <div v-for="field in detailFields" :key="field" class="detail-item">
            <dt>{{ field }}</dt>
            <dd>{{ entry[field] || '—' }}</dd>
          </div>
        </dl>
      </article>

      <article class="detail-card">
        <h3 class="detail-title">验收资料</h3>
        <dl v-if="entry.acceptance" class="detail-grid">
          <div class="detail-item">
            <dt>完成日期</dt>
            <dd>{{ entry.acceptance.完成日期 }}</dd>
          </div>
          <div class="detail-item">
            <dt>监理人员</dt>
            <dd>{{ entry.acceptance.监理人员 }}</dd>
          </div>
          <div class="detail-item">
            <dt>最近提交时间</dt>
            <dd>{{ entry.acceptance.提交时间 }}</dd>
          </div>
        </dl>
        <p v-else class="muted-text">
          尚未提交验收（一张修复单只会保留一条验收记录，提交后可覆盖更新，不会重复堆积）。
        </p>
      </article>

      <div class="detail-actions">
        <button
          v-if="entry.status === '待开工'"
          class="btn primary"
          type="button"
          :disabled="busy"
          @click="runQuick('确认开工')"
        >
          确认开工
        </button>
        <button
          v-if="entry.status === '施工中'"
          class="btn primary"
          type="button"
          :disabled="busy"
          @click="openAccept('首次')"
        >
          提交验收
        </button>
        <template v-if="entry.status === '待验收'">
          <button class="btn primary" type="button" :disabled="busy" @click="runQuick('确认完工')">
            确认完工
          </button>
          <button class="btn" type="button" :disabled="busy" @click="openAccept('覆盖')">
            更新验收资料
          </button>
        </template>
        <p v-if="entry.status === '已完工'" class="muted-text">
          该修复单已完工，流程结束，不能再执行任何状态动作。
        </p>
      </div>

      <footer class="page-foot">
        <span v-if="message" :class="ok ? 'ok-text' : 'error-text'">{{ message }}</span>
      </footer>

      <AcceptDialog
        :open="acceptOpen"
        :row="entry"
        :mode="acceptMode"
        @close="acceptOpen = false"
        @done="onAcceptDone"
      />
    </template>

    <p v-else-if="loadError" class="error-text">{{ loadError }}</p>
    <p v-else class="error-text">修复单不存在或已归档，<RouterLink class="link" to="/repair">返回列表</RouterLink>。</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  NetworkError,
  fetchRepairDetail,
  runRepairAction,
  type RepairAction,
  type RepairRow,
} from './api'
import AcceptDialog from './AcceptDialog.vue'

const route = useRoute()
const entryId = Number(route.params.id)

const entry = ref<RepairRow | null>(null)
const loading = ref(true)
const loadError = ref('')
const busy = ref(false)
const message = ref('')
const ok = ref(false)
const acceptOpen = ref(false)
const acceptMode = ref<'首次' | '覆盖'>('首次')

const detailFields = ['修复单号', '关联缺陷', '修复方式', '承接单位', '开挖范围']

function openAccept(mode: '首次' | '覆盖') {
  message.value = ''
  acceptMode.value = mode
  acceptOpen.value = true
}

async function onAcceptDone(updated: RepairRow, resultMessage: string) {
  acceptOpen.value = false
  entry.value = updated
  message.value = resultMessage
  ok.value = true
}

async function runQuick(action: RepairAction) {
  if (!entry.value || busy.value) return
  busy.value = true
  message.value = ''
  try {
    const result = await runRepairAction(entry.value.id, action)
    message.value = result.message
    ok.value = result.ok
    if (result.entry) entry.value = result.entry
  } catch (error) {
    ok.value = false
    message.value = error instanceof Error ? error.message : '修复施工操作失败，请稍后重试'
  } finally {
    busy.value = false
  }
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    entry.value = await fetchRepairDetail(entryId)
  } catch (error) {
    entry.value = null
    if (error instanceof NetworkError) {
      loadError.value = `详情加载失败：网络中断，无法确认最新状态，请检查网络后重新打开（${error.message}）`
    } else {
      loadError.value = error instanceof Error ? error.message : '修复单详情读取失败'
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
