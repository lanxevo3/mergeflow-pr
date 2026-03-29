
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
