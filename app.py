#!/usr/bin/env python3
"""MergeFlow - GitHub PR Auto-Merge SaaS API"""
import json, os, uuid
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, create_engine, select

from config import settings
from models import User, Repo, MergeLog

engine = create_engine(settings.database_url, echo=False)

def get_db():
    with Session(engine) as session:
        yield session

app = FastAPI(title="MergeFlow", version="1.0.0")
_sessions = {}

def get_session_id(request: Request) -> Optional[str]:
    return request.cookies.get("session_id")

def get_user(session_id: Optional[str] = None, db: Session = Depends(get_db)) -> Optional[User]:
    if not session_id:
        return None
    s = _sessions.get(session_id)
    if not s or s["expires"] < datetime.utcnow():
        _sessions.pop(session_id, None)
        return None
    return db.get(User, s["user_id"])

@app.get("/healthz")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    with open("templates/landing.html") as f:
        return HTMLResponse(content=f.read())

@app.get("/login")
async def login():
    client_id = settings.github_client_id
    if not client_id:
        return {"error": "GitHub OAuth not configured"}
    scope = "repo,admin:repo_hook"
    url = "https://github.com/login/oauth/authorize?client_id=" + client_id + "&scope=" + scope
    return RedirectResponse(url=url, status_code=302)

@app.get("/oauth/callback")
async def oauth_callback(code: str = Form(...), db: Session = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={"client_id": settings.github_client_id, "client_secret": settings.github_client_secret, "code": code},
            headers={"Accept": "application/json"},
        )
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise HTTPException(400, "GitHub OAuth failed")
    async with httpx.AsyncClient() as client:
        gh = await client.get("https://api.github.com/user", headers={"Authorization": "Bearer " + token})
    gh_user = gh.json()
    login_name = gh_user["login"]
    email = gh_user.get("email") or (login_name + "@users.noreply.github.com")
    user = db.exec(select(User).where(User.email == email)).first()
    if not user:
        user = User(email=email, github_username=login_name, plan="free")
        db.add(user)
    else:
        user.github_username = login_name
    db.commit()
    db.refresh(user)
    sid = str(uuid.uuid4())
    _sessions[sid] = {"user_id": user.id, "expires": datetime.utcnow() + timedelta(hours=settings.session_lifetime_hours)}
    resp = RedirectResponse(url="/dashboard", status_code=302)
    resp.set_cookie(key="session_id", value=sid, httponly=True, samesite="lax", max_age=settings.session_lifetime_hours * 3600)
    return resp

@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_user(get_session_id(request), db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    repos = db.exec(select(Repo).where(Repo.user_id == user.id)).all()
    plan_display = {"free": "Free Trial", "individual": "Individual 29/mo", "team": "Team 99/mo"}.get(user.plan or "free", "Free Trial")
    repos_list = [{"name": r.full_name, "branch": r.branch, "enabled": r.auto_merge_enabled} for r in repos]
    return {"user": user.github_username or user.email, "plan": plan_display, "repos": repos_list}

@app.post("/api/repos")
async def add_repo(request: Request, full_name: str = Form(...),
    branch: str = Form("main"),
    min_approvals: int = Form(1),
    db: Session = Depends(get_db)
):
    user = get_user(get_session_id(request), db)
    if not user:
        raise HTTPException(401, "Not authenticated")
    repo_count = len(db.exec(select(Repo).where(Repo.user_id == user.id)).all())
    if user.plan == "free" and repo_count >= 1:
        raise HTTPException(403, "Free plan limited to 1 repo. Upgrade at /upgrade/individual")
    repo = Repo(user_id=user.id, full_name=full_name, branch=branch, min_approvals=min_approvals)
    db.add(repo)
    db.commit()
    return {"ok": True, "repo": full_name}

@app.get("/api/repos/{repo_id}/toggle")
async def toggle_repo(repo_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_user(get_session_id(request), db)
    if not user:
        raise HTTPException(401, "Not authenticated")
    repo = db.exec(select(Repo).where(Repo.id == repo_id, Repo.user_id == user.id)).first()
    if not repo:
        raise HTTPException(404, "Repo not found")
    repo.auto_merge_enabled = not repo.auto_merge_enabled
    db.commit()
    return {"ok": True, "enabled": repo.auto_merge_enabled}

@app.get("/upgrade/{plan}")
async def upgrade(plan: str):
    if plan not in ("individual", "team"):
        raise HTTPException(400, "Invalid plan")
    return RedirectResponse(url="https://buy.stripe.com/9RE6oI1Nm4E45pCfZB", status_code=302)

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    event = json.loads(payload)
    if event.get("type") == "checkout.session.completed":
        customer_id = event["data"]["object"]["customer"]
        plan = event["data"]["object"]["metadata"].get("plan", "individual")
        user = db.exec(select(User).where(User.stripe_customer_id == customer_id)).first()
        if user:
            user.plan = plan
            db.commit()
    return {"ok": True}

@app.get("/api/scan/{repo_id}")
async def trigger_scan(repo_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_user(get_session_id(request), db)
    if not user:
        raise HTTPException(401, "Not authenticated")
    repo = db.exec(select(Repo).where(Repo.id == repo_id, Repo.user_id == user.id)).first()
    if not repo:
        raise HTTPException(404, "Repo not found")
    import subprocess, os as os_module
    result = subprocess.run(
        ["python", "auto_merge.py", repo.full_name, "--dry-run"],
        capture_output=True, text=True,
        cwd=os_module.path.dirname(os_module.path.abspath(__file__))
    )
    return {"ok": True, "stdout": result.stdout, "stderr": result.stderr}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
