"""Background jobs for Extraction and Compliance Checks. Submitting records a queued Job and
hands its work to a runner; tests use the inline runner so jobs finish before the response."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Protocol

from planogram.models import Job, JobKind, JobStatus
from planogram.repository import Repository, new_id

log = logging.getLogger(__name__)


class JobRunner(Protocol):
    def submit(self, work: Callable[[], None]) -> None: ...
    def shutdown(self) -> None: ...


class InlineJobRunner:
    def submit(self, work: Callable[[], None]) -> None:
        work()

    def shutdown(self) -> None:
        pass


class ThreadJobRunner:
    """Runs jobs one at a time off the request thread; recognition is CPU/GPU-bound anyway."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="planogram-job")

    def submit(self, work: Callable[[], None]) -> None:
        self._executor.submit(work)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)


def start_job(
    repo: Repository, runner: JobRunner, job: Job, work: Callable[[], str]
) -> Job:
    """Records ``job`` as queued and runs ``work``, which returns the id of the job's result."""
    repo.save_job(job)

    def run() -> None:
        repo.save_job(job.model_copy(update={"status": JobStatus.RUNNING}))
        try:
            result_id = work()
        except Exception as e:  # a failed job is reported through its status, not raised
            log.exception("Job %s failed", job.id)
            repo.save_job(job.model_copy(update={"status": JobStatus.FAILED, "error": f"{type(e).__name__}: {e}"}))
        else:
            repo.save_job(job.model_copy(update={"status": JobStatus.DONE, "result_id": result_id}))

    runner.submit(run)
    return repo.get_job(job.id) or job


def new_job(kind: JobKind, shelf_photo_id: str, submitted_by: str, submitted_at: datetime) -> Job:
    return Job(
        id=new_id(), kind=kind, status=JobStatus.QUEUED, shelf_photo_id=shelf_photo_id,
        submitted_by=submitted_by, submitted_at=submitted_at,
    )
