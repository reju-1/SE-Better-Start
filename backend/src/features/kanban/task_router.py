from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from pydantic import BaseModel
from .task_schemas import TaskCreate, TaskResponse, TaskUpdate
from .task_services import (
    create_task, get_task, update_task, delete_task, get_tasks,
    add_member_to_task, remove_member_from_task, update_task_status
)
from .task_schemas import ProjectWithTasksResponse, TaskResponse
from src.models.project_models import Project
from src.features.kanban.task_services import get_tasks
from src.core.db import get_session
from src.security import oauth2
from src.schemas import TokenData
from src.enums import KanbanStatus
from src.models.user_models import User
from src.models.company_models import CompanyMember
from src.models.task_models import TaskMember  # Add this import


router = APIRouter(prefix="/tasks")
DBSession = Depends(get_session)

class TaskMemberAddRequest(BaseModel):
    work: str

@router.post("/project/{project_id}", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_new_task(
    project_id: int,
    task: TaskCreate,
    session: Session = DBSession,
    user: TokenData = Depends(oauth2.get_current_user)
):
    if user.role != "Admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can create tasks.")
    db_user = session.exec(select(User).where(User.email == user.email)).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    task.assignee = db_user.id  # set assignee to current user's id
    return create_task(project_id, task, session)

@router.get("/{task_id}", response_model=TaskResponse)
def read_task_by_task_id(task_id: int, session: Session = DBSession, user: TokenData = Depends(oauth2.get_current_user)):
    task = get_task(task_id, session, user)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    members = session.exec(
        select(TaskMember).where(TaskMember.task_id == task.id)
    ).all()
    member_refs = []
    for m in members:
        company_member = session.exec(
            select(CompanyMember).where(CompanyMember.user_id == m.user_id)
        ).first()
        user_obj = session.exec(
            select(User).where(User.id == m.user_id)
        ).first()
        member_refs.append({
            "id": m.user_id,
            "name": user_obj.name if user_obj else "",
            "work": company_member.work if company_member else m.work,
            "photo": user_obj.photo if user_obj and hasattr(user_obj, "photo") else None
        })
    task_dict = task.dict()
    task_dict["members"] = member_refs
    return TaskResponse(**task_dict)

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_existing_task(task_id: int, session: Session = DBSession, user: TokenData = Depends(oauth2.get_current_user)):
    if user.role != "Admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can create tasks.")
    delete_task(task_id, session, user)

@router.get("/project/{project_id}/tasks", response_model=ProjectWithTasksResponse)
def read_tasks_by_project(
    project_id: int,
    session: Session = Depends(get_session),
    user: TokenData = Depends(oauth2.get_current_user),
):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    tasks = get_tasks(project_id, session, user)
    task_responses = []
    for task in tasks:
        members = session.exec(
            select(TaskMember).where(TaskMember.task_id == task.id)
        ).all()
        member_refs = []
        for m in members:
            company_member = session.exec(
                select(CompanyMember).where(CompanyMember.user_id == m.user_id)
            ).first()
            user_obj = session.exec(
                select(User).where(User.id == m.user_id)
            ).first()
            member_refs.append({
                "id": m.user_id,
                "name": user_obj.name if user_obj else "",
                "work": company_member.work if company_member else m.work,
                "photo": user_obj.photo if user_obj and hasattr(user_obj, "photo") else None
            })
        task_dict = task.dict()
        task_dict["members"] = member_refs
        task_responses.append(TaskResponse(**task_dict))
    return {
        "title": project.title,
        "description": project.description,
        "tasks": task_responses
    }

@router.patch("/{task_id}/status", status_code=status.HTTP_200_OK)
def change_task_status(
    task_id: int,
    status: KanbanStatus,
    session: Session = DBSession,
    user: TokenData = Depends(oauth2.get_current_user),
):
    updated = update_task_status(task_id, status, session)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return {"message": "Task status updated successfully"}

# --- Task Member Management ---

@router.post("/{task_id}/members/{user_id}", status_code=status.HTTP_200_OK)
def add_member(
    task_id: int,
    user_id: int,
    work: str,
    session: Session = DBSession,
    user: TokenData = Depends(oauth2.get_current_user)
):
    if user.role != "Admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can create tasks.")
    add_member_to_task(task_id, user_id, work, session, user)
    return {"detail": "Member added to task successfully."}

@router.delete("/{task_id}/members/{user_id}", status_code=status.HTTP_200_OK)
def remove_member(task_id: int, user_id: int, session: Session = DBSession, user: TokenData = Depends(oauth2.get_current_user)):
    if user.role != "Admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can create tasks.")
    remove_member_from_task(task_id, user_id, session, user)
    return {"detail": "Member removed from task successfully."}

@router.patch("/{task_id}", status_code=status.HTTP_200_OK)
def update_existing_task(
    task_id: int,
    task_update: TaskUpdate,
    session: Session = DBSession,
    user: TokenData = Depends(oauth2.get_current_user)
):
    if user.role != "Admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can update tasks.")
    update_task(task_id, task_update, session, user)
    return {"message": "Task updated successfully"}
