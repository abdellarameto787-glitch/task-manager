import os
from datetime import datetime

from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)

from models import db, User, Project, Task

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///taskmanager.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access that page."
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


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


# ---------- Entry point ----------

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
