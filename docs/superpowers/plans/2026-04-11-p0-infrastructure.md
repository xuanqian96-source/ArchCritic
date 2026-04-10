# P0: ArchCritic 基础设施搭建 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 ArchCritic 项目骨架，使后端 FastAPI 服务、SQLite 数据库、LLM API 封装层和前端 React 应用全部可运行并能相互通信。

**Architecture:** 单体后端（FastAPI）+ 前端 SPA（React）+ SQLite 数据库。后端负责 API 路由、ORM 模型、LLM 调用封装；前端负责界面展示。LLM 封装层抽象为统一接口，支持后续切换不同模型供应商。

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy + aiosqlite | React 18 + Vite | SQLite

---

## File Structure

```
ArchCritic/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app 入口，挂载路由和中间件
│   │   ├── config.py            # 配置管理（从 .env 读取）
│   │   ├── database.py          # SQLAlchemy engine + session
│   │   ├── models.py            # ORM 模型（User, Project, Submission, AgentEvaluation, OverallReport）
│   │   ├── schemas.py           # Pydantic 请求/响应模型
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── health.py        # /health 端点
│   │   │   ├── projects.py      # 项目 CRUD
│   │   │   └── submissions.py   # 方案提交
│   │   └── llm/
│   │       ├── __init__.py
│   │       ├── base.py          # LLM 抽象基类
│   │       ├── openai_client.py # OpenAI/GPT 实现
│   │       └── client.py        # 工厂函数，按配置返回具体客户端
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_health.py
│   │   ├── test_database.py
│   │   ├── test_models.py
│   │   └── test_llm.py
│   ├── prompts/
│   │   └── v1/
│   │       └── CHANGELOG.md     # Prompt 版本变更日志
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── (Vite + React 项目，Task 6 中 create)
├── .gitignore
└── README.md
```

---

### Task 1: Git 仓库初始化 + .gitignore

**Files:**
- Create: `ArchCritic/.gitignore`
- Create: `ArchCritic/README.md`

- [ ] **Step 1: 初始化 Git 仓库**

```bash
cd /mnt/e/claude/论文/ArchCritic
git init
```

- [ ] **Step 2: 创建 .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
.venv/
venv/

# Environment
.env

# Database
*.db
*.sqlite3

# Node
node_modules/
frontend/dist/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 3: 创建 README.md**

```markdown
# ArchCritic

基于多Agent协作与RAG知识增强的建筑设计课评图辅助系统。

## 开发环境

- Python 3.10+
- Node.js 20+
- SQLite

## 快速启动

```bash
# 后端
cd backend
pip install -r requirements.txt
cp .env.example .env  # 填入 API key
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev
```
```

- [ ] **Step 4: 首次提交**

```bash
git add .gitignore README.md
git commit -m "chore: init repo with gitignore and readme"
```

---

### Task 2: 后端项目结构 + FastAPI 入口 + /health 端点

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/health.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: 创建 requirements.txt**

```
fastapi==0.115.*
uvicorn[standard]==0.34.*
sqlalchemy==2.0.*
aiosqlite==0.20.*
pydantic==2.*
pydantic-settings==2.*
python-dotenv==1.*
httpx==0.28.*
python-multipart==0.0.*
pytest==8.*
pytest-asyncio==0.24.*
```

- [ ] **Step 2: 创建 .env.example**

```
# LLM API
OPENAI_API_KEY=sk-your-key-here
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o

# Database
DATABASE_URL=sqlite+aiosqlite:///./archcritic.db

# Server
CORS_ORIGINS=http://localhost:5173
```

- [ ] **Step 3: 安装依赖**

```bash
cd /mnt/e/claude/论文/ArchCritic/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: 所有包安装成功，无报错。

- [ ] **Step 4: 创建 config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    database_url: str = "sqlite+aiosqlite:///./archcritic.db"
    cors_origins: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()
```

- [ ] **Step 5: 创建 health 路由**

`backend/app/routers/health.py`:
```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "archcritic"}
```

- [ ] **Step 6: 创建 FastAPI 主入口**

