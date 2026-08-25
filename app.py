import os
from datetime import datetime, timedelta

from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
import requests

from models import db, User, Project, Task

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///taskmanager_new.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access that page."
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------- Telegram Configuration ----------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

def send_telegram_message(chat_id, message):
    """Send a message via Telegram bot"""
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.ok
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


# ---------- Auth ----------

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username or not password:
            flash("Username and password are required.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif User.query.filter_by(username=username).first():
            flash("That username is already taken.", "error")
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created! Welcome.", "success")
            return redirect(url_for("dashboard"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        flash("Invalid username or password.", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------- Dashboard ----------

@app.route("/")
@login_required
def dashboard():
    projects = (
        Project.query.filter_by(user_id=current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return render_template("dashboard.html", projects=projects)


# ---------- Projects ----------

def get_owned_project_or_404(project_id):
    project = db.session.get(Project, project_id)
    if project is None or project.user_id != current_user.id:
        abort(404)
    return project


@app.route("/projects/new", methods=["POST"])
@login_required
def create_project():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()

    if not name:
        flash("Project name is required.", "error")
        return redirect(url_for("dashboard"))

    project = Project(name=name, description=description, owner=current_user)
    db.session.add(project)
    db.session.commit()
    flash(f'Project "{name}" created.', "success")
    return redirect(url_for("dashboard"))


@app.route("/projects/<int:project_id>")
@login_required
def view_project(project_id):
    project = get_owned_project_or_404(project_id)
    tasks_by_status = {
        "todo": [t for t in project.tasks if t.status == "todo"],
        "doing": [t for t in project.tasks if t.status == "doing"],
        "done": [t for t in project.tasks if t.status == "done"],
    }
    return render_template("project.html", project=project, tasks_by_status=tasks_by_status)


@app.route("/projects/<int:project_id>/edit", methods=["POST"])
@login_required
def edit_project(project_id):
    project = get_owned_project_or_404(project_id)
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()

    if not name:
        flash("Project name is required.", "error")
    else:
        project.name = name
        project.description = description
        db.session.commit()
        flash("Project updated.", "success")

    return redirect(url_for("view_project", project_id=project.id))


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
@login_required
def delete_project(project_id):
    project = get_owned_project_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash(f'Project "{project.name}" deleted.', "success")
    return redirect(url_for("dashboard"))


# ---------- Tasks ----------

def get_owned_task_or_404(task_id):
    task = db.session.get(Task, task_id)
    if task is None or task.project.user_id != current_user.id:
        abort(404)
    return task


@app.route("/projects/<int:project_id>/tasks/new", methods=["POST"])
@login_required
def create_task(project_id):
    project = get_owned_project_or_404(project_id)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    due_date_str = request.form.get("due_date", "").strip()

    if not title:
        flash("Task title is required.", "error")
        return redirect(url_for("view_project", project_id=project.id))

    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid due date.", "error")
            return redirect(url_for("view_project", project_id=project.id))

    task = Task(title=title, description=description, due_date=due_date, project=project)
    db.session.add(task)
    db.session.commit()
    flash(f'Task "{title}" added.', "success")
    return redirect(url_for("view_project", project_id=project.id))


@app.route("/tasks/<int:task_id>/edit", methods=["POST"])
@login_required
def edit_task(task_id):
    task = get_owned_task_or_404(task_id)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    due_date_str = request.form.get("due_date", "").strip()

    if not title:
        flash("Task title is required.", "error")
        return redirect(url_for("view_project", project_id=task.project_id))

    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid due date.", "error")
            return redirect(url_for("view_project", project_id=task.project_id))

    task.title = title
    task.description = description
    task.due_date = due_date
    db.session.commit()
    flash("Task updated.", "success")
    return redirect(url_for("view_project", project_id=task.project_id))


@app.route("/tasks/<int:task_id>/status", methods=["POST"])
@login_required
def update_task_status(task_id):
    task = get_owned_task_or_404(task_id)
    status = request.form.get("status")

    if status not in ("todo", "doing", "done"):
        flash("Invalid status.", "error")
    else:
        task.status = status
        db.session.commit()

    return redirect(url_for("view_project", project_id=task.project_id))


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    task = get_owned_task_or_404(task_id)
    project_id = task.project_id
    db.session.delete(task)
    db.session.commit()
    flash("Task deleted.", "success")
    return redirect(url_for("view_project", project_id=project_id))


# ---------- Telegram Integration ----------

@app.route("/telegram/connect", methods=["GET", "POST"])
@login_required
def connect_telegram():
    """Page for users to connect their Telegram"""
    if request.method == "POST":
        # Check if user wants to disconnect
        if request.form.get("remove"):
            current_user.telegram_chat_id = None
            db.session.commit()
            flash("Telegram disconnected.", "info")
            return redirect(url_for("connect_telegram"))
        
        chat_id = request.form.get("chat_id", "").strip()
        if not chat_id:
            flash("Please enter your Telegram Chat ID.", "error")
        else:
            # Test the connection
            test_msg = f"✅ Connected to Task Manager!\nHello {current_user.username}!"
            if send_telegram_message(chat_id, test_msg):
                current_user.telegram_chat_id = chat_id
                db.session.commit()
                flash("Telegram connected successfully! Check your Telegram for a test message.", "success")
            else:
                flash("Failed to send test message. Check your Chat ID and try again.", "error")
        return redirect(url_for("connect_telegram"))
    
    return render_template("connect_telegram.html")


def send_due_task_reminders():
    """Send Telegram reminders for tasks due in 24 hours or overdue"""
    if not TELEGRAM_BOT_TOKEN:
        print("Telegram bot not configured. Skipping reminders.")
        return 0
    
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    
    # Tasks due tomorrow OR overdue (and not done)
    tasks = Task.query.filter(
        Task.status != 'done',
        Task.due_date.isnot(None),
        Task.due_date <= tomorrow
    ).all()
    
    sent_count = 0
    for task in tasks:
        user = task.project.owner
        if not user.telegram_chat_id:
            continue
        
        # Check if overdue or due soon
        if task.due_date < today:
            status_emoji = "🔴 OVERDUE"
        elif task.due_date == today:
            status_emoji = "⚠️ DUE TODAY"
        else:
            status_emoji = "⏰ DUE TOMORROW"
        
        message = f"""
🔔 <b>Task Reminder</b>

<b>Project:</b> {task.project.name}
<b>Task:</b> {task.title}
<b>Status:</b> {status_emoji}
<b>Due Date:</b> {task.due_date}

📝 <b>Description:</b> {task.description or 'No description'}

🔗 View: https://your-app-domain.com/projects/{task.project_id}
        """
        
        if send_telegram_message(user.telegram_chat_id, message):
            sent_count += 1
    
    return sent_count


@app.route("/send-reminders")
@login_required
def trigger_reminders():
    """Manually trigger reminders (for testing)"""
    count = send_due_task_reminders()
    flash(f"Sent {count} reminder(s)!", "success")
    return redirect(url_for("dashboard"))

# ---------- Cron Job Endpoint ----------

@app.route("/cron/reminders")
def cron_reminders():
    """Public endpoint for Render Cron Jobs to trigger reminders"""
    try:
        count = send_due_task_reminders()
        return f"✅ Sent {count} reminder(s)!"
    except Exception as e:
        return f"❌ Error: {str(e)}", 500
# ---------- Entry point ----------

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)