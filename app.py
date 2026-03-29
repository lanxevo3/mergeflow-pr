#!/usr/bin/env python3
import sys, os, secrets
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
    from flask import Flask, request, redirect, jsonify, render_template, session
    print("STEP1e flask OK", flush=True)
    from flask_sqlalchemy import SQLAlchemy
    print("STEP1f sqlalchemy OK", flush=True)
    from flask_login import LoginManager, UserMixin, login_user, logout_user
    print("STEP1g flask-login OK", flush=True)
except Exception as e:
    import traceback; traceback.print_exc()
    print(f"IMPORT FAILED: {e}", flush=True)
    sys.exit(1)
print("STEP2", flush=True)
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", secrets.token_hex(32))
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["GITHUB_CLIENT_ID"] = os.getenv("GITHUB_CLIENT_ID", "")
app.config["GITHUB_CLIENT_SECRET"] = os.getenv("GITHUB_CLIENT_SECRET", "")
app.config["STRIPE_SECRET_KEY"] = os.getenv("STRIPE_SECRET_KEY", "")
app.config["STRIPE_WEBHOOK_SECRET"] = os.getenv("STRIPE_WEBHOOK_SECRET", "")
app.config["ADMIN_SECRET"] = os.getenv("ADMIN_SECRET", "")
app.config["MARKETPLACE_WEBHOOK_SECRET"] = os.getenv("MARKETPLACE_WEBHOOK_SECRET", "")
app.config["FREE_REPO_LIMIT"] = 3
print(f"DB={bool(app.config.get('SQLALCHEMY_DATABASE_URI'))}", flush=True)
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
print("STEP3", flush=True)
class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    github_username = db.Column(db.String(255))
    plan = db.Column(db.String(50), default="free")
    stripe_customer_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class Repo(db.Model):
    __tablename__ = "repos"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    full_name = db.Column(db.String(255), nullable=False)
    branch = db.Column(db.String(100), default="main")
    auto_merge_enabled = db.Column(db.Boolean, default=True)
    min_approvals = db.Column(db.Integer, default=1)
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
def get_user_plan(user):
    return user.plan or "Free Trial"
def is_free_user(user):
    return user.plan in (None, "free", "Free Trial")
def can_add_repo(user):
    if is_free_user(user):
        count = db.session.execute(
            db.select(db.func.count()).select_from(Repo).where(Repo.user_id == user.id)
        ).scalar()
        return count < 3
    return True
print("STEP4 app alive V6_HARDENED", flush=True)
@app.route("/healthz")
def health():
    return jsonify({"status": "ok"})
@app.route("/")
def root():
    return render_template("landing.html")
@app.route("/login")
def login():
    state = secrets.token_hex(16)
    session["oauth_state"] = state
    cid = app.config.get("GITHUB_CLIENT_ID", "")
    return redirect(f"https://github.com/login/oauth/authorize?client_id={cid}&scope=repo,admin:repo_hook&state={state}")
@app.route("/github/callback")
def oauth_callback():
    stored_state = session.pop("oauth_state", None)
    incoming_state = request.args.get("state")
    if not stored_state or stored_state != incoming_state:
        return jsonify({"error": "Invalid OAuth state - possible CSRF attack"}), 400
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
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
@app.route("/dashboard")
def dashboard():
    from flask_login import current_user
    if not current_user.is_authenticated:
        return redirect("/login")
    repos = db.session.execute(db.select(Repo).where(Repo.user_id == current_user.id)).scalars().all()
    plan = get_user_plan(current_user)
    user = current_user.github_username or current_user.email
    upgrade_msg = request.args.get("upgrade", "")
    repos_data = [{"name": r.full_name, "branch": r.branch, "enabled": r.auto_merge_enabled, "id": r.id, "min_approvals": r.min_approvals} for r in repos]
    return render_template("dashboard.html", plan=plan, user=user, repos=repos_data, upgrade_msg=upgrade_msg)
@app.route("/api/repos", methods=["POST"])
def add_repo():
    from flask_login import current_user
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    if not can_add_repo(current_user):
        return jsonify({"error": "Free plan limited to 3 repos. Upgrade to add more."}), 403
    data = request.get_json() or {}
    full_name = data.get("full_name", "").strip()
    if not full_name or "/" not in full_name:
        return jsonify({"error": "Invalid repo format. Use owner/repo"}), 400
    branch = data.get("branch", "main").strip() or "main"
    min_approvals = int(data.get("min_approvals", 1))
    repo = Repo(user_id=current_user.id, full_name=full_name, branch=branch, min_approvals=min_approvals)
    db.session.add(repo)
    db.session.commit()
    return jsonify({"ok": True, "id": repo.id})
