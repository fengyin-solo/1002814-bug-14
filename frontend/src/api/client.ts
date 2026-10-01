/** 统一请求封装：拼后端地址、抛网络错误、给页脚留一句可读的说明。 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

// 进行中的 GET 请求按最终 URL 合并：同一查询条件被重复提交时只发一次，多处共用同一份响应
const inflight = new Map<string, Promise<Response>>()

function buildUrl(path: string): string {
  return path.startsWith('http') ? path : `${API_BASE}${path}`
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = buildUrl(path)
  const method = (init?.method ?? 'GET').toUpperCase()

  if (method === 'GET') {
    const pending = inflight.get(url)
    if (pending) {
      // Response 只能消费一次，克隆一份给各调用方独立读取
      return pending.then((response) => response.clone())
    }
  }

  const promise = fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
    .catch((error: unknown) => {
      const detail = error instanceof Error ? error.message : '请求未送达'
      throw new Error(`接口请求失败：${detail}`)
    })

  if (method === 'GET') {
    inflight.set(url, promise)
    void promise.finally(() => inflight.delete(url))
  }
  return promise
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}
