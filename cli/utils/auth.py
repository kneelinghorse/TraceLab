"""Authentication and token management for TraceLab CLI."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


class TokenManager:
    """Manages JWT token storage in ~/.tracelab/token."""

    def __init__(self, token_dir: Optional[Path] = None):
        self.token_dir = token_dir or Path.home() / ".tracelab"
        self.token_file = self.token_dir / "token"

    def ensure_token_dir(self) -> None:
        """Create token directory if it doesn't exist."""
        self.token_dir.mkdir(parents=True, exist_ok=True)
        self.token_dir.chmod(0o700)  # Owner read/write/execute only

    def save_token(
        self,
        access_token: str,
        token_type: str = "bearer",
        expires_in: Optional[int] = None,
    ) -> None:
        """Save token to disk."""
        self.ensure_token_dir()

        # Calculate expiration time
        expires_at = None
        if expires_in:
            expires_at = datetime.now(timezone.utc).timestamp() + expires_in

        token_data = {
            "access_token": access_token,
            "token_type": token_type,
            "expires_at": expires_at,
        }

        with open(self.token_file, "w") as f:
            json.dump(token_data, f, indent=2)

        self.token_file.chmod(0o600)  # Owner read/write only

    def load_token(self) -> Optional[Dict[str, any]]:
        """Load token from disk."""
        if not self.token_file.exists():
            return None

        try:
            with open(self.token_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def get_token(self) -> Optional[str]:
        """Get valid access token, or None if expired/missing."""
        token_data = self.load_token()
        if not token_data:
            return None

        # Check expiration
        expires_at = token_data.get("expires_at")
        if expires_at:
            now = datetime.now(timezone.utc).timestamp()
            # Token is expired if within 60 seconds of expiration
            if now >= expires_at - 60:
                return None

        return token_data.get("access_token")

    def clear_token(self) -> None:
        """Delete token file."""
        if self.token_file.exists():
            self.token_file.unlink()

    def is_authenticated(self) -> bool:
        """Check if user has a valid token."""
        return self.get_token() is not None
