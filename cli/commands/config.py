"""Configuration management commands."""

import sys

import click

from cli.utils.config import ConfigManager
from cli.utils.errors import CLIError, format_error_human, format_error_json


@click.group(name="config")
def config_cmd():
    """Manage CLI configuration."""
    pass


@config_cmd.command()
@click.pass_obj
def show(ctx):
    """Show current configuration."""
    try:
        config_mgr = ConfigManager()
        config = config_mgr.config

        if ctx.json_mode:
            ctx.output.print_data(config)
        else:
            ctx.output.info("Current configuration:")
            ctx.output.print_data(config)

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@config_cmd.command()
@click.argument("key")
@click.argument("value")
@click.pass_obj
def set(ctx, key, value):
    """Set a configuration value."""
    try:
        config_mgr = ConfigManager()

        # Try to parse value as JSON for complex types
        import json
        try:
            value = json.loads(value)
        except:
            pass  # Keep as string

        config_mgr.set(key, value)

        if ctx.json_mode:
            ctx.output.success("Configuration updated", data={"key": key, "value": value})
        else:
            ctx.output.success(f"Set {key} = {value}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@config_cmd.command()
@click.argument("key")
@click.pass_obj
def get(ctx, key):
    """Get a configuration value."""
    try:
        config_mgr = ConfigManager()
        value = config_mgr.get(key)

        if value is None:
            if ctx.json_mode:
                ctx.output.print_data({"key": key, "value": None})
            else:
                ctx.output.info(f"{key} is not set")
        else:
            if ctx.json_mode:
                ctx.output.print_data({"key": key, "value": value})
            else:
                ctx.output.info(f"{key} = {value}")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@config_cmd.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def reset(ctx, confirm):
    """Reset configuration to defaults."""
    try:
        if not confirm and not ctx.json_mode:
            click.confirm("Are you sure you want to reset configuration?", abort=True)

        config_mgr = ConfigManager()
        config_mgr.reset()

        if ctx.json_mode:
            ctx.output.success("Configuration reset", data=config_mgr.config)
        else:
            ctx.output.success("Configuration reset to defaults")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)

