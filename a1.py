pf = r"C:\Users\lanxe\Singularity\external\openclaw_fresh\workspace\pr-merge-saas\app.py"
c = open(pf, "r", encoding="utf-8").read()
marker = 'print("STEP5", flush=True)'
idx = c.find(marker)
if idx == -1:
    print("Marker not found!")
else:
    inject = '''
def get_github_prs(owner, repo_name):
    try:
        token = app.config.get("GITHUB_CLIENT_SECRET", "")
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
        resp = httpx.get(
            "https://api.github.com/repos/" + owner + "/" + repo_name + "/pulls?state=open&per_page=20",
            headers=headers, timeout=10
        )
        if resp.status_code != 200:
            return []
        return [
            {"number": p["number"], "title": p.get("title", "")[:80],
             "author": p.get("user", {}).get("login", "?"),
             "draft": p.get("draft", False), "url": p.get("html_url", "")}
            for p in resp.json()
        ]
    except Exception as e:
        print(f"GitHub API error: {e}", flush=True)
        return []

@app.route("/admin/api")
def admin_api():
    admin_key = app.config.get("ADMIN_SECRET", "")
    provided = request.args.get("key", "")
    if admin_key and provided != admin_key:
        return jsonify({"error": "Unauthorized"}), 403
    users = db.session.execute(db.select(User).order_by(User.created_at.desc())).scalars().all()
    paid = [u for u in users if u.plan == "paid"]
    result = {
        "summary": {"total_users": len(users), "paid_users": len(paid), "free_users": len(users) - len(paid)},
        "users": []
    }
    for u in users:
        repos = db.session.execute(db.select(Repo).where(Repo.user_id == u.id)).scalars().all()
        user_repos = []
        for r in repos:
            parts = r.full_name.split("/") if "/" in r.full_name else ["?", r.full_name]
            prs = get_github_prs(parts[0], parts[1])
            ready = [p for p in prs if not p.get("draft")]
            user_repos.append({
                "id": r.id, "full_name": r.full_name, "branch": r.branch,
                "enabled": r.auto_merge_enabled, "min_approvals": r.min_approvals,
                "open_prs": len(prs), "prs_ready": len(ready), "prs": prs[:8]
            })
        result["users"].append({
            "id": u.id, "email": u.email, "github": u.github_username,
            "plan": u.plan or "free", "stripe_id": u.stripe_customer_id or None,
            "created": u.created_at.strftime("%Y-%m-%d") if u.created_at else None,
            "repos": user_repos
        })
    return jsonify(result)
'''
    new_c = c[:idx] + inject + '\n' + c[idx:]
    open(pf, "w", encoding="utf-8").write(new_c)
    print("DONE", len(new_c), "bytes")
