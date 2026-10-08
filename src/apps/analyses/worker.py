"""Read the queue cluster's short-lived heartbeat."""

from django.utils import timezone
from django_q.conf import Conf
from django_q.status import Stat


def worker_available() -> bool:
    return any(
        stat.status in (Conf.IDLE, Conf.WORKING)
        and stat.workers
        and (timezone.now() - stat.timestamp).total_seconds() < 10
        for stat in Stat.get_all()
    )