`backend/app/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import health

app = FastAPI(title="ArchCritic API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
```

`backend/app/__init__.py` 和 `backend/app/routers/__init__.py`: 空文件。

- [ ] **Step 7: 写 health 端点的测试**

`backend/tests/test_health.py`:
```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "archcritic"
```

- [ ] **Step 8: 运行测试**

```bash
cd /mnt/e/claude/论文/ArchCritic/backend
source .venv/bin/activate
python -m pytest tests/test_health.py -v
```

Expected: `test_health_returns_ok PASSED`

- [ ] **Step 9: 手动验证服务启动**

```bash
cd /mnt/e/claude/论文/ArchCritic/backend
source .venv/bin/activate
uvicorn app.main:app --port 8000 &
sleep 2
curl http://localhost:8000/health
kill %1
```

Expected: `{"status":"ok","service":"archcritic"}`

- [ ] **Step 10: 提交**

```bash
git add backend/
git commit -m "feat(backend): fastapi skeleton with /health endpoint"
```

---

### Task 3: 数据库 + ORM 模型

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models.py`
- Create: `backend/app/schemas.py`
- Create: `backend/tests/test_database.py`
- Create: `backend/tests/test_models.py`

- [ ] **Step 1: 写数据库模型测试**

`backend/tests/test_models.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, User, Project, Submission, AgentEvaluation, OverallReport


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_create_user(db):
    user = User(name="Alice", role="student")
    db.add(user)
    db.commit()
    db.refresh(user)
    assert user.id is not None
    assert user.name == "Alice"


def test_create_project_with_user(db):
    user = User(name="Bob", role="student")
    db.add(user)
    db.commit()
    project = Project(name="图书馆设计", building_type="library", user_id=user.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    assert project.user_id == user.id
    assert project.building_type == "library"


def test_create_submission_with_evaluation(db):
    user = User(name="Carol", role="student")
    db.add(user)
    db.commit()
    project = Project(name="美术馆设计", building_type="museum", user_id=user.id)
    db.add(project)
    db.commit()
    submission = Submission(
        project_id=project.id,
        images='["img1.png"]',
        description="一个以光影为主题的美术馆",
        design_stage="scheme",
    )
    db.add(submission)
    db.commit()
    evaluation = AgentEvaluation(
        submission_id=submission.id,
        agent_type="site_response",
        dimension="场地与回应",
        scores='{"1.1": 4, "1.2": 3, "1.3": 4}',
        feedback="总平面布局合理，入口方向可进一步优化。",
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    assert evaluation.submission_id == submission.id


def test_create_overall_report(db):
    user = User(name="Dave", role="student")
    db.add(user)
    db.commit()
    project = Project(name="社区中心", building_type="community_center", user_id=user.id)
    db.add(project)
    db.commit()
    submission = Submission(
        project_id=project.id,
        images='["img1.png"]',
        description="社区活动中心设计",
        design_stage="conceptual",
    )
    db.add(submission)
    db.commit()
    report = OverallReport(
        submission_id=submission.id,
        total_score=72.5,
        grade="B",
        must_fix='["入口流线不清晰"]',
        should_improve='["立面比例"]',
        optional='["材料细节"]',
        strengths='["概念立意清晰"]',
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    assert report.total_score == 72.5
    assert report.grade == "B"
```

- [ ] **Step 2: 运行测试，确认全部失败**

```bash
cd /mnt/e/claude/论文/ArchCritic/backend
source .venv/bin/activate
python -m pytest tests/test_models.py -v
```

Expected: 4 FAILED（ImportError: cannot import name 'Base' from 'app.models'）

- [ ] **Step 3: 实现 database.py**

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 4: 实现 models.py**

```python
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="student")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    projects: Mapped[list["Project"]] = relationship(back_populates="user")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    building_type: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="projects")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="project")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    images: Mapped[str] = mapped_column(Text, default="[]")
    description: Mapped[str] = mapped_column(Text, default="")
    design_stage: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="submissions")
    evaluations: Mapped[list["AgentEvaluation"]] = relationship(back_populates="submission")
    report: Mapped["OverallReport"] = relationship(back_populates="submission", uselist=False)


