"""Authentication commands."""

import sys

import click

from cli.utils.api import APIClient
from cli.utils.auth import TokenManager
from cli.utils.errors import CLIError, format_error_human, format_error_json
from cli.utils.output import OutputFormatter


@click.group()
def auth():
    """Manage authentication."""
    pass


@auth.command()
@click.option("--username", prompt=True, help="Username")
@click.option("--password", prompt=True, hide_input=True, help="Password")
@click.pass_obj
def login(ctx, username, password):
    """Login and store authentication token."""
    try:
        client = APIClient(base_url=ctx.api_url)

        with ctx.output.progress_spinner("Authenticating..."):
            token_data = client.login(username, password)

        if ctx.json_mode:
            ctx.output.success("Authenticated successfully", data={"token_type": token_data.get("token_type")})
        else:
            ctx.output.success("Authenticated successfully")
            ctx.output.info(f"Token saved to ~/.tracelab/token")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@auth.command()
@click.pass_obj
def status(ctx):
    """Check authentication status."""
    try:
        token_mgr = TokenManager()

        if token_mgr.is_authenticated():
            token = token_mgr.get_token()
            if ctx.json_mode:
                ctx.output.print_data({"authenticated": True, "has_token": True})
            else:
                ctx.output.success("Authenticated")
                ctx.output.info(f"Token: {token[:20]}...")
        else:
            if ctx.json_mode:
                ctx.output.print_data({"authenticated": False, "has_token": False})
            else:
                ctx.output.error(
                    "Not authenticated",
                    details={"suggestion": "Run 'tracelab auth login' to authenticate"}
                )
                sys.exit(3)

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@auth.command()
@click.pass_obj
def logout(ctx):
    """Logout and remove stored token."""
    try:
        token_mgr = TokenManager()
        token_mgr.clear_token()

        if ctx.json_mode:
            ctx.output.success("Logged out successfully", data={"authenticated": False})
        else:
            ctx.output.success("Logged out successfully")
            ctx.output.info("Token removed from ~/.tracelab/token")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)


@auth.command()
@click.pass_obj
def refresh(ctx):
    """Refresh authentication token."""
    try:
        client = APIClient(base_url=ctx.api_url, token=ctx.token)

        with ctx.output.progress_spinner("Refreshing token..."):
            response = client.post("/api/v1/auth/refresh", data={})

        token_mgr = TokenManager()
        token_mgr.save_token(
            access_token=response["access_token"],
            token_type=response.get("token_type", "bearer"),
            expires_in=response.get("expires_in")
        )

        if ctx.json_mode:
            ctx.output.success("Token refreshed successfully", data={"token_type": response.get("token_type")})
        else:
            ctx.output.success("Token refreshed successfully")

    except CLIError as e:
        if ctx.json_mode:
            print(format_error_json(e), file=sys.stderr)
        else:
            print(format_error_human(e), file=sys.stderr)
        sys.exit(e.exit_code)

