@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_user(get_session_id(request), db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    repos = db.exec(select(Repo).where(Repo.user_id == user.id)).all()
    logs = db.exec(
        select(MergeLog)
        .where(MergeLog.user_id == user.id)
        .order_by(MergeLog.created_at.desc())
        .limit(30)
    ).all()

    plan_map = {
        "free": "Free Trial",
        "individual": "Individual $29/mo",
        "team": "Team $99/mo",
    }
    plan_display = plan_map.get(user.plan or "free", "Free Trial")

    repos_html = ""
    for r in repos:
        status = "Enabled" if r.auto_merge_enabled else "Paused"
        toggle_url = f"/api/repos/{r.id}/toggle"
        repos_html += f"""
        <tr>
          <td><code>{r.full_name}</code></td>
          <td>{r.branch}</td>
          <td>{r.min_approvals}</td>
          <td>{status}</td>
          <td><a href=\"{toggle_url}\">Toggle</a></td>
        </tr>"""

    logs_html = ""
    for log in logs:
        icon = "✅" if log.action == "merged" else "⏭" if "skip" in log.action else "❌"
        logs_html += f"""
        <tr>
          <td>{log.created_at.strftime('%Y-%m-%d %H:%M')}</td>
          <td>#{log.pr_number}</td>
          <td>{icon} {log.action}</td>
          <td>{log.reason or ''}</td>
        </tr>"""

    has_repos = len(repos) > 0
    add_repo_form = """
    <h3>Add Repository</h3>
    <form method="post" action="/api/repos">
      <input name="full_name" placeholder="owner/repo" required style="width:200px">
      <input name="branch" placeholder="main" value="main" style="width:100px">
      <input name="min_approvals" type="number" value="1" min="0" style="width:60px">
      <button type="submit">Add</button>
    </form>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<title>MergeFlow Dashboard</title>
<style>
body{{font-family:-apple-system,sans-serif;margin:0;padding:20px;background:#0d1117;color:#e6edf3}}
h1{{color:#58a6ff}}h2{{color:#8b949e}}
table{{border-collapse:collapse;width:100%;margin:16px 0}}
th,td{{border:1px solid #30363d;padding:8px;text-align:left}}
th{{background:#161b22;color:#58a6ff}}
tr:nth-child(even){{background:#161b22}}
a{{color:#58a6ff}}
.badge{{display:inline-block;background:#238636;padding:2px 8px;border-radius:4px;font-size:0.85em}}
</style>
</head>
<body>
<h1>MergeFlow Dashboard</h1>
<p>Logged in as {user.github_username or user.email} &mdash; <strong>{plan_display}</strong></p>

<h2>Your Repositories</h2>
<table>
<tr><th>Repository</th><th>Branch</th><th>Min Approvals</th><th>Status</th><th>Action</th></tr>
{repos_html or '<tr><td colspan="5">No repos added yet.</td></tr>'}
</table>
{add_repo_form if has_repos or True else ''}

<h2>Recent Activity</h2>
<table>
<tr><th>Date</th><th>PR</th><th>Action</th><th>Reason</th></tr>
{logs_html or '<tr><td colspan="4">No activity yet.</td></tr>'}
</table>
</body>
</html>"""
    return html

# ── API Routes ──────────────────────────────────────────────────────────────