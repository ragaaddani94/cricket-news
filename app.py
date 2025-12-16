# application.py
# Production-ready Flask app for Elastic Beanstalk / AWS
import os
import time
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
import feedparser   # needs to be in requirements

# WSGI application object expected by many platforms (Elastic Beanstalk)
application = Flask(__name__)

# Secrets / config from environment
application.secret_key = os.environ.get("SECRET_KEY", "change-me-locally")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_TO_EMAIL = os.environ.get("SMTP_TO_EMAIL", "")
NEWS_FEED_URL = os.environ.get("NEWS_FEED_URL", "https://news.google.com/rss/search?q=cricket")

# -----------------------------
# MongoDB SETUP
# -----------------------------
client = MongoClient(MONGO_URI)
#db = client.get_default_database() if client.get_default_database() else client["small_flask_site"]
db = client["small_flask_site"]

users_collection = db["users"]
contacts_collection = db["contacts"]

# -----------------------------
# EMAIL SENDER
# -----------------------------
def send_email(subject, body):
    """
    Generic email sender using SMTP credentials from env vars.
    Returns True if sent/attempted (or mocked), False if failed.
    """
    if not (SMTP_USER and SMTP_PASSWORD and SMTP_TO_EMAIL):
        print(f"SMTP not configured; Mock sending email: Subject='{subject}'")
        return False

    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = SMTP_TO_EMAIL

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"Email sent successfully: {subject}")
        return True
    except Exception as e:
        print("Error sending email:", e)
        return False

def send_contact_notification(name, email, message):
    subject = f"New Contact: {name}"
    body = f"Name: {name}\nEmail: {email}\n\nMessage:\n{message}"
    return send_email(subject, body)

def send_registration_notification(username):
    subject = f"New User Registered: {username}"
    body = f"A new user has registered on the site.\n\nUsername: {username}\nTime: {time.ctime()}"
    return send_email(subject, body)

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
# Simple cached RSS fetcher for daily news
# - Fetches NEWS_FEED_URL and caches for CACHE_TTL seconds (default 3600 = 1 hour)
# -----------------------------
NEWS_CACHE = {"ts": 0, "items": []}
CACHE_TTL = int(os.environ.get("NEWS_CACHE_TTL", "3600"))

def fetch_news():
    now = time.time()
    if now - NEWS_CACHE["ts"] < CACHE_TTL and NEWS_CACHE["items"]:
        return NEWS_CACHE["items"]
    try:
        feed = feedparser.parse(NEWS_FEED_URL)
        items = []
        for entry in feed.entries[:8]:
            items.append({
                "title": entry.get("title"),
                "link": entry.get("link"),
                "published": entry.get("published", ""),
            })
        NEWS_CACHE["ts"] = now
        NEWS_CACHE["items"] = items
        return items
    except Exception as e:
        print("Error fetching news:", e)
        return []

# -----------------------------
# ROUTES
# -----------------------------
@application.route("/")
def home():
    return render_template("index.html")

@application.route("/news")
def news():
    news_items = fetch_news()
    return render_template("news.html", news=news_items)

@application.route("/about")
def about():
    return render_template("about.html")

@application.route("/scores")
def scores():
    # Fetch live cricket scores from Cricinfo RSS
    try:
        feed = feedparser.parse("http://static.cricinfo.com/rss/livescores.xml")
        matches = []
        for entry in feed.entries[:5]:  # Limit to 5 matches
            # Mock Images for captains (since RSS doesn't provide them)
            # In a real app, you'd fetch these from a paid API API or database
            team1_img = "https://ui-avatars.com/api/?name=Captain+1&background=random&color=fff"
            team2_img = "https://ui-avatars.com/api/?name=Captain+2&background=random&color=fff"
            
            matches.append({
                "title": entry.get("title"),
                "description": entry.get("description"),
                "link": entry.get("link"),
                "team1_img": team1_img,
                "team2_img": team2_img
            })
        return {"matches": matches}
    except Exception as e:
        print("Error fetching scores:", e)
        return {"matches": []}

@application.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")

        # Save to MongoDB
        try:
            contacts_collection.insert_one(
                {"name": name, "email": email, "message": message, "created_at": time.time()}
            )
        except Exception as e:
            print("Mongo insert contact failed:", e)

        # Send email (if configured)
        send_contact_notification(name, email, message)

        flash("Thanks for reaching out! We'll get back to you soon.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")

@application.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        existing_user = users_collection.find_one({"username": username})
        if existing_user:
            flash("Username already exists. Please choose another.", "danger")
            return redirect(url_for("register"))

        hashed_pw = generate_password_hash(password)
        try:
            result = users_collection.insert_one(
                {
                    "username": username,
                    "password": hashed_pw,
                }
            )
            session["user_id"] = str(result.inserted_id)
            session["username"] = username
            
            # Send notification to admin
            send_registration_notification(username)

            flash("Registration successful! You are now logged in.", "success")
            return redirect(url_for("dashboard"))
        except Exception as e:
            print("Mongo insert user failed:", e)
            flash("Registration failed. Try again.", "danger")
            return redirect(url_for("register"))

    return render_template("register.html")

@application.route("/login", methods=["GET", "POST"])
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

@application.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))

@application.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

# Run locally for dev
if __name__ == "__main__":
    application.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
