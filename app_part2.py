        for r in repos:
            status = "Enabled" if r.auto_merge_enabled else "Paused"
            repos_rows += "<tr>"
            repos_rows += "<td><code>" + r.full_name + "</code></td>"
            repos_rows += "<td>" + r.branch + "</td>"
            repos_rows += "<td>" + str(r.min_approvals) + "</td>"
            repos_rows += "<td>" + status + "</td>"
            repos_rows += "<td><a href=\"/api/repos/" + r.id + "/toggle\">Toggle</a></td>"
            repos_rows += "</tr>"

    logs_rows = ""
    for log in logs:
        icon = "merged" if log.action == "merged" else "skipped" if "skip" in log.action else "error"
        logs_rows += "<tr>"
        logs_rows += "<td>" + log.created_at.strftime("%Y-%m-%d %H:%M") + "</td>"
        logs_rows += "<td>#" + str(log.pr_number) + "</td>"
        logs_rows += "<td>" + icon + "</td>"
        logs_rows += "<td>" + (log.reason or "") + "</td>"
        logs_rows += "</tr>"

    repos_table = "<tr><th>Repo</th><th>Branch</th><th>Min Approvals</th><th>Status</th><th>Action</th></tr>"
    if not repos:
        repos_table += "<tr><td colspan=\"5\">No repos added yet.</td></tr>"
    else:
        repos_table += repos_rows

    logs_table = "<tr><th>Date</th><th>PR</th><th>Action</th><th>Reason</th></tr>"
    if not logs:
        logs_table += "<tr><td colspan=\"4\">No activity yet.</td></tr>"
    else:
        logs_table += logs_rows

    html = (
        "<!DOCTYPE html><html><head><title>MergeFlow Dashboard</title>"
        "<style>body{font-family:-apple-system,sans-serif;margin:20px;background:#0d1117;color:#e6edf3}"
        "h1{color:#58a6ff}h2{color:#8b949e}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}"
        "th,td{border:1px solid #30363d;padding:8px;text-align:left}"
        "th{background:#161b22;color:#58a6ff}a{color:#58a6ff}</style></head>"
        "<body>"
        "<h1>MergeFlow Dashboard</h1>"
        "<p>Logged in as " + (user.github_username or user.email) + " &mdash; <strong>" + plan_display + "</strong></p>"
        "<h2>Repositories</h2>"
        "<table>" + repos_table + "</table>"
        "<h3>Add Repository</h3>"
        "<form method=\"post\" action=\"/api/repos\">"
        "<input name=\"full_name\" placeholder=\"owner/repo\" required style=\"width:200px\"> "
        "<input name=\"branch\" value=\"main\" style=\"width:100px\"> "
        "<input name=\"min_approvals\" type=\"number\" value=\"1\" min=\"0\" style=\"width:60px\"> "
        "<button type=\"submit\">Add</button></form>"
        "<h2>Recent Activity</h2>"
        "<table>" + logs_table + "</table>"
        "</body></html>"
    )
    return html

@app.post("/api/repos")
async def add_repo(request: Request, full_name: str = Form(...), branch: str = Form("main"), min_approvals: int = Form(1), db: Session = Depends(get_db)):
    user = get_user(get_session_id(request), db)
    if not user:
        raise HTTPException(401, "Not authenticated")
    repo_count = len(db.exec(select(Repo).where(Repo.user_id == user.id)).all())
    if user.plan == "free" and repo_count >= 1:
        raise HTTPException(403, "Free plan limited to 1 repo. Upgrade to Individual for unlimited.")
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
