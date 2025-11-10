"""Output formatting for TraceLab CLI."""

import json
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .config import ConfigManager


class OutputFormatter:
    """Formats CLI output for human or JSON modes."""

    def __init__(self, json_mode: bool = False, quiet: bool = False, no_color: bool = False):
        self.json_mode = json_mode
        self.quiet = quiet
        self.config = ConfigManager()

        # Use colors unless explicitly disabled or in JSON mode
        use_color = not no_color and not json_mode and self.config.get("preferences.color", True)
        self.console = Console(color_system="auto" if use_color else None)

    def success(self, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Print success message."""
        if self.json_mode:
            self._print_json_success(data or {}, message)
        else:
            if not self.quiet:
                self.console.print(f"✓ {message}", style="green")

    def error(self, message: str, details: Optional[Dict[str, Any]] = None, code: str = "ERROR") -> None:
        """Print error message."""
        if self.json_mode:
            self._print_json_error(message, code, details)
        else:
            self.console.print(f"✗ Error: {message}", style="red", file=sys.stderr)
            if details:
                if "reason" in details:
                    self.console.print(f"  Reason: {details['reason']}", file=sys.stderr)
                if "suggestion" in details:
                    self.console.print(f"  Suggestion: {details['suggestion']}", file=sys.stderr)

    def info(self, message: str) -> None:
        """Print info message."""
        if not self.json_mode and not self.quiet:
            self.console.print(message)

    def print_data(self, data: Any, title: Optional[str] = None) -> None:
        """Print data (object, list, or primitive)."""
        if self.json_mode:
            self._print_json_success(data)
        else:
            if title:
                self.console.print(f"\n[bold]{title}[/bold]")

            if isinstance(data, dict):
                self._print_dict(data)
            elif isinstance(data, list):
                self._print_list(data)
            else:
                self.console.print(data)

    def print_table(self, data: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> None:
        """Print data as a table."""
        if self.json_mode:
            self._print_json_success(data)
        elif not data:
            self.info("No results found")
        else:
            # Auto-detect columns if not provided
            if not columns:
                columns = list(data[0].keys())

            table = Table(show_header=True, header_style="bold")
            for col in columns:
                table.add_column(col.replace("_", " ").title())

            for row in data:
                table.add_row(*[str(row.get(col, "")) for col in columns])

            self.console.print(table)

    def _print_dict(self, data: Dict[str, Any], indent: int = 0) -> None:
        """Print dictionary with nice formatting."""
        prefix = "  " * indent
        for key, value in data.items():
            if isinstance(value, dict):
                self.console.print(f"{prefix}[bold]{key}:[/bold]")
                self._print_dict(value, indent + 1)
            elif isinstance(value, list):
                self.console.print(f"{prefix}[bold]{key}:[/bold]")
                for item in value:
                    if isinstance(item, dict):
                        self._print_dict(item, indent + 1)
                    else:
                        self.console.print(f"{prefix}  - {item}")
            else:
                self.console.print(f"{prefix}[bold]{key}:[/bold] {value}")

    def _print_list(self, data: List[Any]) -> None:
        """Print list with nice formatting."""
        for item in data:
            if isinstance(item, dict):
                self._print_dict(item)
                self.console.print()  # Blank line between items
            else:
                self.console.print(f"  - {item}")

    def _print_json_success(self, data: Any, message: Optional[str] = None) -> None:
        """Print success response in JSON format."""
        output = {
            "success": True,
            "data": data,
            "meta": {
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        }
        if message:
            output["message"] = message

        print(json.dumps(output, indent=2))

    def _print_json_error(self, message: str, code: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Print error response in JSON format."""
        output = {
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "details": details or {}
            }
        }
        print(json.dumps(output, indent=2), file=sys.stderr)

    @contextmanager
    def progress_spinner(self, message: str):
        """Context manager that renders a spinner with the provided message."""
        if self.json_mode or self.quiet:
            yield None
            return

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True
        ) as progress:
            progress.add_task(description=message, total=None)
            yield progress
