from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# CHANGE THIS in real project
app.secret_key = "change-this-secret-key"

# -----------------------------
# MongoDB SETUP
# -----------------------------
# Make sure MongoDB is running locally on default port 27017
client = MongoClient("mongodb://localhost:27017/")
db = client["small_flask_site"]
users_collection = db["users"]
contacts_collection = db["contacts"]


# -----------------------------
# EMAIL SENDER (CONTACT FORM)
# -----------------------------
def send_contact_email(name, email, message):
    """
    Configure your SMTP credentials here.
    For Gmail, you must use App Password (not your main password).
    """

    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SMTP_USER = "your_email@gmail.com"          # TODO: change this
    SMTP_PASSWORD = "your_app_password_here"    # TODO: change this
    TO_EMAIL = "destination_email@example.com"  # TODO: change this

    subject = f"New contact message from {name}"
    body = f"Name: {name}\nEmail: {email}\n\nMessage:\n{message}"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = TO_EMAIL

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print("Contact email sent successfully")
    except Exception as e:
        # For development: just print the error instead of crashing
        print("Error sending email:", e)


# -----------------------------
# LOGIN REQUIRED DECORATOR
# -----------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to view this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")

        # Save to MongoDB
        contacts_collection.insert_one(
            {"name": name, "email": email, "message": message}
        )

        # Send email (console log if SMTP not configured properly)
        send_contact_email(name, email, message)

        flash("Thanks for reaching out! We'll get back to you soon.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        existing_user = users_collection.find_one({"username": username})
        if existing_user:
            flash("Username already exists. Please choose another.", "danger")
            return redirect(url_for("register"))

        hashed_pw = generate_password_hash(password)
        result = users_collection.insert_one(
            {
                "username": username,
                "password": hashed_pw,
            }
        )

        session["user_id"] = str(result.inserted_id)
        session["username"] = username
        flash("Registration successful! You are now logged in.", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = users_collection.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            session["username"] = user["username"]
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


if __name__ == "__main__":
    app.run(debug=True)