class AgentEvaluation(Base):
    __tablename__ = "agent_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"))
    agent_type: Mapped[str] = mapped_column(String(50))
    dimension: Mapped[str] = mapped_column(String(100))
    scores: Mapped[str] = mapped_column(Text, default="{}")
    feedback: Mapped[str] = mapped_column(Text, default="")
    rag_references: Mapped[str] = mapped_column(Text, default="[]")
    raw_llm_response: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    submission: Mapped["Submission"] = relationship(back_populates="evaluations")


class OverallReport(Base):
    __tablename__ = "overall_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), unique=True)
    total_score: Mapped[float] = mapped_column(Float)
    grade: Mapped[str] = mapped_column(String(5))
    must_fix: Mapped[str] = mapped_column(Text, default="[]")
    should_improve: Mapped[str] = mapped_column(Text, default="[]")
    optional: Mapped[str] = mapped_column(Text, default="[]")
    strengths: Mapped[str] = mapped_column(Text, default="[]")
    comparison_data: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    submission: Mapped["Submission"] = relationship(back_populates="report")
```

- [ ] **Step 5: 实现 schemas.py**

```python
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    building_type: str


class ProjectResponse(BaseModel):
    id: int
    name: str
    building_type: str

    model_config = {"from_attributes": True}


class SubmissionCreate(BaseModel):
    description: str
    design_stage: str


class HealthResponse(BaseModel):
    status: str
    service: str
```

- [ ] **Step 6: 运行模型测试**

```bash
python -m pytest tests/test_models.py -v
```

Expected: 4 PASSED

- [ ] **Step 7: 写异步数据库初始化测试**

`backend/tests/test_database.py`:
```python
import pytest
from sqlalchemy import create_engine, inspect

from app.models import Base


def test_all_tables_created():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "users" in tables
    assert "projects" in tables
    assert "submissions" in tables
    assert "agent_evaluations" in tables
    assert "overall_reports" in tables
```

- [ ] **Step 8: 运行全部测试**

```bash
python -m pytest tests/ -v
```

Expected: 6 PASSED（1 health + 4 models + 1 database）

- [ ] **Step 9: 在 main.py 中挂载数据库初始化**

在 `backend/app/main.py` 中增加 lifespan：

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="ArchCritic API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
```

- [ ] **Step 10: 提交**

```bash
git add backend/
git commit -m "feat(backend): database schema with 5 ORM models"
```

---

### Task 4: LLM API 封装层

**Files:**
- Create: `backend/app/llm/__init__.py`
- Create: `backend/app/llm/base.py`
- Create: `backend/app/llm/openai_client.py`
- Create: `backend/app/llm/client.py`
- Create: `backend/tests/test_llm.py`

- [ ] **Step 1: 写 LLM 封装层测试**

`backend/tests/test_llm.py`:
```python
import pytest

from app.llm.base import LLMClient, LLMResponse


def test_llm_response_model():
    resp = LLMResponse(content="hello", model="gpt-4o", usage={"prompt_tokens": 10, "completion_tokens": 5})
    assert resp.content == "hello"
    assert resp.usage["prompt_tokens"] == 10


def test_llm_client_is_abstract():
    with pytest.raises(TypeError):
        LLMClient()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_llm.py -v
```

Expected: 2 FAILED（ImportError）

- [ ] **Step 3: 实现 base.py（抽象基类）**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict


class LLMClient(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], model: str | None = None) -> LLMResponse:
        """Send messages to LLM and get response."""

    @abstractmethod
    async def chat_with_images(
        self, messages: list[dict], image_urls: list[str], model: str | None = None
    ) -> LLMResponse:
        """Send messages with images (multimodal) to LLM."""
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_llm.py -v
```

Expected: 2 PASSED

- [ ] **Step 5: 实现 openai_client.py**

```python
import openai

from app.config import settings
from app.llm.base import LLMClient, LLMResponse


