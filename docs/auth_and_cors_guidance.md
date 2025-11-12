
# Authentication and CORS Guidance

This document provides guidance on handling authentication and Cross-Origin Resource Sharing (CORS) between the frontend and backend services in a production environment.

## CORS Configuration

When the frontend and backend services are running on different domains, you need to configure CORS in the FastAPI backend to allow requests from the frontend domain.

### Best Practices

*   **Restrict origins:** Do not use `allow_origins=["*"]` in a production environment. Instead, explicitly list the allowed origins. This helps prevent unauthorized domains from interacting with your API.
*   **Use specific methods and headers:** If possible, specify the allowed HTTP methods and headers instead of using `allow_methods=["*"]` and `allow_headers=["*"]`. This provides an extra layer of security.
*   **Allow credentials for token-based auth:** If you are using token-based authentication, you will need to set `allow_credentials=True` to allow the frontend to send the authentication token in the `Authorization` header.

### Example Configuration

Here's an example of how to configure CORS in `app/main.py` for a production environment:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

# ... (other imports)

app = FastAPI(
    title=settings.app_name,
    description="Personal research repository with RAG-powered search",
    version=settings.app_version
)

# CORS middleware
origins = [
    "https://your-frontend-domain.com",
    "https://www.your-frontend-domain.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ... (rest of the application)
```

## Authentication

For a production environment, you should implement a robust authentication mechanism to secure your API. Token-based authentication is a good choice for single-page applications like the one in this project.

### Token-Based Authentication

Here's a high-level overview of how to implement token-based authentication:

1.  **Create a login endpoint:** Create a new endpoint in your API that accepts a username and password.
2.  **Validate credentials:** When a user submits their credentials, validate them against the database.
3.  **Generate a token:** If the credentials are valid, generate a JSON Web Token (JWT) that contains the user's ID and other relevant information.
4.  **Return the token:** Return the JWT to the frontend.
5.  **Store the token:** The frontend should store the JWT in a secure way, such as in an `HttpOnly` cookie or in local storage.
6.  **Send the token with requests:** The frontend should send the JWT in the `Authorization` header with every request to the API.
7.  **Protect endpoints:** Create a dependency that verifies the JWT and protects your API endpoints from unauthorized access.

### Recommended Libraries

*   **`passlib`:** For hashing and verifying passwords.
*   **`python-jose`:** For encoding and decoding JWTs.

### Security Considerations

*   **Use HTTPS:** Always use HTTPS in a production environment to encrypt the communication between the frontend and backend.
*   **Set token expiration:** Set an expiration time for your JWTs to reduce the risk of token theft.
*   **Implement token refresh:** Implement a mechanism to refresh the JWT before it expires to provide a better user experience.
*   **Store tokens securely:** Be mindful of where you store the JWT on the frontend. `HttpOnly` cookies are generally more secure than local storage as they are not accessible via JavaScript.

## Next Steps

1.  **Update `app/main.py`:** Update the CORS configuration in `app/main.py` to allow requests from the production frontend domain.
2.  **Implement authentication:** Implement token-based authentication in the FastAPI backend.
3.  **Update the frontend:** Update the frontend to handle the authentication flow, including storing the JWT and sending it with requests.

### Production Reference Configuration (Sprint 05)

Use the following `.env` fragment when deploying the FastAPI service behind Cloudflare/ Railway:

```
ENVIRONMENT=production
DEBUG=false
CORS_ALLOWED_ORIGINS_PROD=["https://namozine.com", "https://www.namozine.com"]
CORS_ALLOWED_METHODS=["GET","POST","PUT","PATCH","DELETE","OPTIONS"]
CORS_ALLOWED_HEADERS=["Authorization","Content-Type"]

# Railway origins documented for incident response
CORS_ALLOWED_ORIGINS_DEV=["http://localhost:3000"]

# Frontend (Next.js) picks up the vanity domain through NEXT_PUBLIC_API_BASE_URL (host only)
NEXT_PUBLIC_API_BASE_URL=https://api.namozine.com
```

After updating the environment variables, restart the FastAPI process and re-run the production Playwright smoke suite to verify that `https://namozine.com/missions` and `https://api.namozine.com/api/v1/health` (or whatever path matches `NEXT_PUBLIC_API_PATH_PREFIX`) both succeed with `access-control-allow-origin: https://namozine.com`. Keep `NEXT_PUBLIC_API_BASE_URL` host-only and adjust `NEXT_PUBLIC_API_PATH_PREFIX` (`/api/v1` by default, set to `""` for root-level APIs) instead of hard-coding suffixes into the base URL.

## TraceLab Implementation Notes

- **Environment variables:**
  - `AUTH_USERNAME` and either `AUTH_PASSWORD` (hashed automatically at startup) or `AUTH_PASSWORD_HASH` define the service account used for login.
  - `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_ALGORITHM`, and the CORS-related settings (`CORS_ALLOWED_ORIGINS_DEV`, `CORS_ALLOWED_ORIGINS_PROD`, `CORS_ALLOWED_METHODS`, `CORS_ALLOWED_HEADERS`) are required for secure deployments.
- **API surface:**
  - `POST /api/v1/auth/login` validates the configured credentials with passlib and issues a JWT signed by `python-jose`.
  - `POST /api/v1/auth/refresh` rotates the caller's token without re-submitting credentials.
  - All routers except `/api/v1/health` are now wrapped in an authentication dependency; missing or invalid bearer tokens return `401` with actionable error text.
- **Frontend updates:**
  - The Next.js UI introduces an `AuthGate` and login form that stores the access token (and username metadata) in local storage, automatically attaching the header via the shared API client.
  - Users must sign in before reaching `/missions` pages, and a signed-in banner exposes a manual sign-out action.
- **CORS controls:**
  - In development, `http://localhost:3000` is the default allowed origin. Production builds must specify explicit domains via `CORS_ALLOWED_ORIGINS_PROD`; wildcard origins are rejected to satisfy hardening requirements.
  - Only the headers listed in `CORS_ALLOWED_HEADERS` (default: `Authorization`, `Content-Type`) are accepted, and the middleware mirrors the allowed origin back to clients to satisfy browser pre-flight checks.
