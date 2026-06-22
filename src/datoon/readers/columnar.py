"""Columnar format readers: Parquet, ORC, Avro (requires datoon[columnar])."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_INSTALL_HINT = "pip install 'datoon[columnar]'"


def read_parquet(path: Path) -> list[dict[str, Any]]:
    """Read a Parquet file into a list of row dicts."""
    try:
        import pyarrow.parquet as pq  # type: ignore
    except ImportError as exc:
        raise ImportError(
            f"Parquet support requires the 'columnar' extra: {_INSTALL_HINT}"
        ) from exc
    return pq.read_table(path).to_pylist()


def read_orc(path: Path) -> list[dict[str, Any]]:
    """Read an ORC file into a list of row dicts."""
    try:
        import pyarrow.orc as orc  # type: ignore
    except ImportError as exc:
        raise ImportError(
            f"ORC support requires the 'columnar' extra: {_INSTALL_HINT}"
        ) from exc
    return orc.read_table(path).to_pylist()


def read_avro(path: Path) -> list[dict[str, Any]]:
    """Read an Avro file into a list of row dicts."""
    try:
        import fastavro  # type: ignore
    except ImportError as exc:
        raise ImportError(
            f"Avro support requires the 'columnar' extra: {_INSTALL_HINT}"
        ) from exc
    with open(path, "rb") as f:
        return list(fastavro.reader(f))
