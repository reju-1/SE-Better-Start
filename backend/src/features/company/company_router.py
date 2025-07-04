# Company Router
from typing import Annotated, Optional
from fastapi import Security
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select
from datetime import timedelta

# Internal imports
from src import models
from src.core import settings
from src.core import get_session
from src.security import oauth2
from src.services.email import send_mail
from src.schemas import Message, TokenData
from src.utils.jwt_utils import create_jwt_token, decode_jwt_token
from . import company_schemas as schema
from . import company_services

from src import enums

router = APIRouter(prefix="/company")
DBSession = Annotated[Session, Depends(get_session)]


@router.post("/create", response_model=Message)
def create_company(
    company_info: schema.CompanyCreate,
    session: DBSession,
    user: TokenData = Depends(oauth2.get_current_user),
):
    """
    Create a company and register the creator as an Admin in the CompanyMember table.
    User cannot create a new company if they already own or belong to one.
    """
    # Check if user is a member of any company
    existing_membership = session.exec(
        select(models.CompanyMember).where(models.CompanyMember.user_id == user.email)
    ).first()

    if existing_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You already own or belong to a company. You cannot create another one.",
        )

    # Create company
    new_company = models.Company(**company_info.model_dump(), user_id=user.email)
    session.add(new_company)
    session.commit()
    session.refresh(new_company)

    # Add creator as Admin
    company_member = models.CompanyMember(
        user_id=user.email,
        company_id=new_company.id,
        role=enums.MemberRole.ADMIN,
        position="Founder",  # default or from request
    )
    session.add(company_member)
    session.commit()

    return Message(message="Company created successfully")


@router.get("/invitation/link", response_model=str)
def create_invitation_link(
    session: DBSession,
    user: TokenData = Depends(oauth2.get_current_user),
):
    """
    An admin can create an invitation link via JWT.
    The invitation JWT token contains company_id, role='Member', and position.
    """
    # Verify that user is an ADMIN
    member = session.exec(
        select(models.CompanyMember).where(
            models.CompanyMember.user_id == user.email,
            models.CompanyMember.company_id == user.company_id,
        )
    ).first()

    if not member or member.role != enums.MemberRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admins can generate invite links.",
        )

    payload = {
        "company_id": member.company_id,
        "role": enums.MemberRole.MEMBER,
        "position": "Employee",  # Default; can be made dynamic
    }

    token = create_jwt_token(payload, expires_delta=timedelta(hours=24))
    return f"{settings.api_prefix}/company/invitation/join?token={token}"


@router.get("/invitation/join", response_model=Message)
def join_company_via_invite(
    session: DBSession,
    token: str = Query(...),
    user: TokenData = Depends(oauth2.get_current_user),
):
    """
    A user with no existing company role can join using the invitation link.
    """
    # User must not be already in a company
    existing_member = session.exec(
        select(models.CompanyMember).where(models.CompanyMember.user_id == user.email)
    ).first()

    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are already a member of a company.",
        )

    # Decode token
    data = decode_jwt_token(token)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired invitation token.",
        )
    data = schema.InvitationToken(**data)

    # Ensure company exists
    company = session.get(models.Company, data.company_id)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company does not exist."
        )

    # Add user to company
    new_member = models.CompanyMember(
        user_id=user.email,
        company_id=company.id,
        role=data.role,
        position=data.position,
    )
    session.add(new_member)
    session.commit()

    return Message(message=f"You have successfully joined the company: {company.name}")


@router.get("/{company_id}", response_model=schema.CompanyCreate)
def read_company(
    session: DBSession,
    user: TokenData = Depends(oauth2.get_current_user),
):
    """
    Get company details by company_id if user is associated with it.
    """
    # Check association
    member = session.exec(
        select(models.CompanyMember).where(
            models.CompanyMember.user_id == user.email,
        )
    ).first()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not associated with this company.",
        )
    company = company_services.get_company_by_id(session, user)
    return company


@router.put("/{company_id}", response_model=schema.CompanyCreate)
def update_company(
    update_data: schema.CompanyCreate,
    session: DBSession,
    user: TokenData = Depends(oauth2.get_current_user),
):
    """
    Update company details by company_id if user is the owner/admin.
    """
    # Check association
    member = session.exec(
        select(models.CompanyMember).where(
            models.CompanyMember.user_id == user.email,
        )
    ).first()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not associated with this company.",
        )
    company = company_services.update_company_by_id(session, update_data, user)
    return company


@router.get("/company/members", response_model=list[schema.CompanyMemberInfo])
def list_company_members(
    session: DBSession,
    user: TokenData = Depends(oauth2.get_current_user),
):
    # Ensure user is in a company
    if not user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not associated with any company.",
        )
    members = session.exec(
        select(models.CompanyMember).where(
            models.CompanyMember.company_id == user.company_id
        )
    ).all()
    result = []
    for m in members:
        user_obj = session.exec(
            select(models.User).where(models.User.email == m.user_id)
        ).first()
        result.append(
            {
                "id": user_obj.id if user_obj else None,  # Use integer ID
                "name": user_obj.name if user_obj else "",
                "position": m.position,
            }
        )
    return result


@router.post("/invite/{email}", response_model=Message)
async def send_invitation_link(
    email: str,
    session: DBSession,
    user: oauth2.TokenData = Depends(oauth2.get_current_user),
):
    """
    An admin can create an invitation link via JWT.
    The invitation JWT token contains new_member_email, company_id, role='Member', and position.
    """
    member = session.exec(
        select(models.CompanyMember).where(
            models.CompanyMember.user_id == user.email,
            models.CompanyMember.company_id == user.company_id,
        )
    ).first()

    if not member or member.role != enums.MemberRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admins can generate invite links.",
        )
    # Check if user is already a member
    existing_member = session.exec(
        select(models.CompanyMember).where(models.CompanyMember.user_id == email)
    ).first()

    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of the company.",
        )

    payload = {
        "new_member_email": email,
        "company_id": member.company_id,
        "role": enums.MemberRole.MEMBER,
        "position": "Employee",  # Default; can be made dynamic
    }

    token = create_jwt_token(payload, expires_delta=timedelta(hours=24))
    # return f"{settings.server_url}/api/company/join?token={token}"
    link = f"{settings.server_url}/api/company/join?token={token}"
    await send_mail(
        subject="Invitation link",
        body=link,
        emails=[email],
    )

    return Message(message="Invitation link send successfully!")


@router.get("/join", response_model=Message)
def accept_invitation_link(
    token: str = Query(...),
    session: Session = Depends(get_session),
):
    """
    Parse the JWT token and add the user to the company member table.
    """
    try:
        payload = decode_jwt_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation token.",
        )

    # Extract fields from payload new_member_email
    new_member_email = payload.get("new_member_email")
    company_id = payload.get("company_id")
    role = payload.get("role", enums.MemberRole.MEMBER)
    position = payload.get("position", "Employee")

    # Add new company member
    new_member = models.CompanyMember(
        user_id=new_member_email,
        company_id=company_id,
        role=role,
        position=position,
    )
    session.add(new_member)
    session.commit()

    return Message(message="You have successfully joined the company.")
