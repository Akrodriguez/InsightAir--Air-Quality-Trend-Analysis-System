from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, EmailStr
from datetime import datetime
import logging
from ..db import get_db
from ..models import User, RefreshToken
from ..core.security import hash_password, verify_password, create_access_token, get_auth_user
from ..core.config import settings

router = APIRouter()
logger = logging.getLogger("airq.auth")

def _issue_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
        max_age=settings.JWT_EXPIRES_MIN * 60,
    )

def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path="/",
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )

def _create_user_token(user: User) -> str:
    return create_access_token(
        {"sub": str(user.id), "email": user.email, "plan": user.plan},
        settings.JWT_EXPIRES_MIN
    )

@router.get("/test")
def test_auth():
    """Simple test endpoint without database dependency"""
    return {"status": "ok", "message": "Auth router working"}

class SignupRequest(BaseModel):
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    plan: str

@router.post("/signup", response_model=UserResponse, status_code=201)
def signup(request: SignupRequest, response: Response, db: Session = Depends(get_db)):
    try:
        email = request.email.strip().lower()
        # Check if user exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create new user
        hashed_pw = hash_password(request.password)
        user = User(
            email=email,
            password_hash=hashed_pw,
            plan="free"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Auto-login the user after signup
        _issue_auth_cookie(response, _create_user_token(user))
        
        return UserResponse(id=user.id, email=user.email, plan=user.plan)
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error during signup")
        raise HTTPException(status_code=500, detail="Database error during signup")
    except Exception:
        db.rollback()
        logger.exception("Unexpected error during signup")
        raise HTTPException(status_code=500, detail="Signup failed; check backend logs")

@router.post("/login", response_model=UserResponse)
def login(request: LoginRequest, response: Response, db: Session = Depends(get_db)):
    try:
        email = request.email.strip().lower()
        # Find user
        user = db.query(User).filter(User.email == email).first()
        if not user or not verify_password(request.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Create JWT token
        _issue_auth_cookie(response, _create_user_token(user))
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        
        return UserResponse(id=user.id, email=user.email, plan=user.plan)
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error during login")
        raise HTTPException(status_code=500, detail="Database error during login")
    except Exception:
        db.rollback()
        logger.exception("Unexpected error during login")
        raise HTTPException(status_code=500, detail="Login failed; check backend logs")

@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        # Get user from token to clean up refresh tokens
        user_data = get_auth_user(request)
        if user_data:
            # Delete all refresh tokens for this user
            db.query(RefreshToken).filter(RefreshToken.user_id == user_data["id"]).delete()
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("Unexpected error during logout")

    _clear_auth_cookie(response)
    return {"message": "Logged out successfully"}

@router.get("/me", response_model=UserResponse)
def get_current_user(request: Request, db: Session = Depends(get_db)):
    try:
        user_data = get_auth_user(request)
        if not user_data:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        # Get fresh user data from DB
        user = db.query(User).filter(User.id == user_data["id"]).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        return UserResponse(id=user.id, email=user.email, plan=user.plan)
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("Database error while loading current user")
        raise HTTPException(status_code=500, detail="Database error while loading current user")
    except Exception:
        logger.exception("Unexpected error while loading current user")
        raise HTTPException(status_code=500, detail="Unable to load current user")


