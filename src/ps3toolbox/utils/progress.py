"""Progress reporting utilities."""

from typing import Protocol
from rich.progress import Progress, TaskID


class ProgressCallback(Protocol):
    """Protocol for progress callback functions."""
    def __call__(self, current: int, total: int) -> None: ...


class ConsoleProgress:
    """Console progress bar using rich."""

    def __init__(self, description: str):
        self.description = description
        self.progress: Progress | None = None
        self.task_id: TaskID | None = None

    def start(self, total: int) -> None:
        """Start progress tracking."""
        self.progress = Progress()
        self.progress.start()
        self.task_id = self.progress.add_task(self.description, total=total)

    def update(self, current: int, total: int) -> None:
        """Update progress to current position."""
        if self.progress and self.task_id is not None:
            self.progress.update(self.task_id, completed=current)

    def finish(self) -> None:
        """Finish and close progress bar."""
        if self.progress:
            self.progress.stop()
            self.progress = None
            self.task_id = None
