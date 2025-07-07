from flask import Flask, request, jsonify, render_template_string, redirect, session
import sqlite3
import hashlib
import time
import requests

app = Flask(__name__)
app.secret_key = "xtracash_secret"
DB = "xtracash.db"
NOWPAYMENTS_API_KEY = "bMecyltCU7dw/2I40tS3cGeLOPD3eDlo"
NOWPAYMENTS_URL = "https://api.nowpayments.io/v1/invoice"

template = """
<!DOCTYPE html>
<html lang="en" class="bg-gray-900 text-white">
<head>
  <meta charset="UTF-8" />
  <title>XtraCash Wallet</title>
  <script src='https://cdn.tailwindcss.com'></script>
</head>
<body class="p-4">
  <div class="max-w-xl mx-auto mt-10 bg-gray-800 rounded-2xl p-6 shadow-xl">
    {% if not session.username %}
      <h1 class="text-2xl mb-4">Welcome to XtraCash 💸</h1>
      <form method="post" action="/register" class="mb-4">
        <input name="username" placeholder="Username" class="w-full p-2 rounded mb-2 text-black" />
        <input name="password" type="password" placeholder="Password" class="w-full p-2 rounded mb-2 text-black" />
        <button class="bg-green-600 px-4 py-2 rounded">Register</button>
      </form>
      <form method="post" action="/login">
        <input name="username" placeholder="Username" class="w-full p-2 rounded mb-2 text-black" />
        <input name="password" type="password" placeholder="Password" class="w-full p-2 rounded mb-2 text-black" />
        <button class="bg-blue-600 px-4 py-2 rounded">Login</button>
      </form>
    {% else %}
      <h1 class="text-xl mb-2">Hello, {{ session.username }} 👋</h1>
      <p class="mb-2">Balance: <strong>{{ balance }}</strong> XTRA</p>
      <form method="post" action="/send" class="mb-4">
        <input name="to" placeholder="Send to user" class="w-full p-2 rounded mb-2 text-black" />
        <input name="amount" placeholder="Amount" type="number" class="w-full p-2 rounded mb-2 text-black" />
        <button class="bg-yellow-500 px-4 py-2 rounded">Send</button>
      </form>
      <form method="post" action="/topup_real" class="mb-4">
        <input name="amount" placeholder="Top up XTRA amount" type="number" class="w-full p-2 rounded mb-2 text-black" />
        <select name="pay_currency" class="w-full p-2 rounded mb-2 text-black">
          <option value="usd">USD (Card/Crypto)</option>
          <option value="btc">Bitcoin</option>
          <option value="eth">Ethereum</option>
          <option value="usdt">USDT</option>
        </select>
        <button class="bg-purple-600 px-4 py-2 rounded">Pay with Crypto / Card</button>
      </form>
      <a href="/logout" class="text-red-400">Logout</a>
    {% endif %}
  </div>
</body>
</html>
"""

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
        return render_template_string(template, balance=balance)
    return render_template_string(template)

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
    price_per_xtra = 0.05  # $0.05 за 1 XTRA
    usd_amount = round(xtra_amount * price_per_xtra, 2)

    payload = {
        "price_amount": usd_amount,
        "price_currency": "usd",
        "pay_currency": pay_currency,
        "order_id": f"{session['username']}_{int(time.time())}",
        "order_description": f"Top up {xtra_amount} XTRA",
        "ipn_callback_url": "https://yourdomain.com/ipn",  # можно игнорировать для локального
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
from flask import Flask, request, jsonify, render_template_string, redirect, session
import sqlite3
import hashlib
import time
import requests
import os

app = Flask(__name__)
app.secret_key = "xtracash_secret"
DB = "xtracash.db"
NOWPAYMENTS_API_KEY = "bMecyltCU7dw/2I40tS3cGeLOPD3eDlo"
NOWPAYMENTS_URL = "https://api.nowpayments.io/v1/invoice"

# 👇 UI шаблон и все маршруты остаются без изменений
# (из предыдущего сообщения можно скопировать всё остальное как есть)

# в самом конце:
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
  
