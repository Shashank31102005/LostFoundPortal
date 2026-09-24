from flask import Flask, render_template, request, redirect, session
import psycopg2
from psycopg2.extras import DictCursor
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
# DATABASE CONNECTION - POSTGRESQL
# =========================================================

def get_db():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set."
        )

    conn = psycopg2.connect(
        database_url,
        cursor_factory=DictCursor
    )

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

    conn = get_db()
    cursor = conn.cursor()

    # USERS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    """)

    # LOST ITEMS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lost_items (
            id SERIAL PRIMARY KEY,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            location TEXT NOT NULL,
            date_lost TEXT NOT NULL,
            contact TEXT NOT NULL,
            user_id INTEGER,
            photo TEXT
        )
    """)

    # FOUND ITEMS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS found_items (
            id SERIAL PRIMARY KEY,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            location TEXT NOT NULL,
            date_found TEXT NOT NULL,
            contact TEXT NOT NULL,
            user_id INTEGER,
            photo TEXT
        )
    """)

    # ACTIVITY LOG
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            activity TEXT NOT NULL,
            activity_time TEXT NOT NULL
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()


# =========================================================
# ADD NEW COLUMNS TO EXISTING POSTGRESQL DATABASE
# =========================================================

def add_columns():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        ALTER TABLE lost_items
        ADD COLUMN IF NOT EXISTS user_id INTEGER
    """)

    cursor.execute("""
        ALTER TABLE lost_items
        ADD COLUMN IF NOT EXISTS photo TEXT
    """)

    cursor.execute("""
        ALTER TABLE found_items
        ADD COLUMN IF NOT EXISTS user_id INTEGER
    """)

    cursor.execute("""
        ALTER TABLE found_items
        ADD COLUMN IF NOT EXISTS photo TEXT
    """)

    cursor.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS is_admin INTEGER DEFAULT 0
    """)

    conn.commit()
    cursor.close()
    conn.close()


# =========================================================
# CREATE ADMIN ACCOUNT
# =========================================================

