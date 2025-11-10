"""Error handling for TraceLab CLI."""

from typing import Any, Dict, Optional


class CLIError(Exception):
    """Base exception for CLI errors."""

    def __init__(self, message: str, code: str = "CLI_ERROR", details: Optional[Dict[str, Any]] = None, exit_code: int = 1):
        self.message = message
        self.code = code
        self.details = details or {}
        self.exit_code = exit_code
        super().__init__(message)


class AuthenticationError(CLIError):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="AUTHENTICATION_ERROR", details=details, exit_code=3)


class ResourceNotFoundError(CLIError):
    """Resource not found."""

    def __init__(self, resource: str, resource_id: str, details: Optional[Dict[str, Any]] = None):
        message = f"{resource} not found: {resource_id}"
        super().__init__(message, code="RESOURCE_NOT_FOUND", details=details, exit_code=4)


class PermissionDeniedError(CLIError):
    """Permission denied."""

    def __init__(self, message: str = "Permission denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="PERMISSION_DENIED", details=details, exit_code=5)


class APIError(CLIError):
    """API request failed."""

    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        if status_code:
            details["status_code"] = status_code
        super().__init__(message, code="API_ERROR", details=details, exit_code=1)


class ValidationError(CLIError):
    """Input validation failed."""

    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        if field:
            details["field"] = field
        super().__init__(message, code="VALIDATION_ERROR", details=details, exit_code=2)


def format_error_human(error: CLIError) -> str:
    """Format error for human-readable output."""
    lines = [f"✗ Error: {error.message}"]

    if error.details:
        if "reason" in error.details:
            lines.append(f"  Reason: {error.details['reason']}")
        if "suggestion" in error.details:
            lines.append(f"  Suggestion: {error.details['suggestion']}")
        if "status_code" in error.details:
            lines.append(f"  Status Code: {error.details['status_code']}")

    return "\n".join(lines)


def format_error_json(error: CLIError) -> Dict[str, Any]:
    """Format error for JSON output."""
    return {
        "success": False,
        "error": {
            "code": error.code,
            "message": error.message,
            "details": error.details
        }
    }

