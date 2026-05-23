import jwt
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_jwt(token: str) -> dict:
    payload = jwt.decode(token, settings.NEXTAUTH_SECRET, algorithms=["HS256"])
    return payload
