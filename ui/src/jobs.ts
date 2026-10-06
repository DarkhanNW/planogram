import { api, type Job } from './api'

/** Polls a job until it is done or failed. */
export async function waitForJob(job: Job, onUpdate?: (job: Job) => void): Promise<Job> {
  let current = job
  while (current.status === 'queued' || current.status === 'running') {
    onUpdate?.(current)
    await new Promise((resolve) => setTimeout(resolve, 1000))
    current = await api.get<Job>(`/jobs/${current.id}`)
  }
  onUpdate?.(current)
  return current
}
