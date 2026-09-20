from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)

# =========================================================
# FLASK CONFIGURATION
# =========================================================

app.secret_key = "lost-found-secret-key"

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp"
}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


# =========================================================
# CHECK ALLOWED IMAGE
# =========================================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def init_db():

    conn = sqlite3.connect("database.db")

    # USERS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # LOST ITEMS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lost_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            location TEXT NOT NULL,
            date_lost TEXT NOT NULL,
            contact TEXT NOT NULL
        )
    """)

    # FOUND ITEMS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS found_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            location TEXT NOT NULL,
            date_found TEXT NOT NULL,
            contact TEXT NOT NULL
        )
    """)

    # ACTIVITY LOG
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            activity TEXT NOT NULL,
            activity_time TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# ADD NEW COLUMNS TO OLD DATABASE
# =========================================================

def add_columns():

    conn = sqlite3.connect("database.db")

    # LOST ITEMS - user_id
    try:
        conn.execute("""
            ALTER TABLE lost_items
            ADD COLUMN user_id INTEGER
        """)
    except sqlite3.OperationalError:
        pass

    # FOUND ITEMS - user_id
    try:
        conn.execute("""
            ALTER TABLE found_items
            ADD COLUMN user_id INTEGER
        """)
    except sqlite3.OperationalError:
        pass

    # LOST ITEMS - photo
    try:
        conn.execute("""
            ALTER TABLE lost_items
            ADD COLUMN photo TEXT
        """)
    except sqlite3.OperationalError:
        pass

    # FOUND ITEMS - photo
    try:
        conn.execute("""
            ALTER TABLE found_items
            ADD COLUMN photo TEXT
        """)
    except sqlite3.OperationalError:
        pass

    # USERS - is_admin
    try:
        conn.execute("""
            ALTER TABLE users
            ADD COLUMN is_admin INTEGER DEFAULT 0
        """)
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


# =========================================================
# CREATE ADMIN ACCOUNT
# =========================================================

def create_admin():

    conn = sqlite3.connect("database.db")

    admin_email = "admin@lostfound.com"

    admin = conn.execute("""
        SELECT id
        FROM users
        WHERE email = ?
    """, (admin_email,)).fetchone()

    if admin:

        conn.execute("""
            UPDATE users
            SET is_admin = 1
            WHERE email = ?
        """, (admin_email,))

    else:

        conn.execute("""
            INSERT INTO users
            (name, email, password, is_admin)
            VALUES (?, ?, ?, ?)
        """, (
            "Administrator",
            admin_email,
            "admin123",
            1
        ))

    conn.commit()
    conn.close()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    conn = get_db()

    lost_count = conn.execute(
        "SELECT COUNT(*) FROM lost_items"
    ).fetchone()[0]

    found_count = conn.execute(
        "SELECT COUNT(*) FROM found_items"
    ).fetchone()[0]

    total_count = lost_count + found_count

    conn.close()

    return render_template(
        "index.html",
        lost_count=lost_count,
        found_count=found_count,
        total_count=total_count
    )


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]

        conn = get_db()

        try:

            conn.execute("""
                INSERT INTO users
                (name, email, password, is_admin)
                VALUES (?, ?, ?, ?)
            """, (
                name,
                email,
                password,
                0
            ))

            conn.commit()

        except sqlite3.IntegrityError:

            conn.close()
            return "Email already registered."

        conn.close()

        return redirect("/login")

    return render_template("register.html")


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip()
        password = request.form["password"]

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE email = ?
            AND password = ?
        """, (
            email,
            password
        )).fetchone()

        if user:

            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["email"] = user["email"]
            session["is_admin"] = user["is_admin"]

            # LOGIN ACTIVITY
            conn.execute("""
                INSERT INTO activity_logs
                (user_id, name, email, activity, activity_time)
                VALUES (?, ?, ?, ?, ?)
            """, (
                user["id"],
                user["name"],
                user["email"],
                "Login",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))

            conn.commit()
            conn.close()

            # ADMIN → ADMIN DASHBOARD
            if user["is_admin"] == 1:
                return redirect("/admin")

            # NORMAL USER → USER DASHBOARD
            return redirect("/dashboard")

        conn.close()

        return "Invalid email or password."

    return render_template("login.html")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    if "user_id" in session:

        conn = get_db()

        user = conn.execute("""
            SELECT id, name, email
            FROM users
            WHERE id = ?
        """, (
            session["user_id"],
        )).fetchone()

        if user:

            conn.execute("""
                INSERT INTO activity_logs
                (user_id, name, email, activity, activity_time)
                VALUES (?, ?, ?, ?, ?)
            """, (
                user["id"],
                user["name"],
                user["email"],
                "Logout",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))

            conn.commit()

        conn.close()

    session.clear()

    return redirect("/")


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin_dashboard():

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    )).fetchone()

    # Only admin can access
    if not user or user["is_admin"] != 1:

        conn.close()
        return redirect("/dashboard")

    # Statistics
    user_count = conn.execute(
        "SELECT COUNT(*) FROM users WHERE is_admin = 0"
    ).fetchone()[0]

    lost_count = conn.execute(
        "SELECT COUNT(*) FROM lost_items"
    ).fetchone()[0]

    found_count = conn.execute(
        "SELECT COUNT(*) FROM found_items"
    ).fetchone()[0]

    activity_count = conn.execute(
        "SELECT COUNT(*) FROM activity_logs"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "admin.html",
        name=user["name"],
        email=user["email"],
        user_count=user_count,
        lost_count=lost_count,
        found_count=found_count,
        activity_count=activity_count
    )


# =========================================================
# USER DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/login")

    # Admin should use admin dashboard
    if session.get("is_admin") == 1:
        return redirect("/admin")

    conn = get_db()

    lost_items = conn.execute("""
        SELECT *
        FROM lost_items
        WHERE user_id = ?
        ORDER BY id DESC
    """, (
        session["user_id"],
    )).fetchall()

    found_items = conn.execute("""
        SELECT *
        FROM found_items
        WHERE user_id = ?
        ORDER BY id DESC
    """, (
        session["user_id"],
    )).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        name=session["name"],
        email=session["email"],
        lost_items=lost_items,
        found_items=found_items,
        is_admin=session.get("is_admin", 0)
    )


# =========================================================
# REPORT LOST ITEM
# =========================================================

@app.route("/report-lost", methods=["GET", "POST"])
def report_lost():

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        item_name = request.form["item_name"]
        category = request.form["category"]
        description = request.form["description"]
        location = request.form["location"]
        date_lost = request.form["date_lost"]
        contact = request.form["contact"]

        photo = request.files.get("photo")
        filename = None

        if photo and photo.filename:

            if allowed_file(photo.filename):

                filename = secure_filename(photo.filename)

                name, extension = os.path.splitext(filename)

                filename = (
                    f"{session['user_id']}_lost_"
                    f"{name}{extension}"
                )

                photo.save(
                    os.path.join(
                        app.config["UPLOAD_FOLDER"],
                        filename
                    )
                )

        conn = get_db()

        conn.execute("""
            INSERT INTO lost_items
            (
                user_id,
                item_name,
                category,
                description,
                location,
                date_lost,
                contact,
                photo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            item_name,
            category,
            description,
            location,
            date_lost,
            contact,
            filename
        ))

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    return render_template("report_lost.html")