@app.route("/api/repos/<int:repo_id>", methods=["DELETE"])
def delete_repo(repo_id):
    from flask_login import current_user
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
@app.route("/api/repos/<int:repo_id>", methods=["PATCH"])
def update_repo(repo_id):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    repo = db.session.execute(db.select(Repo).where(Repo.id == repo_id, Repo.user_id == current_user.id)).scalar_one_or_none()
    if not repo:
        return jsonify({"error": "Repo not found"}), 404
    data = request.get_json() or {}
    if "branch" in data:
        repo.branch = data["branch"].strip() or "main"
    if "min_approvals" in data:
        repo.min_approvals = max(1, int(data["min_approvals"]))
    if "auto_merge_enabled" in data:
        repo.auto_merge_enabled = bool(data["auto_merge_enabled"])
    db.session.commit()
    return jsonify({"ok": True})
@app.route("/api/repos/<int:repo_id>/toggle", methods=["POST"])
def toggle_repo(repo_id):
    from flask_login import current_user
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
@app.route("/upgrade/<plan>")
def upgrade(plan):
    if plan not in ("individual", "team"):
        return "Invalid plan", 400
    stripe_key = app.config.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        return "Stripe not configured.", 503
    from flask_login import current_user
    plans = {
        "individual": {"name": "MergeFlow Individual", "amount": 2900, "interval": "month"},
        "team": {"name": "MergeFlow Team", "amount": 9900, "interval": "month"},
    }
    cfg = plans[plan]
    try:
        import stripe
        stripe.api_key = stripe_key
        kwargs = {
            "mode": "subscription",
            "line_items": [{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": cfg["name"]},
                    "unit_amount": cfg["amount"],
                    "recurring": {"interval": cfg["interval"]},
                },
                "quantity": 1,
            }],
            "success_url": "https://mergeflow-pr.onrender.com/dashboard?upgrade=success",
            "cancel_url": "https://mergeflow-pr.onrender.com/dashboard?upgrade=cancelled",
        }
        if current_user.is_authenticated:
            kwargs["customer_email"] = current_user.email
        sess = stripe.checkout.Session.create(**kwargs)
        return redirect(sess.url)
    except Exception as e:
        import traceback; traceback.print_exc()
        return f"Stripe error: {str(e)}", 500
def verify_stripe_signature(payload, sig):
    secret = app.config.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        print("WARNING: STRIPE_WEBHOOK_SECRET not set - skipping verification", flush=True)
        return None
    import stripe
    stripe.api_key = app.config.get("STRIPE_SECRET_KEY", "")
    try:
        return stripe.Webhook.construct_event(payload, sig, secret)
    except Exception as e:
        print(f"Stripe signature verification failed: {e}", flush=True)
        return None
@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    try:
        payload = request.get_data()
        sig = request.headers.get("Stripe-Signature", "")
        event = verify_stripe_signature(payload, sig)
        if event is None and app.config.get("STRIPE_WEBHOOK_SECRET"):
            return jsonify({"error": "Invalid signature"}), 400
        event_type = event.get("type", "") if event else request.get_json().get("type", "unknown")
        print(f"Stripe webhook: {event_type}", flush=True)
        if event and event_type == "checkout.session.completed":
            session_obj = event["data"]["object"]
            customer_email = session_obj.get("customer_details", {}).get("email")
            customer_id = session_obj.get("customer")
            if not customer_email and customer_id:
                try:
                    import stripe
                    stripe.api_key = app.config.get("STRIPE_SECRET_KEY", "")
                    cu = stripe.Customer.retrieve(customer_id)
                    customer_email = cu.get("email")
                except Exception as ex:
                    print(f"Could not retrieve Stripe customer: {ex}", flush=True)
            if customer_email:
                user = db.session.execute(
                    db.select(User).where(User.email == customer_email)
                ).scalar_one_or_none()
                if user:
                    if customer_id and not user.stripe_customer_id:
                        user.stripe_customer_id = customer_id
                    user.plan = "paid"
                    db.session.commit()
                    print(f"Upgraded user {customer_email} to paid", flush=True)
        elif event and event_type == "customer.subscription.deleted":
            sub = event["data"]["object"]
            cust_id = sub.get("customer")
            if cust_id:
                user = db.session.execute(db.select(User).where(User.stripe_customer_id == cust_id)).scalar_one_or_none()
                if user:
                    user.plan = "free"
                    db.session.commit()
                    print(f"Downgraded user {user.email} to free", flush=True)
        return jsonify({"ok": True})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
