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
    import stripe as stripe_lib
    print("STEP1d stripe OK", flush=True)
    from flask import Flask, request, redirect, jsonify, render_template
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
print("STEP4 app alive V2", flush=True)
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
    upgrade_msg = request.args.get("upgrade", "")
    return render_template("dashboard.html", plan=plan, user=user, repos=repos_data, upgrade_msg=upgrade_msg)
@app.route("/api/repos", methods=["POST"])
def add_repo():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json() or {}
    repo = Repo(user_id=current_user.id, full_name=data.get("full_name",""), branch=data.get("branch","main"))
    db.session.add(repo)
    db.session.commit()
    return jsonify({"ok": True})
@app.route("/api/repos/<int:repo_id>", methods=["DELETE"])
def delete_repo(repo_id):
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    repo = db.session.execute(db.select(Repo).where(Repo.id == repo_id, Repo.user_id == current_user.id)).scalar_one_or_none()
    if not repo:
        return jsonify({"error": "Repo not found"}), 404
    db.session.delete(repo)
    db.session.commit()
    return jsonify({"ok": True})
@app.route("/upgrade/<plan>")
def upgrade(plan):
    stripe_key = app.config.get("STRIPE_SECRET_KEY", "")
    plans = {
        "individual": {"name": "MergeFlow Individual", "amount": 2900, "interval": "month"},
        "team": {"name": "MergeFlow Team", "amount": 9900, "interval": "month"},
    }
    cfg = plans.get(plan, plans["individual"])
    if not stripe_key:
        return "Stripe not configured.", 503
    try:
        import stripe
        stripe.api_key = stripe_key
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": cfg["name"]},
                    "unit_amount": cfg["amount"],
                    "recurring": {"interval": cfg["interval"]},
                },
                "quantity": 1,
            }],
            success_url="https://mergeflow-pr.onrender.com/dashboard?upgrade=success",
            cancel_url="https://mergeflow-pr.onrender.com/dashboard?upgrade=cancelled",
        )
        return redirect(session.url)
    except Exception as e:
        return f"Stripe error: {str(e)}", 500
@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    try:
        event = request.get_json()
        print(f"Stripe webhook: {event.get('type')}", flush=True)
        if event.get("type") == "checkout.session.completed":
            session = event["data"]["object"]
            customer_email = session.get("customer_details", {}).get("email")
            if customer_email:
                user = db.session.execute(db.select(User).where(User.email == customer_email)).scalar_one_or_none()
                if user:
                    plan = "paid"
                    user.plan = plan
                    db.session.commit()
                    print(f"Upgraded user {customer_email} to {plan}", flush=True)
        return jsonify({"ok": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
@app.route("/webhook/marketplace", methods=["POST"])
def marketplace_webhook():
    event = request.get_json()
    action = event.get("action", "")
    print(f"Marketplace webhook: {action}", flush=True)
    return jsonify({"ok": True})
@app.route("/logout")
def logout():
    logout_user()
    return redirect("/")
print("STEP5", flush=True)
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    print("STARTING SERVER", flush=True)
    app.run(host="0.0.0.0", port=8000)
