import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.user import LoginRequest, LoginResponse, RegisterRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])
DUMMY_PASSWORD_HASH = "$2b$12$YILLYIEDI4PIp57e3ednJuyECemIm2usxgBx1JkQhZnrssiB5.WIu"


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    hashed = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    user = User(email=body.email, hashed_password=hashed)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return LoginResponse(user_id=str(user.id), email=user.email)


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Constant-time check prevents timing attacks / user enumeration
    stored = user.hashed_password.encode() if user else DUMMY_PASSWORD_HASH.encode()
    password_ok = bcrypt.checkpw(body.password.encode(), stored)

    if not user or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return LoginResponse(user_id=str(user.id), email=user.email)


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    result = await db.execute(select(User).where(User.id == current_user["user_id"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(user_id=str(user.id), email=user.email)
