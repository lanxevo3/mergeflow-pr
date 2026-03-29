#!/usr/bin/env python3
"""MergeFlow - GitHub PR Auto-Merge SaaS API (Flask)"""
import json, os, uuid, subprocess, sys
from datetime import datetime, timedelta

import httpx
from flask import Flask, request, redirect, jsonify, make_response, render_template, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

app = Flask(__name__)
app.config.from_object("config")

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

_sessions = {}

# ─── Models ───────────────────────────────────────────────────────────────────

class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    github_username = db.Column(db.String(255))
    plan = db.Column(db.String(50), default="free")
    stripe_customer_id = db.Column(db.String(255))

class Repo(db.Model):
    __tablename__ = "repos"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    branch = db.Column(db.String(100), default="main")
    min_approvals = db.Column(db.Integer, default=1)
    auto_merge_enabled = db.Column(db.Boolean, default=True)

class MergeLog(db.Model):
    __tablename__ = "merge_logs"
    id = db.Column(db.Integer, primary_key=True)
    repo_id = db.Column(db.Integer, db.ForeignKey("repos.id"), nullable=False)
    pr_number = db.Column(db.Integer)
    status = db.Column(db.String(50))
    merged_at = db.Column(db.DateTime, default=datetime.utcnow)
    error_message = db.Column(db.Text)

# ─── Login Manager ────────────────────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/healthz")
def health():
    return jsonify({"status": "ok"})

@app.route("/")
def root():
    return render_template("landing.html")

@app.route("/login")
def login():
    client_id = app.config.get("GITHUB_CLIENT_ID")
    if not client_id:
        return jsonify({"error": "GitHub OAuth not configured"}), 500
    scope = "repo,admin:repo_hook"
    return redirect(f"https://github.com/login/oauth/authorize?client_id={client_id}&scope={scope}")

@app.route("/github/callback")
def oauth_callback():
    code = request.args.get("code") or request.form.get("code")
    if not code:
        abort(400, "Missing OAuth code")

    # Exchange code for access token
    resp = httpx.post(
        "https://github.com/login/oauth/access_token",
        data={
            "client_id": app.config["GITHUB_CLIENT_ID"],
            "client_secret": app.config["GITHUB_CLIENT_SECRET"],
            "code": code,
        },
        headers={"Accept": "application/json"},
        timeout=10,
    )
    data = resp.json()
    token = data.get("access_token")
    if not token:
        abort(400, "GitHub OAuth failed")

    # Get GitHub user info
    gh = httpx.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=10,
    )
    gh_user = gh.json()
    login_name = gh_user.get("login") or gh_user.get("name", "unknown")
    email = gh_user.get("email") or f"{login_name}@users.noreply.github.com"

    # Find or create user
    user = db.session.execute(
        db.select(User).where(User.email == email)
    ).scalar_one_or_none()

    if not user:
        user = User(email=email, github_username=login_name, plan="free")
        db.session.add(user)
    else:
        user.github_username = login_name

    db.session.commit()
    login_user(user)

    return redirect("/dashboard")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

@app.route("/dashboard")
def dashboard():
    if not current_user.is_authenticated:
        return redirect("/login")
    repos = db.session.execute(
        db.select(Repo).where(Repo.user_id == current_user.id)
    ).scalars().all()
    plan_display = {
        "free": "Free Trial",
        "individual": "Individual — $29/mo",
        "team": "Team — $99/mo",
    }.get(current_user.plan or "free", "Free Trial")
    repos_list = [
        {"id": r.id, "Name": r.full_name, "branch": r.branch, "enabled": r.auto_merge_enabled}
        for r in repos
    ]
    return render_template(
        "dashboard.html",
        user=current_user,
        plan=plan_display,
        repos=repos_list,
    )

@app.route("/api/repos", methods=["POST"])
def add_repo():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json() or {}
    full_name = data.get("full_name")
    branch = data.get("branch", "main")
    min_approvals = int(data.get("min_approvals", 1))
    if not full_name:
        return jsonify({"error": "full_name required"}), 400
    repo_count = db.session.execute(
        db.select(db.func.count()).select_from(Repo).where(Repo.user_id == current_user.id)
    ).scalar()
    if current_user.plan == "free" and repo_count >= 1:
        return jsonify({"error": "Free plan limited to 1 repo. Upgrade at /upgrade/individual"}), 403
    repo = Repo(user_id=current_user.id, full_name=full_name, branch=branch, min_approvals=min_approvals)
    db.session.add(repo)
    db.session.commit()
    return jsonify({"ok": True, "repo": full_name})

@app.route("/api/repos/<int:repo_id>/toggle", methods=["POST"])
def toggle_repo(repo_id):
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    repo = db.session.execute(
        db.select(Repo).where(Repo.id == repo_id, Repo.user_id == current_user.id)
    ).scalar_one_or_none()
    if not repo:
        return jsonify({"error": "Repo not found"}), 404
    repo.auto_merge_enabled = not repo.auto_merge_enabled
    db.session.commit()
    return jsonify({"ok": True, "enabled": repo.auto_merge_enabled})

@app.route("/api/repos/<int:repo_id>", methods=["DELETE"])
def delete_repo(repo_id):
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    repo = db.session.execute(
        db.select(Repo).where(Repo.id == repo_id, Repo.user_id == current_user.id)
    ).scalar_one_or_none()
    if not repo:
        return jsonify({"error": "Repo not found"}), 404
    db.session.delete(repo)
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/upgrade/<plan>")
def upgrade(plan):
    if plan not in ("individual", "team"):
        return jsonify({"error": "Invalid plan"}), 400
    return redirect("https://buy.stripe.com/9RE6oI1Nm4E45pCfZB")

@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    event = json.loads(payload)
    if event.get("type") == "checkout.session.completed":
        customer_id = event["data"]["object"]["customer"]
        plan = event["data"]["object"]["metadata"].get("plan", "individual")
        user = db.session.execute(
            db.select(User).where(User.stripe_customer_id == customer_id)
        ).scalar_one_or_none()
        if user:
            user.plan = plan
            db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/scan/<int:repo_id>", methods=["POST"])
def trigger_scan(repo_id):
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    repo = db.session.execute(
        db.select(Repo).where(Repo.id == repo_id, Repo.user_id == current_user.id)
    ).scalar_one_or_none()
    if not repo:
        return jsonify({"error": "Repo not found"}), 404
    result = subprocess.run(
        ["python", "auto_merge.py", repo.full_name, "--dry-run"],
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    return jsonify({"ok": True, "stdout": result.stdout, "stderr": result.stderr})

# ─── Init DB ──────────────────────────────────────────────────────────────────

with app.app_context():
    try:
        db.create_all()
        app.logger.info("Database tables ready")
    except Exception as e:
        app.logger.warning(f"DB init skipped (may be missing env vars): {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
