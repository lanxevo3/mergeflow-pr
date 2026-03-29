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
    from flask import Flask, request, redirect, jsonify, render_template, abort
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
print("STEP4", flush=True)
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
    return jsonify({"error": "callback stub"}), 500
@app.route("/dashboard")
def dashboard():
    if not current_user.is_authenticated:
        return redirect("/login")
    repos = db.session.execute(db.select(Repo).where(Repo.user_id == current_user.id)).scalars().all()
    return jsonify({"user": current_user.github_username or current_user.email, "repos": [r.full_name for r in repos]})
@app.route("/api/repos", methods=["POST"])
def add_repo():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json() or {}
    repo = Repo(user_id=current_user.id, full_name=data.get("full_name",""), branch=data.get("branch","main"))
    db.session.add(repo)
    db.session.commit()
    return jsonify({"ok": True})
print("STEP5", flush=True)
if __name__ == "__main__":
    db.create_all()
    app.run(host="0.0.0.0", port=8000)
