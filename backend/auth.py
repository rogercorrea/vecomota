import os
import time
import secrets
from urllib.parse import urlencode

import httpx
import jwt

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

JWT_ALG = "HS256"
JWT_TTL_SECONDS = 60 * 60 * 24 * 30  # sessão válida por 30 dias


def _jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def new_state_token() -> str:
    """Token anti-CSRF de uso único para o fluxo OAuth."""
    return secrets.token_urlsafe(24)


def build_google_auth_url(state: str) -> str:
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": os.environ["GOOGLE_REDIRECT_URI"],
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_userinfo(code: str) -> dict:
    """Troca o code do callback por um access_token e busca os dados do usuário."""
    async with httpx.AsyncClient(timeout=10) as client:
        token_res = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "redirect_uri": os.environ["GOOGLE_REDIRECT_URI"],
                "grant_type": "authorization_code",
            },
        )
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]

        userinfo_res = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_res.raise_for_status()
        return userinfo_res.json()  # {sub, email, name, picture, ...}


def issue_session_jwt(user_id: str) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + JWT_TTL_SECONDS}
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALG)


def decode_session_jwt(token: str) -> str | None:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALG])
        return payload["sub"]
    except jwt.PyJWTError:
        return None
