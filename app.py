#!/usr/bin/env python3
import sys, os
sys.stderr = sys.stdout
print("STEP1", flush=True)
try:
    import json, uuid, subprocess
    from datetime import datetime
    print("STEP1b stdlib OK", flush=True)
    import httpx
    print("STEP1c httpx OK", flush=True)
    from flask import Flask, request, redirect, jsonify, render_template_string, abort
    print("STEP1d flask OK", flush=True)
    from flask_sqlalchemy import SQLAlchemy
    print("STEP1e sqlalchemy OK", flush=True)
    from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
    print("STEP1f flask-login OK", flush=True)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"IMPORT FAILED: {e}", flush=True)
    sys.exit(1)
print("STEP2", flush=True)
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["GITHUB_CLIENT_ID"] = os.getenv("GITHUB_CLIENT_ID", "")
app.config["GITHUB_CLIENT_SECRET"] = os.getenv("GITHUB_CLIENT_SECRET", "")
app.config["STRIPE_SECRET_KEY"] = os.getenv("STRIPE_SECRET_KEY", "")
print(f"DB={bool(app.config.get('SQLALCHEMY_DATABASE_URI'))}", flush=True)
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
print("STEP3", flush=True)
class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    github_username = db.Column(db.String(255))
    plan = db.Column(db.String(50), default="free")
class Repo(db.Model):
    __tablename__ = "repos"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    branch = db.Column(db.String(100), default="main")
    auto_merge_enabled = db.Column(db.Boolean, default=True)
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
print("STEP4 app alive", flush=True)
@app.route("/healthz")
def health():
    return jsonify({"status": "ok"})
@app.route("/")
def root():
    return render_template("landing.html")
@app.route("/login")
def login():
    cid = app.config.get("GITHUB_CLIENT_ID", "")
    return redirect("https://github.com/login/oauth/authorize?client_id=" + cid + "&scope=repo,admin:repo_hook")
@app.route("/github/callback")
def oauth_callback():
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Missing OAuth code"}), 400
    try:
        resp = httpx.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": app.config["GITHUB_CLIENT_ID"],
                "client_secret": app.config["GITHUB_CLIENT_SECRET"],
                "code": code,
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        token_data = resp.json()
        token = token_data.get("access_token")
        if not token:
            return jsonify({"error": "No access token from GitHub", "detail": token_data}), 400
        gh_resp = httpx.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        gh_user = gh_resp.json()
        login_name = gh_user.get("login") or gh_user.get("name", "unknown")
        email = gh_user.get("email") or f"{login_name}@users.noreply.github.com"
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
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
@app.route("/dashboard")
def dashboard():
    if not current_user.is_authenticated:
        return redirect("/login")
    repos = db.session.execute(db.select(Repo).where(Repo.user_id == current_user.id)).scalars().all()
    plan = current_user.plan or "Free Trial"
    user = current_user.github_username or current_user.email
    repos_data = [{"name": r.full_name, "branch": r.branch, "enabled": r.auto_merge_enabled, "id": r.id} for r in repos]
    html = render_template("dashboard.html", plan=plan, user=user, repos=repos_data)
    return html
@app.route("/api/repos", methods=["POST"])
def add_repo():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json() or {}
    repo = Repo(user_id=current_user.id, full_name=data.get("full_name",""), branch=data.get("branch","main"))
    db.session.add(repo)
    db.session.commit()
@app.route("/webhook/marketplace", methods=["POST"])
def marketplace_webhook():
    event = request.get_json()
    action = event.get("action", "")
    if action in ("purchased", "cancelled", "changed"):
        print(f"Marketplace webhook: {action}", flush=True)
    return jsonify({"ok": True})


    return jsonify({"ok": True})
print("STEP5", flush=True)

DASHBOARD_TMPL = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>MergeFlow</title><style>body{font-family:-apple-system,sans-serif;max-width:860px;margin:0 auto;padding:40px 20px;background:#0d1117;color:#c9d1d9}a{color:#58a6ff}a:hover{text-decoration:underline}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:32px;padding-bottom:20px;border-bottom:1px solid #30363d}.logo{font-size:1.5em;font-weight:700;color:#58a6ff}.right{display:flex;gap:8px;align-items:center}.badge{background:rgba(56,139,253,0.2);color:#58a6ff;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600}.btn{background:#21262d;color:#c9d1d9;padding:6px 14px;border-radius:6px;font-size:13px;border:none;cursor:pointer;display:inline-block;text-decoration:none}.btn:hover{background:#30363d}.logout{background:#da3633;color:white}.logout:hover{background:#f85149}.upg-banner{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px 18px;margin-bottom:28px;display:flex;justify-content:space-between;align-items:center;gap:12px}.upg-banner h3{color:#58a6ff;font-size:14px;margin:0 0 2px}.upg-banner p{color:#8b949e;font-size:13px;margin:0}.upg-btn{background:#238636;color:white;padding:8px 18px;border-radius:6px;font-size:13px;font-weight:600;text-decoration:none}.upg-btn:hover{background:#2ea043;text-decoration:none}.section-title{color:#8b949e;font-size:11px;text-transform:uppercase;margin-bottom:8px}.t{width:100%;border-collapse:collapse;margin-bottom:28px}.t th{text-align:left;padding:8px 12px;color:#6e7681;font-size:11px;text-transform:uppercase;border-bottom:1px solid #21262d}.t td{padding:10px 12px;border-bottom:1px solid #21262d;font-size:14px}.t tr:hover td{background:#161b22}.on{background:rgba(35,134,54,0.25);color:#3fb950;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600}.off{background:rgba(218,54,51,0.15);color:#f85149;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600}.del{background:rgba(218,54,51,0.15);color:#f85149;padding:4px 10px;border-radius:6px;border:none;cursor:pointer;font-size:12px}.del:hover{background:rgba(218,54,51,0.3)}.empty{text-align:center;padding:44px;background:#161b22;border:1px solid #30363d;border-radius:8px;margin-bottom:28px}.empty h3{color:#8b949e;margin:0 0 6px;font-size:15px}.empty p{color:#6e7681;font-size:13px;margin:0}.add-box{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:18px;margin-bottom:24px}.add-box h3{color:#c9d1d9;margin:0 0 14px;font-size:14px}.form-row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}.fld{display:flex;flex-direction:column;gap:3px}.fld label{font-size:11px;color:#6e7681}.fld input{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:7px 10px;color:#c9d1d9;font-size:13px;width:200px}.fld input:focus{outline:none;border-color:#58a6ff}.sub{background:#238636;color:white;border:none;padding:8px 18px;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600;height:34px}.sub:hover{background:#2ea043}.footer{text-align:center;color:#484f58;font-size:11px;padding
