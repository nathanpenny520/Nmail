// ExtApiSection 组件测试（审计 B1 首批：对外 API 密钥管理面）
// 覆盖：明文默认遮蔽 / 眼睛显隐 / 吊销确认 / 重置 / 创建 payload / 总开关
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

import ExtApiSection from './ExtApiSection'
import { api } from '../api/client'
import type { ExtKeysResp } from '../types'

vi.mock('../api/client', () => ({
  api: {
    getExtKeys: vi.fn(),
    getExtApiCalls: vi.fn(),
    createExtKey: vi.fn(),
    updateExtKey: vi.fn(),
    revokeExtKey: vi.fn(),
    setExtApiEnabled: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api, true)

const PLAINTEXT = 'nmail_abcdef1234567890XYZ'

function keysResp(): ExtKeysResp {
  return {
    enabled: true,
    log_enabled: true,
    rate_limit_per_min: 60,
    base_url: 'http://127.0.0.1:8720/api/ext/v1',
    keys: [
      {
        id: 1, name: 'iOS 快捷指令', key: PLAINTEXT, scopes: ['read', 'write'],
        daily_limit: 100, last_used_at: '2026-09-15T10:00:00', revoked: false,
        created_at: '2026-09-14T10:00:00',
      },
      {
        id: 2, name: '旧脚本', scopes: ['read'], daily_limit: null,
        last_used_at: null, revoked: true, created_at: '2026-09-01T10:00:00',
      },
    ],
  }
}

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ExtApiSection />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.getExtKeys.mockResolvedValue(keysResp())
  mockedApi.getExtApiCalls.mockResolvedValue({ calls: [] })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('ExtApiSection 密钥遮蔽与显隐', () => {
  it('默认遮蔽：完整明文不出现在 DOM', async () => {
    renderSection()
    await screen.findByText('iOS 快捷指令')
    expect(screen.queryByText(PLAINTEXT)).not.toBeInTheDocument()
    expect(screen.getByText(`${PLAINTEXT.slice(0, 10)}••••••••`)).toBeInTheDocument()
  })

  it('眼睛按钮显示完整密钥，再点隐藏', async () => {
    const user = userEvent.setup()
    renderSection()
    const eye = await screen.findByTitle('显示完整密钥')
    expect(screen.getAllByTitle('显示完整密钥')).toHaveLength(1) // 已吊销行无明文，不显示
    await user.click(eye)
    expect(screen.getByText(PLAINTEXT)).toBeInTheDocument()
    await user.click(screen.getByTitle('隐藏'))
    expect(screen.queryByText(PLAINTEXT)).not.toBeInTheDocument()
  })

  it('已吊销行不回显明文，只提供彻底删除', async () => {
    renderSection()
    await screen.findByText('旧脚本')
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByTitle('彻底删除记录')).toBeInTheDocument()
    expect(screen.queryByTitle('显示完整密钥')).not.toBeNull() // 仅活跃行有（上面已断言 1 个）
  })
})

describe('ExtApiSection 危险操作确认', () => {
  it('确认后吊销：revokeExtKey(id)', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderSection()
    await user.click(await screen.findByTitle('吊销'))
    await waitFor(() => expect(mockedApi.revokeExtKey).toHaveBeenCalledWith(1))
  })

  it('取消确认则不吊销', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderSection()
    await user.click(await screen.findByTitle('吊销'))
    await waitFor(() => expect(mockedApi.revokeExtKey).not.toHaveBeenCalled())
  })

  it('重置：updateExtKey(id, { reset: true })', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderSection()
    await user.click(await screen.findByTitle('重置（旧密钥立即失效）'))
    await waitFor(() => expect(mockedApi.updateExtKey).toHaveBeenCalledWith(1, { reset: true }))
  })
})

describe('ExtApiSection 创建与总开关', () => {
  it('创建 payload：trimmed 备注名 + 默认 read scope + 空上限=null', async () => {
    const user = userEvent.setup()
    renderSection()
    await user.click(await screen.findByRole('button', { name: '生成密钥' }))
    await user.type(screen.getByPlaceholderText('备注名（如：iOS 快捷指令）'), ' 快捷指令 ')
    await user.click(screen.getByRole('button', { name: '生成' }))
    await waitFor(() =>
      expect(mockedApi.createExtKey).toHaveBeenCalledWith({
        name: '快捷指令', scopes: ['read'], daily_limit: null,
      }),
    )
  })

  it('总开关切换：setExtApiEnabled(新状态)；不携带日志开关字段（后端保持原值）', async () => {
    const user = userEvent.setup()
    renderSection()
    const toggle = await screen.findByRole('checkbox', { name: /启用对外 API/ })
    await user.click(toggle)
    await waitFor(() => expect(mockedApi.setExtApiEnabled).toHaveBeenCalledWith(false, undefined))
  })
})
