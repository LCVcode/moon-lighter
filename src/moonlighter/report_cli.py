"""Thin report command interface; does not launch work or refresh budget."""

from __future__ import annotations

import argparse
from pathlib import Path

from moonlighter.activity_report_view import render_activity_report
from moonlighter.activity_reports import date_range
from moonlighter.history_queries import History, load_history, select_records


class ReportCommandError(ValueError):
    """Invalid report request."""


def configure_report_parser(parser: argparse.ArgumentParser) -> argparse.Action:
    project = parser.add_argument("project", nargs="?", help="Only matching project contributions.")
    ranges = parser.add_mutually_exclusive_group()
    ranges.add_argument("--today", action="store_true", help="Sessions started today (local time).")
    ranges.add_argument(
        "--week", action="store_true", help="Local calendar week, Monday through Sunday."
    )
    ranges.add_argument("--since", help="Inclusive start: YYYY-MM-DD or ISO timestamp.")
    parser.add_argument("--until", help="Exclusive end; use with --since or all history.")
    parser.add_argument("--session", help="Exact session ID shown in --details output.")
    parser.add_argument(
        "--details", action="store_true", help="Show sessions and child work summaries."
    )
    parser.add_argument(
        "--limit", type=int, default=20, help="Detail sessions to show; totals cover all matches."
    )
    parser.add_argument(
        "--all", action="store_true", help="Include routine skips retained in legacy history."
    )
    if not any("--color" in action.option_strings for action in parser._actions):
        parser.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    return project


def handle_report(args: argparse.Namespace, *, state_dir: Path, color: bool) -> int:
    try:
        if args.limit <= 0:
            raise ValueError("--limit must be greater than zero")
        start, end, label = date_range(
            today=args.today, week=args.week, since=args.since, until=args.until
        )
        history = load_history(state_dir)
        records = select_records(
            history.records,
            project=args.project,
            start=start,
            end=end,
            session=args.session,
            include_routine_skips=args.all,
        )
        if args.session is not None and not records:
            raise ValueError("session not found within the selected project/date range")
        print(
            render_activity_report(
                History(records, history.warnings),
                project=args.project,
                label=label,
                details=args.details or args.session is not None,
                limit=args.limit,
                color=color,
            ),
            end="",
        )
        return 0
    except (OSError, ValueError) as exc:
        raise ReportCommandError(str(exc)) from exc
