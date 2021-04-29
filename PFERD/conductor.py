import asyncio
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator, List, Optional

import rich
from rich.progress import Progress, TaskID


class ProgressBar:
    def __init__(self, progress: Progress, taskid: TaskID):
        self._progress = progress
        self._taskid = taskid

    def advance(self, amount: float = 1) -> None:
        self._progress.advance(self._taskid, advance=amount)


class TerminalConductor:
    def __init__(self) -> None:
        self._stopped = False
        self._lock = asyncio.Lock()
        self._progress = Progress()
        self._lines: List[str] = []

    def _start(self) -> None:
        for line in self._lines:
            rich.print(line)
        self._lines = []

        self._progress.start()

    def _stop(self) -> None:
        self._progress.stop()
        self._stopped = True

    async def start(self) -> None:
        async with self._lock:
            self._start()

    async def stop(self) -> None:
        async with self._lock:
            self._stop()

    def print(self, line: str) -> None:
        if self._stopped:
            self._lines.append(line)
        else:
            rich.print(line)

    @asynccontextmanager
    async def exclusive_output(self) -> AsyncIterator[None]:
        async with self._lock:
            self.stop()
            try:
                yield
            finally:
                self.start()

    @contextmanager
    def progress_bar(
            self,
            description: str,
            total: Optional[float] = None,
    ) -> Iterator[ProgressBar]:
        if total is None:
            # Indeterminate progress bar
            taskid = self._progress.add_task(description, start=False)
        else:
            taskid = self._progress.add_task(description, total=total)

        bar = ProgressBar(self._progress, taskid)
        try:
            yield bar
        finally:
            self._progress.remove_task(taskid)