def create_admin():

    conn = get_db()
    cursor = conn.cursor()

    admin_email = "admin@lostfound.com"

    cursor.execute("""
        SELECT id
        FROM users
        WHERE email = %s
    """, (admin_email,))

    admin = cursor.fetchone()

    if admin:

        cursor.execute("""
            UPDATE users
            SET is_admin = 1
            WHERE email = %s
        """, (admin_email,))

    else:

        cursor.execute("""
            INSERT INTO users
            (name, email, password, is_admin)
            VALUES (%s, %s, %s, %s)
        """, (
            "Administrator",
            admin_email,
            "admin123",
            1
        ))

    conn.commit()
    cursor.close()
    conn.close()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM lost_items"
    )
    lost_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM found_items"
    )
    found_count = cursor.fetchone()[0]

    total_count = lost_count + found_count

    cursor.close()
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
        cursor = conn.cursor()

        try:

            cursor.execute("""
                INSERT INTO users
                (name, email, password, is_admin)
                VALUES (%s, %s, %s, %s)
            """, (
                name,
                email,
                password,
                0
            ))

            conn.commit()

        except psycopg2.IntegrityError:

            conn.rollback()
            cursor.close()
            conn.close()

            return "Email already registered."

        cursor.close()
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
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM users
            WHERE email = %s
            AND password = %s
        """, (
            email,
            password
        ))

        user = cursor.fetchone()

        if user:

            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["email"] = user["email"]
            session["is_admin"] = user["is_admin"]

            cursor.execute("""
                INSERT INTO activity_logs
                (user_id, name, email, activity, activity_time)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                user["id"],
                user["name"],
                user["email"],
                "Login",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))

            conn.commit()
            cursor.close()
            conn.close()

            if user["is_admin"] == 1:
                return redirect("/admin")

            return redirect("/dashboard")

        cursor.close()
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
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, email
            FROM users
            WHERE id = %s
        """, (
            session["user_id"],
        ))

        user = cursor.fetchone()

        if user:

            cursor.execute("""
                INSERT INTO activity_logs
                (user_id, name, email, activity, activity_time)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                user["id"],
                user["name"],
                user["email"],
                "Logout",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))

            conn.commit()

        cursor.close()
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
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM users
        WHERE id = %s
    """, (
        session["user_id"],
    ))

    user = cursor.fetchone()

    if not user or user["is_admin"] != 1:

        cursor.close()
        conn.close()
        return redirect("/dashboard")

    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE is_admin = 0"
    )
    user_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM lost_items"
    )
    lost_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM found_items"
    )
    found_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM activity_logs"
    )
    activity_count = cursor.fetchone()[0]

    cursor.close()
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

    if session.get("is_admin") == 1:
        return redirect("/admin")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM lost_items
        WHERE user_id = %s
        ORDER BY id DESC
    """, (
        session["user_id"],
    ))

    lost_items = cursor.fetchall()

    cursor.execute("""
        SELECT *
        FROM found_items
        WHERE user_id = %s
        ORDER BY id DESC
    """, (
        session["user_id"],
    ))

    found_items = cursor.fetchall()

    cursor.close()
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
        cursor = conn.cursor()

        cursor.execute("""
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
        cursor.close()
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
        cursor = conn.cursor()

        cursor.execute("""
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
        cursor.close()
        conn.close()

        return redirect("/dashboard")

    return render_template("report_found.html")


# =========================================================
# VIEW ALL LOST ITEMS
# =========================================================

@app.route("/lost-items")
def lost_items():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM lost_items
        ORDER BY id DESC
    """)

    items = cursor.fetchall()

    cursor.close()
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
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM found_items
        ORDER BY id DESC
    """)

    items = cursor.fetchall()

    cursor.close()
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
    cursor = conn.cursor()

    if query:

        search_value = f"%{query}%"

        cursor.execute("""
            SELECT *
            FROM lost_items
            WHERE item_name ILIKE %s
               OR category ILIKE %s
               OR location ILIKE %s
               OR description ILIKE %s
            ORDER BY id DESC
        """, (
            search_value,
            search_value,
            search_value,
            search_value
        ))

        lost_items = cursor.fetchall()

        cursor.execute("""
            SELECT *
            FROM found_items
            WHERE item_name ILIKE %s
               OR category ILIKE %s
               OR location ILIKE %s
               OR description ILIKE %s
            ORDER BY id DESC
        """, (
            search_value,
            search_value,
            search_value,
            search_value
        ))

        found_items = cursor.fetchall()

    else:

        lost_items = []
        found_items = []

    cursor.close()
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
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM lost_items
        WHERE id = %s
        AND user_id = %s
    """, (
        item_id,
        session["user_id"]
    ))

    item = cursor.fetchone()

    if item is None:

        cursor.close()
        conn.close()
        return "Report not found or you don't have permission to edit it."

    if request.method == "POST":

        cursor.execute("""
            UPDATE lost_items
            SET item_name = %s,
                category = %s,
                description = %s,
                location = %s,
                date_lost = %s,
                contact = %s
            WHERE id = %s
            AND user_id = %s
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
        cursor.close()
        conn.close()

        return redirect("/dashboard")

    cursor.close()
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
    cursor = conn.cursor()

    cursor.execute("""
        SELECT photo
        FROM lost_items
        WHERE id = %s
        AND user_id = %s
    """, (
        item_id,
        session["user_id"]
    ))

    item = cursor.fetchone()

    if item:

        if item["photo"]:

            photo_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                item["photo"]
            )

            if os.path.exists(photo_path):
                os.remove(photo_path)

        cursor.execute("""
            DELETE FROM lost_items
            WHERE id = %s
            AND user_id = %s
        """, (
            item_id,
            session["user_id"]
        ))

    conn.commit()
    cursor.close()
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
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM found_items
        WHERE id = %s
        AND user_id = %s
    """, (
        item_id,
        session["user_id"]
    ))

    item = cursor.fetchone()

    if item is None:

        cursor.close()
        conn.close()
        return "Report not found or you don't have permission to edit it."

    if request.method == "POST":

        cursor.execute("""
            UPDATE found_items
            SET item_name = %s,
                category = %s,
                description = %s,
                location = %s,
                date_found = %s,
                contact = %s
            WHERE id = %s
            AND user_id = %s
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
        cursor.close()
        conn.close()

        return redirect("/dashboard")

    cursor.close()
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
    cursor = conn.cursor()

    cursor.execute("""
        SELECT photo
        FROM found_items
        WHERE id = %s
        AND user_id = %s
    """, (
        item_id,
        session["user_id"]
    ))

    item = cursor.fetchone()

    if item:

        if item["photo"]:

            photo_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                item["photo"]
            )

            if os.path.exists(photo_path):
                os.remove(photo_path)

        cursor.execute("""
            DELETE FROM found_items
            WHERE id = %s
            AND user_id = %s
        """, (
            item_id,
            session["user_id"]
        ))

    conn.commit()
    cursor.close()
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
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM lost_items
        WHERE user_id = %s
        ORDER BY id DESC
    """, (
        session["user_id"],
    ))

    lost_items = cursor.fetchall()

    matches = []

    for lost in lost_items:

        cursor.execute("""
            SELECT *
            FROM found_items
            WHERE
                LOWER(item_name) LIKE %s
                OR LOWER(category) LIKE %s
                OR LOWER(location) LIKE %s
            ORDER BY id DESC
        """, (
            f"%{lost['item_name'].lower()}%",
            f"%{lost['category'].lower()}%",
            f"%{lost['location'].lower()}%"
        ))

        found_items = cursor.fetchall()

        for found in found_items:

            matches.append({
                "lost": lost,
                "found": found
            })

    cursor.close()
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
    cursor = conn.cursor()

    cursor.execute("""
        SELECT is_admin
        FROM users
        WHERE id = %s
    """, (
        session["user_id"],
    ))

    user = cursor.fetchone()

    if not user or user["is_admin"] != 1:

        cursor.close()
        conn.close()
        return redirect("/dashboard")

    cursor.execute("""
        SELECT *
        FROM activity_logs
        ORDER BY id DESC
    """)

    logs = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "activity.html",
        logs=logs
    )


# =========================================================
# START APPLICATION
# =========================================================

if os.environ.get("DATABASE_URL"):
    init_db()
    add_columns()
    create_admin()


if __name__ == "__main__":
    app.run(debug=True)
