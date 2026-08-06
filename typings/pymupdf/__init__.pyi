from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Literal, Self

class FileDataError(Exception): ...

class Matrix:
    def __init__(self, zoom_x: float, zoom_y: float) -> None: ...

class Pixmap:
    def tobytes(self, output: Literal["png"]) -> bytes: ...

class Page:
    def get_pixmap(self, *, matrix: Matrix, alpha: bool) -> Pixmap: ...

class Document:
    page_count: int
    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    def __iter__(self) -> Iterator[Page]: ...

def open(filename: str | Path) -> Document: ...
