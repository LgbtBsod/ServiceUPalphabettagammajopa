#!/usr/bin/env python3

"""Regression test for core/logging/logger.py::ColoredFormatter — live run
of main.py (after wiring setup_logging() to a real file, see
tests/test_config_log_paths.py) showed raw ANSI escape codes baked into
serviceup.log for roughly half the lines. Root cause: the same LogRecord
instance is delivered to every handler attached to a logger AND its
ancestors (root included, since Logger.propagate defaults to True).
ColoredFormatter.format() used to write the ANSI-wrapped levelname
directly onto record.levelname with no rollback, so any handler that
processed the record AFTER the colored console handler (e.g. the file
handler added by setup_logging()) saw the already-corrupted value instead
of the plain "INFO"/"ERROR" text — defeating the point of a clean,
greppable log file."""

from __future__ import annotations

import logging

from core.logging.logger import ColoredFormatter


def _make_record(level: int = logging.INFO, msg: str = "hello") -> logging.LogRecord:
    return logging.LogRecord(
        name="test", level=level, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )


class TestColoredFormatterDoesNotLeakIntoOtherHandlers:
    def test_a_plain_formatter_processing_the_same_record_afterward_sees_clean_levelname(self):
        """Simulates two handlers on the same logger (e.g. a colored
        console handler and a plain file handler) both receiving the same
        LogRecord, colored one first - matches real logging dispatch
        order."""
        record = _make_record()
        colored = ColoredFormatter("%(levelname)s | %(message)s")
        plain = logging.Formatter("%(levelname)s | %(message)s")

        colored_output = colored.format(record)
        plain_output = plain.format(record)

        assert "\033[" in colored_output  # sanity: color really was applied
        assert "\033[" not in plain_output
        assert plain_output == "INFO | hello"

    def test_record_levelname_is_restored_after_formatting(self):
        record = _make_record()
        ColoredFormatter("%(levelname)s").format(record)
        assert record.levelname == "INFO"

    def test_formatting_the_same_record_twice_does_not_double_wrap(self):
        record = _make_record()
        fmt = ColoredFormatter("%(levelname)s")
        first = fmt.format(record)
        second = fmt.format(record)
        assert first == second