@app.route("/webhook/marketplace", methods=["POST"])
def marketplace_webhook():
    try:
        event = request.get_json()
        action = event.get("action", "")
        mp = event.get("marketplace_purchase", {})
        purchase = mp.get("purchase", {})
        email = purchase.get("email")
        account_login = purchase.get("account_login") or (event.get("marketplace_purchase", {}).get("account") or {}).get("login")
        print(f"Marketplace webhook: action={action} login={account_login} email={email}", flush=True)
        if action in ("purchased", "free_trial_started"):
            if not email and account_login:
                email = f"{account_login}@users.noreply.github.com"
            if email:
                user = db.session.execute(
                    db.select(User).where(User.email == email)
                ).scalar_one_or_none()
                if user:
                    user.plan = "paid"
                    db.session.commit()
                    print(f"Marketplace: upgraded {email} to paid", flush=True)
        elif action in ("cancelled", "pending_cancellation"):
            if not email and account_login:
                email = f"{account_login}@users.noreply.github.com"
            if email:
                user = db.session.execute(
                    db.select(User).where(User.email == email)
                ).scalar_one_or_none()
                if user:
                    user.plan = "free"
                    db.session.commit()
                    print(f"Marketplace: downgraded {email} to free", flush=True)
        elif action == "plan_changed":
            print(f"Marketplace plan_changed: {mp}", flush=True)
        return jsonify({"ok": True})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500
@app.route("/logout")
def logout():
    logout_user()
    return redirect("/")

# TEMP TEST ROUTE - simulates a successful Stripe purchase for testing
# Remove after confirming the upgrade flow works
@app.route("/test-simulate-upgrade")
def test_simulate_upgrade():
    email = request.args.get("email", "test@example.com")
    user = db.session.execute(db.select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        user = User(email=email, github_username="testuser", plan="free")
        db.session.add(user)
        db.session.commit()
    old_plan = user.plan
    user.plan = "paid"
    user.stripe_customer_id = "cus_test_" + secrets.token_hex(8)
    db.session.commit()
    login_user(user)
    return jsonify({
        "ok": True,
        "email": email,
        "old_plan": old_plan,
        "new_plan": user.plan,
        "stripe_customer_id": user.stripe_customer_id
    })
def get_github_prs(owner, repo_name):
    try:
        import urllib.request
        token = app.config.get("GITHUB_CLIENT_SECRET", "")
        req = urllib.request.Request(
            "https://api.github.com/repos/" + owner + "/" + repo_name + "/pulls?state=open&per_page=20",
            headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github.v3+json"}
        )
        resp = urllib.request.urlopen(req, timeout=10)
        import json as _json
        return [
            {"number": p["number"], "title": (p.get("title") or "")[:80],
             "author": (p.get("user") or {}).get("login", "?"),
             "draft": p.get("draft", False), "url": p.get("html_url", "")}
            for p in _json.loads(resp.read())
        ]
    except Exception as e:
        print("GitHub API error: " + str(e), flush=True)
        return []

@app.route("/admin/api")
def admin_api():
    try:
        admin_key = app.config.get("ADMIN_SECRET", "")
        provided = request.args.get("key", "")
        if admin_key and provided != admin_key:
            return jsonify({"error": "Unauthorized - provide ?key=ADMIN_SECRET"}), 403
        users = db.session.execute(db.select(User).order_by(User.created_at.desc())).scalars().all()
        paid = [u for u in users if u.plan == "paid"]
        result = {
            "summary": {"total_users": len(users), "paid_users": len(paid), "free_users": len(users) - len(paid)},
            "alerts": [],
            "users": []
        }
        for u in users:
            repos = db.session.execute(db.select(Repo).where(Repo.user_id == u.id)).scalars().all()
            user_repos = []
            for r in repos:
                parts = r.full_name.split("/") if "/" in r.full_name else ["?", r.full_name]
                prs = get_github_prs(parts[0], parts[1])
                ready = [p for p in prs if not p.get("draft")]
                if ready:
                    result["alerts"].append({
                        "user_email": u.email, "user_github": u.github_username,
                        "repo": r.full_name, "plan": u.plan or "free", "prs": ready
                    })
                user_repos.append({
                    "id": r.id, "full_name": r.full_name, "branch": r.branch or "main",
                    "enabled": bool(r.auto_merge_enabled), "min_approvals": r.min_approvals or 1,
                    "open_prs": len(prs), "prs_ready": len(ready), "prs": prs[:8]
                })
            result["users"].append({
                "id": u.id, "email": u.email, "github": u.github_username,
                "plan": u.plan or "free", "stripe_id": u.stripe_customer_id or None,
                "created": u.created_at.strftime("%Y-%m-%d") if u.created_at else None,
                "repos": user_repos
            })
        return jsonify(result)
    except Exception as e:
        print(f"admin_api error: {e}", flush=True)
        return jsonify({"error": "internal", "detail": str(e)}), 500

print("STEP5", flush=True)
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        # Safely add stripe_customer_id column to existing users table
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(255)"))
            db.session.commit()
            print("DB: added stripe_customer_id column", flush=True)
        except Exception:
            db.session.rollback()
            print("DB: stripe_customer_id column already exists (OK)", flush=True)
        try:
            db.session.execute(db.text("ALTER TABLE repos ADD COLUMN min_approvals INTEGER DEFAULT 1"))
            db.session.commit()
            print("DB: added min_approvals column", flush=True)
        except Exception:
            db.session.rollback()
            print("DB: min_approvals column already exists (OK)", flush=True)
    print("STARTING SERVER", flush=True)
    app.run(host="0.0.0.0", port=8000)