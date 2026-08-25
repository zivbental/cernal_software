"""Background tasks.

Deliberately thin (rule: tasks are shells). The logic lives in
``apps.analyses.services``, so it can be unit-tested without a worker running.

Tasks take **primitive arguments** and re-fetch: a serialised model instance in a queue
is a stale snapshot waiting to happen.
"""

import logging

from apps.analyses.services import execute_run

logger = logging.getLogger(__name__)


def run_analysis(run_id: str) -> None:
    """Execute one analysis run. Queued by ``submit_run``.

    Safe to re-run: ``execute_run`` no-ops on a run that already reached a terminal
    state, so a redelivered task cannot recompute or duplicate results.
    """
    logger.info("Worker picked up run %s", run_id)
    execute_run(run_id)
