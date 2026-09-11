import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { JobInfo } from '../types'

/** 跟踪一个后台任务：start(jobId) 后 1s 轮询，终态（done/failed）自动停并回调。

 * 典型用法：提交接口拿到 job_id → start(id) → 组件读 job 渲染进度条；
 * onSettled 里做收尾（失效列表缓存、展示结果/错误）。 */
export function useJob(onSettled?: (job: JobInfo) => void) {
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState<number | null>(null)
  const settledRef = useRef(onSettled)
  settledRef.current = onSettled

  const query = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => api.getJob(jobId as number),
    enabled: jobId != null,
    refetchInterval: 1000,
  })
  const job = query.data ?? null

  useEffect(() => {
    if (job && job.status !== 'running') {
      settledRef.current?.(job)
      queryClient.removeQueries({ queryKey: ['job', jobId] })
      setJobId(null)
    }
  }, [job, jobId, queryClient])

  return { job, start: setJobId, tracking: jobId != null }
}
