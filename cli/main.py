#!/usr/bin/env python3
"""TraceLab CLI - Main entry point."""

import sys
from pathlib import Path

import click

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli import __version__
from cli.commands import auth, config, documents, missions, projects, search
from cli.utils.errors import CLIError, format_error_human, format_error_json
from cli.utils.output import OutputFormatter


class Context:
    """CLI context object passed to all commands."""

    def __init__(self):
        self.output: OutputFormatter = None
        self.json_mode: bool = False
        self.quiet: bool = False
        self.verbose: bool = False
        self.api_url: str = None
        self.token: str = None


pass_context = click.make_pass_decorator(Context, ensure=True)


@click.group()
@click.option("--json", "json_mode", is_flag=True, help="Output in JSON format")
@click.option("--quiet", "-q", is_flag=True, help="Suppress non-essential output")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--api-url", help="Override API base URL")
@click.option("--token", help="Override stored authentication token")
@click.option("--no-color", is_flag=True, help="Disable color output")
@click.version_option(version=__version__, prog_name="tracelab")
@pass_context
def cli(ctx, json_mode, quiet, verbose, api_url, token, no_color):
    """TraceLab CLI - Agent-first interface for TraceLab research repository."""
    ctx.json_mode = json_mode
    ctx.quiet = quiet
    ctx.verbose = verbose
    ctx.api_url = api_url
    ctx.token = token
    ctx.output = OutputFormatter(json_mode=json_mode, quiet=quiet, no_color=no_color)


# Register command groups
cli.add_command(auth.auth)
cli.add_command(projects.projects)
cli.add_command(documents.documents)
cli.add_command(search.search)
cli.add_command(search.rag)
cli.add_command(missions.missions)
cli.add_command(config.config_cmd)


@cli.command(name="version")
@pass_context
def version_cmd(ctx):
    """Show version information."""
    if ctx.json_mode:
        ctx.output.print_data({"version": __version__})
    else:
        ctx.output.info(f"TraceLab CLI version {__version__}")


@cli.command(name="health")
@click.option("--full", is_flag=True, help="Show full health check")
@pass_context
def health(ctx, full):
    """Check API health status."""
    from cli.utils.api import APIClient

    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)
        path = "/api/v1/health/db" if full else "/api/v1/health"
        response = client.get(path)

        if ctx.json_mode:
            ctx.output.print_data(response)
        else:
            status = response.get("status", "unknown")
            if status == "healthy" or status == "ok":
                ctx.output.success(f"API is healthy: {response}")
            else:
                ctx.output.error(f"API health check failed: {response}")
                sys.exit(1)

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


def main():
    """Main entry point with error handling."""
    try:
        cli(obj=Context())
    except CLIError as e:
        # Errors are already handled in command functions
        sys.exit(e.exit_code)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
