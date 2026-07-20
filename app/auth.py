from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient, decode
from jwt.exceptions import PyJWTError

from app.config import Settings, get_settings


def _jwks_url(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"


async def require_user(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    if not settings.auth_required:
        return {"sub": "local-dev"}

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    if not settings.azure_ad_tenant_id or not settings.azure_ad_audience:
        raise HTTPException(status_code=500, detail="Azure AD auth is not configured")

    token = auth_header.removeprefix("Bearer ").strip()
    issuer = f"https://login.microsoftonline.com/{settings.azure_ad_tenant_id}/v2.0"

    try:
        signing_key = PyJWKClient(_jwks_url(settings.azure_ad_tenant_id)).get_signing_key_from_jwt(token)
        return decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.azure_ad_audience,
            issuer=issuer,
        )
    except PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

