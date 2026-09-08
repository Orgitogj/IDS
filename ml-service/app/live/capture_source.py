import csv
import io
import time
from pathlib import Path


class CaptureError(RuntimeError):
    pass


class CsvFlowSource:
    def __init__(self, path, encoding="utf-8"):
        self.path = Path(path)
        self.encoding = encoding
        self.header = None
        self._offset = 0
        self._pending = ""
        self.rows_yielded = 0
        self.rows_emitted = 0
        self.malformed_lines = 0

    def exists(self):
        return self.path.exists()

    def _split_complete_lines(self, text):
        if "\n" not in text:
            return [], text
        parts = text.split("\n")
        return parts[:-1], parts[-1]

    def _parse(self, line):
        if not line.strip():
            return None
        try:
            values = next(csv.reader(io.StringIO(line)))
        except (csv.Error, StopIteration):
            self.malformed_lines += 1
            return None
        if len(values) != len(self.header):
            self.malformed_lines += 1
            return None
        return dict(zip(self.header, values))

    def read_new(self):
        if not self.path.exists():
            return []

        with open(self.path, "r", encoding=self.encoding, errors="replace",
                  newline="") as handle:
            handle.seek(self._offset)
            chunk = handle.read()
            self._offset = handle.tell()

        if not chunk:
            return []

        lines, self._pending = self._split_complete_lines(self._pending + chunk)
        rows = []

        for line in lines:
            line = line.rstrip("\r")
            if self.header is None:
                if not line.strip():
                    continue
                self.header = next(csv.reader(io.StringIO(line)))
                continue
            row = self._parse(line)
            if row is not None:
                rows.append(row)
                self.rows_yielded += 1

        return rows

    def read_all(self):
        collected = []
        while True:
            rows = self.read_new()
            if not rows:
                break
            collected.extend(rows)
        return collected

    def follow(self, poll_interval=2.0, duration_seconds=None, max_rows=None,
               stop_predicate=None, idle_timeout=None):
        started = time.monotonic()
        last_row_at = started

        while True:
            rows = self.read_new()
            if rows:
                last_row_at = time.monotonic()
            for row in rows:
                yield row
                self.rows_emitted += 1
                if max_rows is not None and self.rows_emitted >= max_rows:
                    return

            if stop_predicate is not None and stop_predicate():
                return
            if duration_seconds is not None and \
                    time.monotonic() - started >= duration_seconds:
                return
            if idle_timeout is not None and \
                    time.monotonic() - last_row_at >= idle_timeout:
                return

            time.sleep(poll_interval)


def column_report(path, encoding="utf-8"):
    source = CsvFlowSource(path, encoding=encoding)
    rows = source.read_all()
    if source.header is None:
        raise CaptureError(f"asnje header nuk u lexua nga {path}")

    duplicates = sorted({name for name in source.header
                         if source.header.count(name) > 1})

    return {
        "path": str(path),
        "row_count": len(rows),
        "column_count": len(source.header),
        "columns": list(source.header),
        "duplicate_columns": duplicates,
        "malformed_lines": source.malformed_lines,
        "rows": rows,
    }
