import os
import datetime
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from . import models, auth

Base.metadata.create_all(bind=engine)

app = FastAPI(title="TaskFlow")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev-secret-change-me"))

BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ---------- Home ----------

@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    return RedirectResponse("/projects" if user else "/login")


# ---------- Auth ----------

@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.post("/register")
def register_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(models.User).filter_by(email=email).first()
    if existing:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "An account with that email already exists."}
        )

    user = models.User(name=name, email=email, password_hash=auth.hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse("/projects", status_code=303)


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter_by(email=email).first()
    if not user or not auth.verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Invalid email or password."}
        )

    request.session["user_id"] = user.id
    return RedirectResponse("/projects", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------- Projects ----------

@app.get("/projects")
def list_projects(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    memberships = db.query(models.ProjectMembership).filter_by(user_id=user.id).all()
    joined_project_ids = {m.project_id for m in memberships}

    # Any project the user hasn't joined yet — shown so they can self-serve join
    other_projects = (
        db.query(models.Project)
        .filter(~models.Project.id.in_(joined_project_ids))
        .all()
        if joined_project_ids
        else db.query(models.Project).all()
    )

    return templates.TemplateResponse(
        "projects_list.html",
        {
            "request": request,
            "user": user,
            "memberships": memberships,
            "other_projects": other_projects,
        },
    )


@app.post("/projects")
def create_project(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    project = models.Project(name=name, description=description)
    db.add(project)
    db.commit()
    db.refresh(project)

    # Creator becomes Admin of their own project automatically
    membership = models.ProjectMembership(project_id=project.id, user_id=user.id, role=models.Role.ADMIN)
    db.add(membership)
    db.commit()

    return RedirectResponse(f"/projects/{project.id}", status_code=303)


@app.post("/projects/{project_id}/join")
def join_project(project_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    existing = auth.get_membership(db, project_id, user.id)
    if not existing:
        # Self-serve join always grants Member — never Admin. Only an existing
        # Admin can promote someone via Manage Members, so this can't be used
        # to grant yourself elevated access.
        db.add(models.ProjectMembership(project_id=project_id, user_id=user.id, role=models.Role.MEMBER))
        db.commit()

    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@app.get("/projects/{project_id}")
def project_board(project_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    membership = auth.get_membership(db, project_id, user.id)
    if not membership:
        raise HTTPException(403, "You're not a member of this project")

    project = db.query(models.Project).get(project_id)
    tasks = db.query(models.Task).filter_by(project_id=project_id).all()
    members = db.query(models.ProjectMembership).filter_by(project_id=project_id).all()

    columns = {
        "todo": [t for t in tasks if t.status == models.TaskStatus.TODO],
        "in_progress": [t for t in tasks if t.status == models.TaskStatus.IN_PROGRESS],
        "done": [t for t in tasks if t.status == models.TaskStatus.DONE],
    }

    return templates.TemplateResponse(
        "project_board.html",
        {
            "request": request,
            "user": user,
            "project": project,
            "columns": columns,
            "members": members,
            "is_admin": membership.role == models.Role.ADMIN,
        },
    )


# ---------- Tasks ----------

@app.post("/projects/{project_id}/tasks")
def create_task(
    project_id: int,
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    assignee_id: str = Form(""),
    due_date: str = Form(""),
    db: Session = Depends(get_db),
):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    membership = auth.get_membership(db, project_id, user.id)
    if not membership:
        raise HTTPException(403, "You're not a member of this project")

    task = models.Task(
        project_id=project_id,
        title=title,
        description=description,
        assignee_id=int(assignee_id) if assignee_id else None,
        due_date=datetime.datetime.fromisoformat(due_date) if due_date else None,
    )
    db.add(task)
    db.commit()

    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@app.post("/projects/{project_id}/tasks/{task_id}/status")
def update_task_status(
    project_id: int,
    task_id: int,
    request: Request,
    new_status: str = Form(...),
    db: Session = Depends(get_db),
):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    membership = auth.get_membership(db, project_id, user.id)
    if not membership:
        raise HTTPException(403, "You're not a member of this project")

    task = db.query(models.Task).get(task_id)
    if not task or task.project_id != project_id:
        raise HTTPException(404, "Task not found")

    task.status = models.TaskStatus(new_status)
    db.commit()

    return RedirectResponse(f"/projects/{project_id}", status_code=303)


# ---------- Members (admin only) ----------

@app.get("/projects/{project_id}/members")
def members_page(project_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    auth.require_admin(db, project_id, user)  # 403 if not admin

    project = db.query(models.Project).get(project_id)
    members = db.query(models.ProjectMembership).filter_by(project_id=project_id).all()

    return templates.TemplateResponse(
        "members.html", {"request": request, "user": user, "project": project, "members": members, "error": None}
    )


@app.post("/projects/{project_id}/members/add")
def add_member(
    project_id: int,
    request: Request,
    email: str = Form(...),
    role: str = Form("member"),
    db: Session = Depends(get_db),
):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    auth.require_admin(db, project_id, user)

    target = db.query(models.User).filter_by(email=email).first()
    project = db.query(models.Project).get(project_id)
    members = db.query(models.ProjectMembership).filter_by(project_id=project_id).all()

    if not target:
        return templates.TemplateResponse(
            "members.html",
            {
                "request": request, "user": user, "project": project, "members": members,
                "error": f"No account found with email {email}. They need to register first.",
            },
        )

    existing = auth.get_membership(db, project_id, target.id)
    if existing:
        return templates.TemplateResponse(
            "members.html",
            {"request": request, "user": user, "project": project, "members": members,
             "error": f"{target.name} is already a member."},
        )

    db.add(models.ProjectMembership(project_id=project_id, user_id=target.id, role=models.Role(role)))
    db.commit()

    return RedirectResponse(f"/projects/{project_id}/members", status_code=303)


@app.post("/projects/{project_id}/members/{member_user_id}/remove")
def remove_member(project_id: int, member_user_id: int, request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    auth.require_admin(db, project_id, user)

    membership = auth.get_membership(db, project_id, member_user_id)
    if membership:
        db.delete(membership)
        db.commit()

    return RedirectResponse(f"/projects/{project_id}/members", status_code=303)
