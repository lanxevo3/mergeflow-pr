    return RedirectResponse(url="/dashboard", status_code=302)

@app.get("/upgrade/{plan}")
async def upgrade(plan: str, db: Session = Depends(get_db)):
    stripe_urls = {
        "individual": "https://buy.stripe.com/9RE6oI1Nm4E45pCfZB",
        "team": "https://buy.stripe.com/9RE6oI1Nm4E45pCfZB",
    }
    url = stripe_urls.get(plan)
    if not url:
        raise HTTPException(400, "Invalid plan")
    return RedirectResponse(url=url, status_code=302)

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    # In production: verify signature with stripe_webhook_secret
    event = json.loads(payload)
    if event.get("type") == "checkout.session.completed":
        customer_id = event["data"]["object"]["customer"]
        plan = event["data"]["object"]["metadata"].get("plan", "individual")
        user = db.exec(select(User).where(User.stripe_customer_id == customer_id)).first()
        if user:
            user.plan = plan
            user.stripe_subscription_id = event["data"]["object"].get("subscription")
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
    # Run the auto-merge scan
    import subprocess
    result = subprocess.run(
        ["python", "auto_merge.py", repo.full_name, "--dry-run"],
        capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__))
    )
    return {"ok": True, "output": result.stdout, "errors": result.stderr}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
