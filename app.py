from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import calendar
import mysql.connector


app = Flask(__name__)
app.secret_key = "secret123"

calendar.setfirstweekday(calendar.SUNDAY)

# ---------------- Database Connection ----------------
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="pepelegeg_db"
    )

# ---------------- Calendar Data ----------------
def get_calendar(year=None, month=None):
    now = datetime.now()
    if not year: year = now.year
    if not month: month = now.month
    cal = calendar.monthcalendar(year, month)
    return {
        "calendar": cal,
        "month": month,
        "year": year,
        "month_name": calendar.month_name[month],
        "current_date": now.date()
    }

# ---------------- AUTH ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        hashed_pw = generate_password_hash(password)


        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_pw))
        conn.commit()
        conn.close()
        return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))


        else:
            return render_template("login.html", error="Username atau password salah")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------- INDEX ----------------
@app.route("/index")
def index():
    if "user_id" not in session:
      return redirect(url_for("login"))  
    
    year = request.args.get("year", type=int) or datetime.now().year
    month = request.args.get("month", type=int) or datetime.now().month
    cal_data = get_calendar(year, month)

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # ---------- Tasks ----------
    cursor.execute("SELECT * FROM tasks")
    tasks = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) AS done FROM tasks WHERE done=1")
    completed_tasks = cursor.fetchone()["done"]

    cursor.execute("SELECT COUNT(*) AS total FROM tasks")
    total_tasks = cursor.fetchone()["total"]

    tasks_by_date = {}
    for t in tasks:
        if t["date"]:
            d = t["date"].strftime("%Y-%m-%d")
            tasks_by_date.setdefault(d, []).append(t)

    # ---------- Moods ----------
    cursor.execute("SELECT * FROM moods")
    moods_raw = cursor.fetchall()
    moods_by_date = {}
    for m in moods_raw:
        if m["date"] is not None:
            moods_by_date[m["date"].strftime("%Y-%m-%d")] = m["mood"]

    # ---------- Habits ----------
    today = date.today()
    start_week = today - timedelta(days=today.weekday())
    week_days = [start_week + timedelta(days=i) for i in range(7)]

    cursor.execute("SELECT * FROM habits")
    habits_raw = cursor.fetchall()

    habits = []
    for habit in habits_raw:
        row = {"id": habit["id"], "name": habit["name"], "days": []}
        for d in week_days:
            cursor.execute("SELECT done FROM habit_logs WHERE habit_id=%s AND date=%s", (habit["id"], d))
            result = cursor.fetchone()
            if result:
                done = bool(result["done"])
            else:
                cursor.execute("INSERT IGNORE INTO habit_logs (habit_id, date, done) VALUES (%s, %s, %s)",
                               (habit["id"], d, False))
                conn.commit()
                done = False
            row["days"].append({"date": d, "done": done})
        habits.append(row)

    # ---------- Budgets ----------
    cursor.execute("SELECT * FROM budgets")
    budgets = cursor.fetchall()

    cursor.execute("SELECT COALESCE(SUM(amount),0) AS income FROM budgets WHERE type='income'")
    budget_income = cursor.fetchone()["income"]

    cursor.execute("SELECT COALESCE(SUM(amount),0) AS expense FROM budgets WHERE type='expense'")
    budget_expense = cursor.fetchone()["expense"]

    cursor.close()
    conn.close()

    # hitung prev/next bulan
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return render_template("index.html",
                           tasks=tasks,
                           habits=habits,
                           budgets=budgets,
                           week_days=week_days,
                           completed_tasks=completed_tasks,
                           total_tasks=total_tasks,
                           budget_income=budget_income,
                           budget_expense=budget_expense,
                           tasks_by_date=tasks_by_date,
                           moods_by_date=moods_by_date,
                           prev_month=prev_month,
                           prev_year=prev_year,
                           next_month=next_month,
                           next_year=next_year,
                           **cal_data)

# ---------------- TASKS ----------------
@app.route("/api/tasks", methods=["POST"])
def api_add_task():
    data = request.get_json()
    date_ = data.get("date")
    task = data.get("task")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (date, text, done) VALUES (%s, %s, %s)", (date_, task, False))
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return jsonify(success=True, id=task_id)

@app.route("/api/tasks/<date>")
def get_tasks(date):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, text, done FROM tasks WHERE date=%s", (date,))
    rows = cur.fetchall()
    conn.close()
    tasks = [{"id":r[0], "text":r[1], "done":bool(r[2])} for r in rows]
    return jsonify({"tasks": tasks})

@app.route("/api/tasks/<date>/<int:task_id>", methods=["DELETE"])
def api_delete_task(date, task_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
    conn.commit()
    conn.close()
    return jsonify(success=True)

@app.route("/api/tasks/<date>/<int:task_id>/toggle", methods=["PUT"])
def api_toggle_task(date, task_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT done FROM tasks WHERE id=%s", (task_id,))
    task = cursor.fetchone()
    if task:
        new_val = 0 if task["done"] else 1
        cursor.execute("UPDATE tasks SET done=%s WHERE id=%s", (new_val, task_id))
        conn.commit()
    conn.close()
    return jsonify(success=True)


# ---------------- HABITS ----------------
@app.route("/habit", methods=["POST"])
def habit():
    habit_name = request.form["habit_name"].strip()
    if habit_name:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO habits (name) VALUES (%s)", (habit_name,))
        conn.commit()
        conn.close()
    return redirect(url_for("index"))

@app.route("/toggle/<int:habit_id>/<string:date_str>")
def toggle(habit_id, date_str):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT done FROM habit_logs WHERE habit_id=%s AND date=%s", (habit_id, date_str))
    result = cursor.fetchone()
    if result:
        new_val = 0 if result["done"] else 1
        cursor.execute("UPDATE habit_logs SET done=%s WHERE habit_id=%s AND date=%s", (new_val, habit_id, date_str))
    else:
        cursor.execute("INSERT INTO habit_logs (habit_id, date, done) VALUES (%s, %s, %s)", (habit_id, date_str, 1))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/delete/<int:habit_id>")
def delete_habit(habit_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM habits WHERE id=%s", (habit_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

# ---------------- BUDGET ----------------
@app.route("/budget", methods=["POST"])
def budget():
    type_ = request.form["type"]
    amount = float(request.form["amount"])
    desc = request.form.get("desc", "")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO budgets (type, amount, description) VALUES (%s, %s, %s)", (type_, amount, desc))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/budget/delete/<int:budget_id>")
def budget_delete(budget_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM budgets WHERE id=%s", (budget_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

# ---------------- MOOD API (AJAX) ----------------
@app.route("/api/mood", methods=["POST"])
def set_mood():
    data = request.get_json()
    date_, mood = data.get("date"), data.get("mood")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO moods (user_id, date, mood) VALUES (%s,%s,%s)
        ON DUPLICATE KEY UPDATE mood=%s
    """, (1, date_, mood, mood))
    conn.commit()
    conn.close()
    return jsonify(success=True)

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
