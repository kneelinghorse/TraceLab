"""API client for TraceLab CLI."""

import json
from typing import Any, Dict, Optional

import httpx

from .auth import TokenManager
from .config import ConfigManager
from .errors import APIError, AuthenticationError, PermissionDeniedError, ResourceNotFoundError


class APIClient:
    """HTTP client for TraceLab API."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None, timeout: int = 30):
        self.config = ConfigManager()
        self.token_manager = TokenManager()

        self.base_url = (base_url or self.config.get("api.base_url", "http://localhost:8000")).rstrip("/")
        self.timeout = timeout
        self._token = token

    @property
    def token(self) -> Optional[str]:
        """Get authentication token."""
        if self._token:
            return self._token
        return self.token_manager.get_token()

    @property
    def headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        return headers

    def _handle_response(self, response: httpx.Response) -> Any:
        """Handle API response and errors."""
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code

            # Try to parse error details
            try:
                error_data = e.response.json()
                message = error_data.get("detail", str(e))
            except:
                message = str(e)

            # Map status codes to specific errors
            if status_code == 401:
                raise AuthenticationError(
                    message="Authentication failed",
                    details={
                        "reason": message,
                        "suggestion": "Run 'tracelab auth login' to authenticate"
                    }
                )
            elif status_code == 403:
                raise PermissionDeniedError(
                    message="Permission denied",
                    details={"reason": message}
                )
            elif status_code == 404:
                raise ResourceNotFoundError(
                    resource="Resource",
                    resource_id="unknown",
                    details={"reason": message}
                )
            else:
                raise APIError(message=message, status_code=status_code)

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Make GET request."""
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=self.headers, params=params)
            return self._handle_response(response)

    def get_binary(self, path: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """Make GET request that returns the raw response (for file downloads)."""
        url = f"{self.base_url}{path}"
        headers = dict(self.headers)
        headers["Accept"] = "*/*"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response

    def post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Make POST request."""
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            if files:
                # For file uploads, don't set Content-Type (let httpx handle it)
                headers = {k: v for k, v in self.headers.items() if k != "Content-Type"}
                response = client.post(url, headers=headers, data=data, files=files, params=params)
            else:
                response = client.post(url, headers=self.headers, json=data, params=params)
            return self._handle_response(response)

    def put(self, path: str, data: Dict[str, Any], params: Optional[Dict[str, Any]] = None) -> Any:
        """Make PUT request."""
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.put(url, headers=self.headers, json=data, params=params)
            return self._handle_response(response)

    def delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """Make DELETE request."""
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.delete(url, headers=self.headers, params=params)
            # DELETE may return 204 with no content
            if response.status_code == 204:
                return None
            return self._handle_response(response)

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticate and store token."""
        # Form data for OAuth2 password flow
        data = {
            "username": username,
            "password": password
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }

        url = f"{self.base_url}/api/v1/auth/login"

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, data=data)

            if response.status_code == 200:
                token_data = response.json()
                # Save token
                self.token_manager.save_token(
                    access_token=token_data["access_token"],
                    token_type=token_data.get("token_type", "bearer"),
                    expires_in=token_data.get("expires_in")
                )
                return token_data
            else:
                try:
                    error_data = response.json()
                    message = error_data.get("detail", "Authentication failed")
                except:
                    message = "Authentication failed"

                raise AuthenticationError(
                    message=message,
                    details={"status_code": response.status_code}
                )
