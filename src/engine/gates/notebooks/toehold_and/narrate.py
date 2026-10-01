"""Progress bars, running commentary and closing findings for the long-running drivers.

A sweep that prints nothing for forty minutes and then a file path is impossible to trust:
there is no way to tell a slow run from a stuck one, no way to abandon a run that is clearly
going nowhere, and no way to see a result forming before it is over. These helpers exist so
every driver in this directory can say what it is doing, how far through it is, what it has
found so far, and what the numbers mean at the end.

Three pieces, deliberately small:

``banner``
    What is about to happen and how big it is, **including an up-front time estimate**, so a
    run can be abandoned before it starts rather than after.
``Progress``
    A bar with elapsed time, rate and ETA, throttled so it never becomes the bottleneck, plus
    an optional ``note`` carried on the same line for the item in flight.
``conclude``
    The closing summary. **Findings, not file paths** — a driver that ends with "12,960 rows
    written" has told the reader nothing about what it learned.

Everything writes to stdout and flushes, because these run under ``nohup`` as often as
interactively and a buffered progress bar is no progress bar at all.
"""

import sys
import time


def _clock(seconds: float) -> str:
    """``2.1s``, ``4m 12s`` or ``1h 03m`` — whichever reads best at that magnitude."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60):02d}s"
    return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60):02d}m"


def banner(title: str, lines: list[str] = (), estimate: float | None = None) -> None:
    """Announce a run: what, how much, and how long it is expected to take."""
    rule = "=" * max(len(title) + 4, 64)
    print(f"\n{rule}\n  {title}\n{rule}")
    for line in lines:
        print(f"  {line}")
    if estimate is not None:
        print(
            f"  estimated {_clock(estimate)}"
            + ("  — abandon now if that is too long" if estimate > 300 else "")
        )
    print(flush=True)


class Progress:
    """A throttled progress bar that reports rate and ETA, not just a count.

    Args:
        total: How many items. ``0`` means unknown, and the bar degrades to a counter.
        label: What the items are, e.g. ``"designs"``.
        every: Minimum seconds between redraws. The bar must never cost meaningful time
            relative to the work it is measuring.
    """

    def __init__(self, total: int, label: str = "items", every: float = 0.5) -> None:
        self.total = total
        self.label = label
        self.every = every
        self.started = time.perf_counter()
        self._last = 0.0
        self.done = 0

    def step(self, note: str = "", count: int = 1) -> None:
        self.done += count
        now = time.perf_counter()
        if now - self._last < self.every and self.done != self.total:
            return
        self._last = now
        elapsed = now - self.started
        rate = self.done / elapsed if elapsed > 0 else 0.0
        if self.total:
            fraction = self.done / self.total
            filled = int(28 * fraction)
            bar = "#" * filled + "." * (28 - filled)
            remaining = (self.total - self.done) / rate if rate > 0 else 0.0
            line = (
                f"\r  [{bar}] {100 * fraction:5.1f}%  {self.done}/{self.total} {self.label}"
                f"  {_clock(elapsed)} elapsed, {_clock(remaining)} left  {rate:.1f}/s"
            )
        else:
            line = f"\r  {self.done} {self.label}  {_clock(elapsed)}  {rate:.1f}/s"
        if note:
            line += f"  | {note}"
        sys.stdout.write(line[:150].ljust(150))
        sys.stdout.flush()

    def finish(self, note: str = "") -> None:
        elapsed = time.perf_counter() - self.started
        sys.stdout.write("\r" + " " * 150 + "\r")
        rate = self.done / elapsed if elapsed > 0 else 0.0
        print(
            f"  done: {self.done} {self.label} in {_clock(elapsed)} ({rate:.1f}/s){note}",
            flush=True,
        )


def interim(title: str, facts: list[tuple[str, str]]) -> None:
    """A mid-run reading, so a result can be seen forming rather than only at the end."""
    sys.stdout.write("\r" + " " * 150 + "\r")
    print(f"\n  --- {title} ---")
    for name, value in facts:
        print(f"      {name:<34}{value}")
    print(flush=True)


def conclude(findings: list[str], wrote: list[str] = ()) -> None:
    """Close with what was learned. File paths come last, and only as a footnote."""
    print("\n" + "=" * 64)
    print("  WHAT THIS RUN FOUND")
    print("=" * 64)
    for finding in findings:
        for index, chunk in enumerate(_wrap(finding, 76)):
            print(f"  {'* ' if index == 0 else '  '}{chunk}")
    if wrote:
        print("\n  written:")
        for path in wrote:
            print(f"    {path}")
    print(flush=True)


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width and current:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines
