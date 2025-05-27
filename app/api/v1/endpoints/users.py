# app/api/v1/endpoints/users.py
from typing import Any, List

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_superuser, get_current_user, get_db
from app.core.security import get_password_hash, verify_password
from app.models.user import User, UserRole
from app.models.power_plant import PowerPlant
from app.schemas.user import UserCreate, UserResponse, UserUpdate, UserWithPermissions

router = APIRouter()


@router.get("/", response_model=List[UserResponse])
def read_users(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """
    Retrieve users. Only accessible by admin users.
    """
    users = db.query(User).offset(skip).limit(limit).all()
    return users


@router.post("/", response_model=UserResponse)
def create_user(
    *,
    db: Session = Depends(get_db),
    user_in: UserCreate,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """
    Create new user. Only accessible by admin users.
    """
    # Validate email
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists in the system.",
        )
    
    # Validate role and power plant assignment
    if user_in.role in [UserRole.OPERATOR, UserRole.EDITOR] and not user_in.power_plant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Operators must be assigned to a power plant.",
        )
    
    # Treat power_plant_id=0 as None
    power_plant_id = None if user_in.power_plant_id == 0 else user_in.power_plant_id
    
    # Validate power plant if provided
    if power_plant_id:
        power_plant = db.query(PowerPlant).filter(PowerPlant.id == power_plant_id).first()
        if not power_plant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Power plant not found",
            )
    
    # Validate password
    if len(user_in.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long",
        )
    
    # Create user
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role,
        power_plant_id=power_plant_id,
        is_active=True,
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=UserWithPermissions)
def read_user_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Get current user information.
    """
    # Get power plant name if assigned
    power_plant_name = None
    if current_user.power_plant_id:
        power_plant = db.query(PowerPlant).filter(PowerPlant.id == current_user.power_plant_id).first()
        if power_plant:
            power_plant_name = power_plant.name
    
    # Define permissions based on role
    permissions = []
    
    # Basic permissions for all users
    permissions.append("view_dashboard")
    permissions.append("view_reports")
    
    # Operator permissions
    if current_user.role in [UserRole.OPERATOR, UserRole.EDITOR]:
        permissions.append("submit_readings")
        permissions.append("submit_reports")
    
    # Editor permissions
    if current_user.role in [UserRole.EDITOR]:
        permissions.append("edit_readings")
        permissions.append("edit_reports")
    
    # Admin permissions
    if current_user.role == UserRole.ADMIN:
        permissions.append("manage_users")
        permissions.append("manage_power_plants")
        permissions.append("manage_turbines")
        permissions.append("view_audit_logs")
    
    # Combine user data with permissions
    result = {
        **current_user.__dict__,
        "power_plant_name": power_plant_name,
        "permissions": permissions
    }
    
    return result


@router.put("/me/password", response_model=UserResponse)
def update_user_password(
    *,
    db: Session = Depends(get_db),
    current_password: str = Body(...),
    new_password: str = Body(...),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Update current user password.
    """
    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password",
        )
    
    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long",
        )
    
    current_user.hashed_password = get_password_hash(new_password)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    
    return current_user


@router.put("/me", response_model=UserResponse)
def update_user_me(
    *,
    db: Session = Depends(get_db),
    full_name: str = Body(None),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Update own user information. Only full_name can be updated by users themselves.
    """
    if full_name is not None:
        current_user.full_name = full_name
        db.add(current_user)
        db.commit()
        db.refresh(current_user)
    
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
def read_user_by_id(
    user_id: int,
    current_user: User = Depends(get_current_active_superuser),
    db: Session = Depends(get_db),
) -> Any:
    """
    Get a specific user by id. Only accessible by admin users.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    *,
    db: Session = Depends(get_db),
    user_id: int,
    user_in: UserUpdate,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """
    Update a user. Only accessible by admin users.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Validate power plant if being updated
    if user_in.power_plant_id is not None:
        power_plant = db.query(PowerPlant).filter(PowerPlant.id == user_in.power_plant_id).first()
        if not power_plant and user_in.power_plant_id != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Power plant not found",
            )
    
    # Check for duplicate email
    if user_in.email is not None and user_in.email != user.email:
        existing = db.query(User).filter(User.email == user_in.email).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email already exists",
            )
    
    # Update user attributes
    if user_in.email is not None:
        user.email = user_in.email
    if user_in.full_name is not None:
        user.full_name = user_in.full_name
    if user_in.role is not None:
        user.role = user_in.role
    if user_in.is_active is not None:
        user.is_active = user_in.is_active
    if user_in.power_plant_id is not None:
        # Allow setting to null by using 0
        user.power_plant_id = None if user_in.power_plant_id == 0 else user_in.power_plant_id
    if user_in.password is not None:
        user.hashed_password = get_password_hash(user_in.password)
    
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    *,
    db: Session = Depends(get_db),
    user_id: int,
    current_user: User = Depends(get_current_active_superuser),
) -> Response:
    """
    Permanently delete a user from the database.
    Only accessible by admin users.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own user account",
        )
    
    # Hard delete
    db.delete(user)
    db.commit()
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)