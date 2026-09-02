# Authentication Phase

This directory contains the security, authentication, and RBAC authorization components for FreightCore Backend.

## Components

- **Auth Service**: Business logic for login, token refresh, token logout, and MFA enrollment in `backend/app/modules/auth/service.py`.
- **Security Utilities**: Password hashing (bcrypt), JWT access/refresh token creation, Fernet encryption, TOTP MFA in `backend/app/core/security.py`.
- **RBAC & Permissions**: Granular system permissions, system role definitions (`SUPER_ADMIN`, `BRANCH_MANAGER`, `SALES`, etc.) in `backend/app/core/permissions.py`.
- **Auth Endpoints**: FastAPI endpoints (`/api/v1/auth/login`, `/refresh`, `/logout`, `/me`, `/mfa/enroll`, `/mfa/confirm`) in `backend/app/api/v1/endpoints/auth.py`.

## Quick Usage

```python
from app.modules.auth.service import AuthService
from app.core.security import hash_password, verify_password, create_access_token
from app.core.permissions import SystemRole
```
