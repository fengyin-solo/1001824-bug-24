<template>
  <div v-if="open" class="modal-mask" @click.self="cancel">
    <div class="modal" role="dialog" aria-modal="true" aria-label="提交验收">
      <header class="modal-head">
        <h3>提交验收{{ mode === '覆盖' ? '（更新验收资料）' : '' }}</h3>
        <button class="link" type="button" :disabled="submitting" @click="cancel">关闭</button>
      </header>

      <p class="modal-tip">
        修复单 <strong>{{ row?.修复单号 ?? row?.id }}</strong>
        当前状态：<strong>{{ row?.修复状态 ?? row?.status }}</strong>
      </p>
      <p v-if="mode === '覆盖'" class="modal-tip warn">
        该单已在待验收，本次提交会用新填的资料覆盖原验收记录，一张单始终只保留一条验收记录。
      </p>

      <form class="modal-form" @submit.prevent="submit">
        <label class="form-item">
          <span>完成日期 *</span>
          <input v-model="form.完成日期" type="date" :disabled="submitting" required />
        </label>
        <label class="form-item">
          <span>监理人员 *</span>
          <input
            v-model="form.监理人员"
            type="text"
            placeholder="请输入监理人员姓名"
            :disabled="submitting"
            required
          />
        </label>
        <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
        <footer class="modal-foot">
          <button class="btn" type="button" :disabled="submitting" @click="cancel">取消</button>
          <button class="btn primary" type="submit" :disabled="submitting">
            {{ submitting ? '提交中…' : mode === '覆盖' ? '覆盖并重新提交' : '提交验收' }}
          </button>
        </footer>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'

import { NetworkError, runRepairAction, type RepairRow } from './api'

const props = defineProps<{
  open: boolean
  row: RepairRow | null
  /** 施工中=首次提交；待验收=网络中断/资料有误后的覆盖重提 */
  mode: '首次' | '覆盖'
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'done', entry: RepairRow, message: string): void
}>()

const form = reactive({ 完成日期: '', 监理人员: '' })
const submitting = ref(false)
const errorMessage = ref('')

// 打开弹窗时回填该单已有的验收资料：网络中断重试或补录都不用重新填。
watch(
  () => props.open,
  (open) => {
    if (!open) return
    errorMessage.value = ''
    const acceptance = props.row?.acceptance
    form.完成日期 = String(props.row?.完成日期 ?? acceptance?.完成日期 ?? '')
    form.监理人员 = String(props.row?.监理人员 ?? acceptance?.监理人员 ?? '')
  },
)

async function submit() {
  if (!props.row || submitting.value) return
  if (!form.完成日期 || !form.监理人员.trim()) {
    errorMessage.value = '请补全完成日期与监理人员后再提交'
    return
  }
  submitting.value = true
  errorMessage.value = ''
  try {
    const result = await runRepairAction(
      props.row.id,
      '提交验收',
      { 完成日期: form.完成日期, 监理人员: form.监理人员.trim() },
    )
    if (!result.ok || !result.entry) {
      // 业务校验未过（如日期格式被后端拒绝）：表单保留，允许修改后重试
      errorMessage.value = result.message
      return
    }
    emit('done', result.entry, result.message)
  } catch (error) {
    // 断网/响应丢失：不关弹窗、不清表单，用户可原地重试
    errorMessage.value = error instanceof NetworkError ? error.message : '提交失败，请保留资料后重试'
  } finally {
    submitting.value = false
  }
}

function cancel() {
  if (submitting.value) return
  emit('close')
}
</script>