# =========================================================
# REPORT FOUND ITEM
# =========================================================

@app.route("/report-found", methods=["GET", "POST"])
def report_found():

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        item_name = request.form["item_name"]
        category = request.form["category"]
        description = request.form["description"]
        location = request.form["location"]
        date_found = request.form["date_found"]
        contact = request.form["contact"]

        photo = request.files.get("photo")
        filename = None

        if photo and photo.filename:

            if allowed_file(photo.filename):

                filename = secure_filename(photo.filename)

                name, extension = os.path.splitext(filename)

                filename = (
                    f"{session['user_id']}_found_"
                    f"{name}{extension}"
                )

                photo.save(
                    os.path.join(
                        app.config["UPLOAD_FOLDER"],
                        filename
                    )
                )

        conn = get_db()

        conn.execute("""
            INSERT INTO found_items
            (
                user_id,
                item_name,
                category,
                description,
                location,
                date_found,
                contact,
                photo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            item_name,
            category,
            description,
            location,
            date_found,
            contact,
            filename
        ))

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    return render_template("report_found.html")


# =========================================================
# VIEW ALL LOST ITEMS
# =========================================================

@app.route("/lost-items")
def lost_items():

    conn = get_db()

    items = conn.execute("""
        SELECT *
        FROM lost_items
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "lost_items.html",
        items=items
    )


# =========================================================
# VIEW ALL FOUND ITEMS
# =========================================================

