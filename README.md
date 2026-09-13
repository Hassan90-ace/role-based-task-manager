# TaskFlow — Role-Based Task Manager

A Trello/Jira-style project management tool where teams have roles.
Each project has its own members, and only Admins can manage who's on the team —
Members can create and move tasks but can't add/remove people.

This is a leveled-up version of the role-based login systems built for
coursework (Java/C#/Python + SQLite): same core idea — authenticate a user,
check their role, restrict what they can do — but now as a real deployed
web app with a database-backed permission model instead of a single
hardcoded login screen.

## Features

- **Auth**: register/login with hashed passwords (bcrypt), session cookies
- **Multiple projects**, each with its own independent team and roles
- **Two roles per project**: Admin (can manage members) and Member (can't)
- **Kanban board**: To Do / In Progress / Done columns, move tasks between them
- **Task assignment** to specific team members, with due dates

## Tech stack

- **Backend**: Python + FastAPI
- **Templates**: Jinja2 (server-rendered HTML — no separate frontend build step)
- **Database**: SQLite via SQLAlchemy
- **Auth**: bcrypt password hashing + signed session cookies (Starlette SessionMiddleware)

## Setup

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# open .env and set SESSION_SECRET to any long random string

uvicorn app.main:app --reload
```

Visit `http://localhost:8000` in your browser.

## How to use it

1. **Register** an account, then **create a project** — you automatically
   become its Admin.
2. **Add tasks** to the board — anyone on the project can do this.
3. **Move tasks** between To Do / In Progress / Done using the buttons on
   each task card.
4. As Admin, go to **Manage Members** to add teammates by email (they need
   to have registered an account first) and set their role.
5. Try logging in as a Member account and notice the "Manage Members" link
   disappears, and the members page returns a 403 if visited directly —
   that's the role check enforced on the backend, not just hidden in the UI.

## Project structure

```
app/
  main.py            # All routes: auth, projects, tasks, members
  models.py           # SQLAlchemy models: User, Project, ProjectMembership, Task
  auth.py              # Password hashing, session helpers, admin-check
  db.py                # SQLite setup
  templates/           # Jinja2 HTML templates (server-rendered, no JS framework)
  static/style.css     # All styling
```

## Why role checks happen on the backend, not just the frontend

Hiding the "Manage Members" button for non-admins is a UI nicety, but it's
not security — anyone could still type the URL directly. That's why every
admin-only route in `main.py` calls `auth.require_admin(...)`, which checks
the database and returns a 403 error regardless of what the UI shows. This
is the same principle as the multi-language role-based login systems this
project is built on top of.

## Roadmap / ideas to extend

- Task comments / activity log
- Email invitations instead of "must already have an account"
- Due-date reminders
- Drag-and-drop reordering (would need a bit of JavaScript)
- Deploy live on Render/Railway for a link you can put directly on your resume
