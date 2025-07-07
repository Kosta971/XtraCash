from flask import Flask, request, jsonify, render_template, redirect, session
import sqlite3
import hashlib
import time
import requests

app = Flask(__name__)
app.secret_key = "xtracash_secret"
DB = "xtracash.db"
NOWPAYMENTS_API_KEY = "bMecyltCU7dw/2I40tS3cGeLOPD3eDlo"
NOWPAYMENTS_URL = "https://api.nowpayments.io/v1/invoice"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, balance INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY, sender TEXT, receiver TEXT, amount INTEGER, timestamp TEXT)")
    conn.commit()
    conn.close()

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def get_balance(username):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

@app.route("/", methods=["GET"])
def index():
    if "username" in session:
        balance = get_balance(session["username"])
        return render_template("index.html", balance=balance)
    return render_template("index.html")

@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = hash_password(request.form["password"])
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, balance) VALUES (?, ?, ?)", (username, password, 0))
        conn.commit()
    except:
        pass
    conn.close()
    session["username"] = username
    return redirect("/")

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = hash_password(request.form["password"])
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    if c.fetchone():
        session["username"] = username
    conn.close()
    return redirect("/")

@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect("/")

@app.route("/send", methods=["POST"])
def send():
    if "username" not in session:
        return redirect("/")
    sender = session["username"]
    receiver = request.form["to"]
    amount = int(request.form["amount"])
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE username = ?", (sender,))
    sender_balance = c.fetchone()
    if not sender_balance or sender_balance[0] < amount:
        conn.close()
        return "Not enough XTRA", 400
    c.execute("UPDATE users SET balance = balance - ? WHERE username = ?", (amount, sender))
    c.execute("UPDATE users SET balance = balance + ? WHERE username = ?", (amount, receiver))
    c.execute("INSERT INTO transactions (sender, receiver, amount, timestamp) VALUES (?, ?, ?, ?)",
              (sender, receiver, amount, time.ctime()))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/topup_real", methods=["POST"])
def topup_real():
    if "username" not in session:
        return redirect("/")
    xtra_amount = int(request.form["amount"])
    pay_currency = request.form["pay_currency"]
    price_per_xtra = 0.05
    usd_amount = round(xtra_amount * price_per_xtra, 2)

    payload = {
        "price_amount": usd_amount,
        "price_currency": "usd",
        "pay_currency": pay_currency,
        "order_id": f"{session['username']}_{int(time.time())}",
        "order_description": f"Top up {xtra_amount} XTRA",
        "ipn_callback_url": "https://yourdomain.com/ipn",
        "success_url": "http://localhost:5000",
        "cancel_url": "http://localhost:5000",
    }

    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(NOWPAYMENTS_URL, json=payload, headers=headers)
    if response.status_code == 200:
        invoice_url = response.json().get("invoice_url")
        return redirect(invoice_url)
    else:
        return f"Error: {response.text}", 500

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