class OpenAIClient(LLMClient):
    def __init__(self):
        self._client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        self._default_model = settings.llm_model

    async def chat(self, messages: list[dict], model: str | None = None) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=messages,
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
        )

    async def chat_with_images(
        self, messages: list[dict], image_urls: list[str], model: str | None = None
    ) -> LLMResponse:
        image_content = [
            {"type": "image_url", "image_url": {"url": url}} for url in image_urls
        ]
        if messages and messages[-1]["role"] == "user":
            last = messages[-1]
            text_part = {"type": "text", "text": last["content"]}
            messages = messages[:-1] + [
                {"role": "user", "content": [text_part] + image_content}
            ]
        return await self.chat(messages, model)
```

- [ ] **Step 6: 实现 client.py（工厂函数）**

```python
from app.config import settings
from app.llm.base import LLMClient


def get_llm_client() -> LLMClient:
    if settings.llm_provider == "openai":
        from app.llm.openai_client import OpenAIClient
        return OpenAIClient()
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
```

`backend/app/llm/__init__.py`:
```python
from app.llm.base import LLMClient, LLMResponse
from app.llm.client import get_llm_client

__all__ = ["LLMClient", "LLMResponse", "get_llm_client"]
```

- [ ] **Step 7: 在 requirements.txt 中添加 openai**

在 `backend/requirements.txt` 末尾追加：

```
openai>=1.50
```

```bash
source .venv/bin/activate
pip install openai>=1.50
```

- [ ] **Step 8: 运行全部测试**

```bash
python -m pytest tests/ -v
```

Expected: 8 PASSED

- [ ] **Step 9: 提交**

```bash
git add backend/
git commit -m "feat(backend): LLM API abstraction layer with OpenAI client"
```

---

### Task 5: 项目和提交 API 路由

**Files:**
- Create: `backend/app/routers/projects.py`
- Create: `backend/app/routers/submissions.py`
- Create: `backend/tests/test_projects.py`

- [ ] **Step 1: 写项目 CRUD 路由测试**

`backend/tests/test_projects.py`:
```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_create_and_list_projects():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create
        resp = await client.post(
            "/api/projects",
            json={"name": "图书馆设计", "building_type": "library"},
            params={"user_id": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "图书馆设计"
        assert "id" in data

        # List
        resp = await client.get("/api/projects", params={"user_id": 1})
        assert resp.status_code == 200
        projects = resp.json()
        assert len(projects) >= 1
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_projects.py -v
```

Expected: FAILED（404，路由不存在）

- [ ] **Step 3: 实现 projects.py 路由**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Project, User
from app.schemas import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse)
async def create_project(
    body: ProjectCreate, user_id: int = 1, db: AsyncSession = Depends(get_db)
):
    # Auto-create user if not exists (dev convenience)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(name=f"user_{user_id}", role="student")
        db.add(user)
        await db.commit()
        await db.refresh(user)

    project = Project(name=body.name, building_type=body.building_type, user_id=user.id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(user_id: int = 1, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.user_id == user_id))
    return result.scalars().all()
```

- [ ] **Step 4: 实现 submissions.py 路由**

```python
from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Submission

router = APIRouter(prefix="/api/submissions", tags=["submissions"])


@router.post("")
async def create_submission(
    project_id: int = Form(...),
    description: str = Form(""),
    design_stage: str = Form("scheme"),
    db: AsyncSession = Depends(get_db),
):
    submission = Submission(
        project_id=project_id,
        description=description,
        design_stage=design_stage,
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    return {"id": submission.id, "project_id": submission.project_id, "design_stage": submission.design_stage}


@router.get("")
async def list_submissions(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Submission).where(Submission.project_id == project_id))
    submissions = result.scalars().all()
    return [
        {"id": s.id, "design_stage": s.design_stage, "created_at": str(s.created_at)}
        for s in submissions
    ]
```

- [ ] **Step 5: 在 main.py 中挂载新路由**

在 `backend/app/main.py` 的 import 和 include_router 中增加：

```python
from app.routers import health, projects, submissions

# ... existing code ...

app.include_router(health.router)
app.include_router(projects.router)
app.include_router(submissions.router)
```

- [ ] **Step 6: 运行全部测试**

```bash
python -m pytest tests/ -v
```

Expected: 9+ PASSED

- [ ] **Step 7: 提交**

```bash
git add backend/
git commit -m "feat(backend): project and submission CRUD API routes"
```

---

### Task 6: 前端 React 项目初始化

**Files:**
- Create: `frontend/` (via Vite scaffolding)

- [ ] **Step 1: 用 Vite 创建 React 项目**

```bash
cd /mnt/e/claude/论文/ArchCritic
npm create vite@latest frontend -- --template react
cd frontend
npm install
```

- [ ] **Step 2: 安装 axios 用于 API 通信**

```bash
cd /mnt/e/claude/论文/ArchCritic/frontend
npm install axios
```

- [ ] **Step 3: 替换 App.jsx 为基础连通性测试页**

`frontend/src/App.jsx`:
```jsx
import { useState, useEffect } from "react";
import axios from "axios";

const API_BASE = "http://localhost:8000";

function App() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    axios
      .get(`${API_BASE}/health`)
      .then((res) => setHealth(res.data))
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div style={{ padding: "2rem", fontFamily: "system-ui" }}>
      <h1>ArchCritic</h1>
      <p>建筑设计课评图辅助系统</p>
      <hr />
      <h3>后端连接状态</h3>
      {health ? (
        <p style={{ color: "green" }}>
          {health.service}: {health.status}
        </p>
      ) : error ? (
        <p style={{ color: "red" }}>连接失败: {error}</p>
      ) : (
        <p>检测中...</p>
      )}
    </div>
  );
}

export default App;
```

- [ ] **Step 4: 验证前端可启动**

```bash
cd /mnt/e/claude/论文/ArchCritic/frontend
npm run dev &
sleep 3
curl -s http://localhost:5173 | head -20
kill %1
```

Expected: 返回 HTML 内容（Vite dev server 正常运行）

- [ ] **Step 5: 提交**

```bash
cd /mnt/e/claude/论文/ArchCritic
git add frontend/
git commit -m "feat(frontend): react app scaffold with backend health check"
```

---

### Task 7: Prompt 版本管理目录

**Files:**
- Create: `backend/prompts/v1/CHANGELOG.md`

- [ ] **Step 1: 创建 Prompt 目录和变更日志**

`backend/prompts/v1/CHANGELOG.md`:
```markdown
# Prompt 版本变更日志

## v1 — 初始版本

- **日期**: 2026-04-11
- **变更**: 建立目录结构
- **说明**: P1 阶段将在此目录下添加评价框架 Prompt 模板

### 文件说明

每个 Prompt 版本包含：
- `system.txt` — 系统指令
- `user_template.txt` — 用户输入模板
- `output_schema.json` — 输出格式 JSON Schema

调整 Prompt 时，复制当前版本目录为 `v2/`、`v3/` 等，并在此文件记录变更原因。
```

- [ ] **Step 2: 提交**

```bash
git add backend/prompts/
git commit -m "chore: prompt version management directory structure"
```

---

## P0 完成验证清单

全部 Task 完成后，按以下步骤端到端验证：

```bash
# 1. 后端启动
cd /mnt/e/claude/论文/ArchCritic/backend
source .venv/bin/activate
uvicorn app.main:app --port 8000 &

# 2. 验证 /health
curl http://localhost:8000/health
# Expected: {"status":"ok","service":"archcritic"}

# 3. 验证 API 文档自动生成
curl -s http://localhost:8000/docs | head -5
# Expected: HTML 页面（Swagger UI）

# 4. 验证项目创建
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"测试项目","building_type":"library"}'
# Expected: {"id":1,"name":"测试项目","building_type":"library"}

# 5. 前端启动并检查连通性
cd /mnt/e/claude/论文/ArchCritic/frontend
npm run dev &
# 在浏览器打开 http://localhost:5173，看到 "archcritic: ok" 绿色文字

# 6. 全部测试通过
cd /mnt/e/claude/论文/ArchCritic/backend
python -m pytest tests/ -v
# Expected: 全部 PASSED

# 清理
kill %1 %2
```
