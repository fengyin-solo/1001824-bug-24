/** 修复施工接口封装：动作结果、网络失败与业务失败在这里分清。 */
import { request } from '@/api/client'

export const REPAIR_ENDPOINT = '/api/repair'
export const REPAIR_STATUSES = ['待开工', '施工中', '待验收', '已完工'] as const
export type RepairStatus = (typeof REPAIR_STATUSES)[number]
export type RepairAction = '确认开工' | '提交验收' | '确认完工'

export type RepairRow = Record<string, string | number | null> & {
  id: number
  status?: string
  修复状态?: string
  修复单号?: string
  完成日期?: string
  监理人员?: string
  acceptance?: { 完成日期: string; 监理人员: string; 提交时间: string }
}

export type RepairStats = { 待开工: number; 施工中: number; 本月完工: number }

export type ActionOutcome = {
  ok: boolean
  message: string
  entry: RepairRow | null
  /** true 表示请求根本没送达/响应没收到（如断网），保留表单允许重试 */
  networkFailed: boolean
}

/** 网络中断：与“业务上没生效”区分开，调用方据此保留已填资料并允许重试。 */
export class NetworkError extends Error {}

export async function fetchRepairList(params: {
  keyword?: string
  status?: string
  page?: number
  size?: number
}): Promise<{ items: RepairRow[]; total: number }> {
  const query = new URLSearchParams()
  if (params.keyword) query.set('keyword', params.keyword)
  if (params.status) query.set('status', params.status)
  if (params.page) query.set('page', String(params.page))
  if (params.size) query.set('size', String(params.size))
  const suffix = query.toString()
  let response: Response
  try {
    response = await request(`${REPAIR_ENDPOINT}${suffix ? `?${suffix}` : ''}`)
  } catch (error) {
    throw new NetworkError(error instanceof Error ? error.message : '修复单列表请求未送达')
  }
  if (!response.ok) {
    const detail = await readDetail(response)
    throw new Error(detail || `修复单列表读取失败（HTTP ${response.status}）`)
  }
  return response.json()
}

export async function fetchRepairDetail(id: number): Promise<RepairRow> {
  let response: Response
  try {
    response = await request(`${REPAIR_ENDPOINT}/${id}`)
  } catch (error) {
    throw new NetworkError(error instanceof Error ? error.message : '修复单详情请求未送达')
  }
  if (!response.ok) {
    const detail = await readDetail(response)
    throw new Error(detail || `修复单详情读取失败（HTTP ${response.status}）`)
  }
  return response.json()
}

export async function fetchRepairStats(): Promise<RepairStats> {
  let response: Response
  try {
    response = await request(`${REPAIR_ENDPOINT}/stats`)
  } catch (error) {
    throw new NetworkError(error instanceof Error ? error.message : '统计数据请求未送达')
  }
  if (!response.ok) {
    throw new Error(`概览卡片统计读取失败（HTTP ${response.status}）`)
  }
  return response.json()
}

/**
 * 执行状态动作。提交验收时把完成日期与监理人员随请求带上。
 * 断网/响应丢失会抛 NetworkError——此时服务端是否已生效未知，调用方保留表单让用户重试；
 * 重试是安全的：服务端对「待验收」状态重复提交按覆盖处理，一张单只留一条验收记录。
 */
export async function runRepairAction(
  id: number,
  action: RepairAction,
  accept?: { 完成日期: string; 监理人员: string },
): Promise<ActionOutcome> {
  const values: Record<string, string> = {}
  if (accept) {
    values.完成日期 = accept.完成日期
    values.监理人员 = accept.监理人员
  }
  let response: Response
  try {
    response = await request(`${REPAIR_ENDPOINT}/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action, values }),
    })
  } catch (error) {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new NetworkError(
      `网络中断，无法确认本次提交是否生效；已填写的完成日期与监理人员已保留，可直接重试（不会重复生成验收记录）。原因：${detail}`,
    )
  }
  let payload: { ok?: boolean; message?: string; entry?: RepairRow | null }
  try {
    payload = await response.json()
  } catch {
    throw new NetworkError(
      `服务端响应不完整（HTTP ${response.status}），无法确认提交结果，请直接重试；重试不会重复生成验收记录`,
    )
  }
  return {
    ok: Boolean(payload.ok),
    message: payload.message || (payload.ok ? '操作已生效' : '操作未生效'),
    entry: payload.entry ?? null,
    networkFailed: false,
  }
}

async function readDetail(response: Response): Promise<string> {
  try {
    const data = await response.json()
    if (typeof data?.detail === 'string') return data.detail
  } catch {
    // 非 JSON 错误体时退回通用说明
  }
  return ''
}
