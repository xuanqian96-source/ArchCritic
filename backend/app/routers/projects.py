"""提供项目创建与列表接口，供前端项目管理页面调用。"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, User
from app.schemas import ProjectCreate, ProjectRead

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, db: Session = Depends(get_db)
) -> Project:
    """创建一个新的演示项目。"""
    owner = User(name=payload.owner_name, role="student")
    db.add(owner)
    db.flush()

    project = Project(
        name=payload.name,
        building_type=payload.building_type,
        owner_name=payload.owner_name,
        user_id=owner.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    """返回当前已创建的项目列表。"""
    result = db.execute(select(Project).order_by(Project.id.desc()))
    return list(result.scalars().all())
