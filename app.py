from flask import Flask, render_template, request, redirect, session, flash, url_for
import sqlite3
import hashlib
import time
import requests
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "your_super_secret_key_here"
app.config['STATIC_FOLDER'] = 'static'

DB = "xtracash.db"
NOWPAYMENTS_API_KEY = "your_api_key_here"  # Замените на реальный ключ
NOWPAYMENTS_URL = "https://api.nowpayments.io/v1/invoice"

# Инициализация БД
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            balance INTEGER DEFAULT 0,
            email TEXT UNIQUE
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            sender TEXT,
            receiver TEXT,
            amount INTEGER,
            status TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# Хэширование пароля
def hash_password(password):
    return generate_password_hash(password, method='pbkdf2:sha256')

# Проверка пароля
def verify_password(stored_hash, password):
    return check_password_hash(stored_hash, password)

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            flash("Пароли не совпадают!", "error")
            return redirect(url_for("register"))

        hashed_pw = hash_password(password)
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (username, email, hashed_pw)
            )
            conn.commit()
            flash("Регистрация успешна! Войдите в аккаунт.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Имя пользователя или email уже заняты.", "error")
        finally:
            conn.close()
    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT username, balance FROM users WHERE id = ?", (session["user_id"],))
    user = c.fetchone()
    conn.close()
    
    return render_template("dashboard.html", user=user)

@app.route("/pay", methods=["POST"])
def create_payment():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    amount = float(request.form["amount"])
    currency = request.form["currency"]
    
    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "price_amount": amount,
        "price_currency": "usd",
        "pay_currency": currency,
        "order_id": f"order_{session['user_id']}_{int(time.time())}",
        "ipn_callback_url": url_for("payment_callback", _external=True),
        "success_url": url_for("payment_success", _external=True),
        "cancel_url": url_for("payment_cancel", _external=True)
    }
    
    response = requests.post(NOWPAYMENTS_URL, json=payload, headers=headers)
    if response.status_code == 201:
        return redirect(response.json()["invoice_url"])
    else:
        flash("Ошибка при создании платежа", "error")
        return redirect(url_for("dashboard"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