@app.route("/found-items")
def found_items():

    conn = get_db()

    items = conn.execute("""
        SELECT *
        FROM found_items
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "found_items.html",
        items=items
    )


# =========================================================
# SEARCH
# =========================================================

@app.route("/search")
def search():

    query = request.args.get("q", "").strip()

    conn = get_db()

    if query:

        search_value = f"%{query}%"

        lost_items = conn.execute("""
            SELECT *
            FROM lost_items
            WHERE item_name LIKE ?
               OR category LIKE ?
               OR location LIKE ?
               OR description LIKE ?
            ORDER BY id DESC
        """, (
            search_value,
            search_value,
            search_value,
            search_value
        )).fetchall()

        found_items = conn.execute("""
            SELECT *
            FROM found_items
            WHERE item_name LIKE ?
               OR category LIKE ?
               OR location LIKE ?
               OR description LIKE ?
            ORDER BY id DESC
        """, (
            search_value,
            search_value,
            search_value,
            search_value
        )).fetchall()

    else:

        lost_items = []
        found_items = []

    conn.close()

    return render_template(
        "search.html",
        lost_items=lost_items,
        found_items=found_items,
        query=query
    )


# =========================================================
# EDIT LOST ITEM
# =========================================================

@app.route("/edit-lost/<int:item_id>", methods=["GET", "POST"])
def edit_lost(item_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    item = conn.execute("""
        SELECT *
        FROM lost_items
        WHERE id = ?
        AND user_id = ?
    """, (
        item_id,
        session["user_id"]
    )).fetchone()

    if item is None:

        conn.close()
        return "Report not found or you don't have permission to edit it."

    if request.method == "POST":

        conn.execute("""
            UPDATE lost_items
            SET item_name = ?,
                category = ?,
                description = ?,
                location = ?,
                date_lost = ?,
                contact = ?
            WHERE id = ?
            AND user_id = ?
        """, (
            request.form["item_name"],
            request.form["category"],
            request.form["description"],
            request.form["location"],
            request.form["date_lost"],
            request.form["contact"],
            item_id,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    conn.close()

    return render_template(
        "edit_lost.html",
        item=item
    )


# =========================================================
# DELETE LOST ITEM
# =========================================================

@app.route("/delete-lost/<int:item_id>")
def delete_lost(item_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    item = conn.execute("""
        SELECT photo
        FROM lost_items
        WHERE id = ?
        AND user_id = ?
    """, (
        item_id,
        session["user_id"]
    )).fetchone()

    if item:

        if item["photo"]:

            photo_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                item["photo"]
            )

            if os.path.exists(photo_path):
                os.remove(photo_path)

        conn.execute("""
            DELETE FROM lost_items
            WHERE id = ?
            AND user_id = ?
        """, (
            item_id,
            session["user_id"]
        ))

    conn.commit()
    conn.close()

    return redirect("/dashboard")


# =========================================================
# EDIT FOUND ITEM
# =========================================================

@app.route("/edit-found/<int:item_id>", methods=["GET", "POST"])
def edit_found(item_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    item = conn.execute("""
        SELECT *
        FROM found_items
        WHERE id = ?
        AND user_id = ?
    """, (
        item_id,
        session["user_id"]
    )).fetchone()

    if item is None:

        conn.close()
        return "Report not found or you don't have permission to edit it."

    if request.method == "POST":

        conn.execute("""
            UPDATE found_items
            SET item_name = ?,
                category = ?,
                description = ?,
                location = ?,
                date_found = ?,
                contact = ?
            WHERE id = ?
            AND user_id = ?
        """, (
            request.form["item_name"],
            request.form["category"],
            request.form["description"],
            request.form["location"],
            request.form["date_found"],
            request.form["contact"],
            item_id,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    conn.close()

    return render_template(
        "edit_found.html",
        item=item
    )


# =========================================================
# DELETE FOUND ITEM
# =========================================================

@app.route("/delete-found/<int:item_id>")
def delete_found(item_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    item = conn.execute("""
        SELECT photo
        FROM found_items
        WHERE id = ?
        AND user_id = ?
    """, (
        item_id,
        session["user_id"]
    )).fetchone()

    if item:

        if item["photo"]:

            photo_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                item["photo"]
            )

            if os.path.exists(photo_path):
                os.remove(photo_path)

        conn.execute("""
            DELETE FROM found_items
            WHERE id = ?
            AND user_id = ?
        """, (
            item_id,
            session["user_id"]
        ))

    conn.commit()
    conn.close()

    return redirect("/dashboard")


# =========================================================
# LOST ↔ FOUND MATCHING
# =========================================================

@app.route("/matches")
def matches():

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    lost_items = conn.execute("""
        SELECT *
        FROM lost_items
        WHERE user_id = ?
        ORDER BY id DESC
    """, (
        session["user_id"],
    )).fetchall()

    matches = []

    for lost in lost_items:

        found_items = conn.execute("""
            SELECT *
            FROM found_items
            WHERE
                LOWER(item_name) LIKE ?
                OR LOWER(category) LIKE ?
                OR LOWER(location) LIKE ?
            ORDER BY id DESC
        """, (
            f"%{lost['item_name'].lower()}%",
            f"%{lost['category'].lower()}%",
            f"%{lost['location'].lower()}%"
        )).fetchall()

        for found in found_items:

            matches.append({
                "lost": lost,
                "found": found
            })

    conn.close()

    return render_template(
        "matches.html",
        matches=matches
    )


# =========================================================
# ADMIN-ONLY ACTIVITY
# =========================================================

@app.route("/activity")
def activity():

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    user = conn.execute("""
        SELECT is_admin
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    )).fetchone()

    # Normal users cannot access activity
    if not user or user["is_admin"] != 1:

        conn.close()
        return redirect("/dashboard")

    logs = conn.execute("""
        SELECT *
        FROM activity_logs
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "activity.html",
        logs=logs
    )


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    init_db()
    add_columns()
    create_admin()

    app.run(debug=True)