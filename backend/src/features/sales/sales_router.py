from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlmodel import Session
from src.core.db import get_session
from .sales_schemas import SalesCreate, SalesUpdate, SalesOut
from .sales_services import create_sale, update_sale, get_all_sales, change_status, get_sale
from src.security import oauth2
from src.schemas import TokenData

router = APIRouter(prefix="/sales", tags=["Sales"])
DBSession = Annotated[Session, Depends(get_session)]

def admin_required(user: TokenData = Depends(oauth2.get_current_user)):
    if user.role.lower() != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user

@router.post("/", response_model=SalesOut, status_code=status.HTTP_201_CREATED)
def create_sales(
    sale: SalesCreate,
    db: DBSession,
    user: TokenData = Depends(admin_required)
):
    return create_sale(db, sale, user.company_id)

@router.put("/{sale_id}", response_model=SalesOut)
def update_sales(
    sale_id: int,
    sale_update: SalesUpdate,
    db: DBSession,
    user: TokenData = Depends(admin_required)
):
    db_sale = update_sale(db, sale_id, sale_update, user.company_id)
    if not db_sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")
    return db_sale

@router.get("/", response_model=List[SalesOut])
def read_all_sales(
    db: DBSession,
    user: TokenData = Depends(admin_required)
):
    return get_all_sales(db, user.company_id)

@router.patch("/{sale_id}/status", response_model=SalesOut)
def change_sales_status(
    db: DBSession,
    sale_id: int,
    status: str = Body(..., embed=True),
    user: TokenData = Depends(admin_required)
):
    db_sale = change_status(db, sale_id, status, user.company_id)
    if not db_sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")
    return db_sale

@router.get("/{sale_id}", response_model=SalesOut)
def read_sale(
    sale_id: int,
    db: DBSession,
    user: TokenData = Depends(admin_required)
):
    db_sale = get_sale(db, sale_id, user.company_id)
    if not db_sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")
    return db_sale


