from fastapi import Depends, HTTPException, status
from app.core.security import oauth2_scheme, verify_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        payload = verify_jwt(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return {"user_id": user_id}
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
