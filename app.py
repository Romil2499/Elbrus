import os, re, secrets, hashlib, sqlite3, smtplib, random, time

from datetime import datetime, timedelta

from email.message import EmailMessage

from functools import wraps



from flask import Flask, render_template, request, jsonify, session, g

from werkzeug.security import generate_password_hash, check_password_hash

from dotenv import load_dotenv



load_dotenv()



app = Flask(__name__, static_folder="static", template_folder="templates")

app.secret_key = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_KEY")

app.config["SESSION_COOKIE_HTTPONLY"] = True

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"



BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "el_brusto.db")



EMAIL_HOST = os.getenv("MAIL_HOST", "smtp.gmail.com")

EMAIL_PORT = int(os.getenv("MAIL_PORT", "587"))

EMAIL_USER = os.getenv("MAIL_USERNAME", "")

EMAIL_PASS = os.getenv("MAIL_PASSWORD", "")

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")

TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")

TWILIO_FROM = os.getenv("TWILIO_FROM_NUMBER", "")

print("SMTP host:", EMAIL_HOST)

print("SMTP port:", EMAIL_PORT)

print("SMTP username configured:", bool(EMAIL_USER))

print("SMTP password configured:", bool(EMAIL_PASS))

OTP_EXPIRY_MINUTES = 10

DEV_SHOW_OTP = os.getenv("DEV_SHOW_OTP", "false").lower() == "true"



def db():

    if "db" not in g:

        g.db = sqlite3.connect(DB_PATH)

        g.db.row_factory = sqlite3.Row

        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db



@app.teardown_appcontext

def close_db(exception=None):

    conn = g.pop("db", None)

    if conn:

        conn.close()



def init_db():

    conn = sqlite3.connect(DB_PATH)

    conn.executescript("""

    CREATE TABLE IF NOT EXISTS users (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        first_name TEXT NOT NULL,

        last_name TEXT NOT NULL,

        age INTEGER NOT NULL,

        email TEXT NOT NULL UNIQUE,

        phone TEXT NOT NULL UNIQUE,

        address TEXT NOT NULL,

        postal_code TEXT NOT NULL,

        password_hash TEXT NOT NULL,

        email_verified INTEGER NOT NULL DEFAULT 0,

        phone_verified INTEGER NOT NULL DEFAULT 0,

        created_at TEXT NOT NULL

    );



    CREATE TABLE IF NOT EXISTS registration_otps (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        token TEXT NOT NULL UNIQUE,

        payload_json TEXT NOT NULL,

        email_hash TEXT NOT NULL,

        phone_hash TEXT NOT NULL,

        email_otp_hash TEXT NOT NULL,

        phone_otp_hash TEXT NOT NULL,

        expires_at TEXT NOT NULL,

        attempts INTEGER NOT NULL DEFAULT 0,

        created_at TEXT NOT NULL

    );



    CREATE TABLE IF NOT EXISTS cart_items (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER NOT NULL,

        name TEXT NOT NULL,

        price REAL NOT NULL,

        image TEXT NOT NULL,

        quantity INTEGER NOT NULL DEFAULT 1,

        UNIQUE(user_id, name),

        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE

    );



    CREATE TABLE IF NOT EXISTS orders (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER NOT NULL,

        address TEXT NOT NULL,

        postal_code TEXT NOT NULL,

        phone TEXT NOT NULL,

        note TEXT,

        total REAL NOT NULL,

        status TEXT NOT NULL DEFAULT 'Pending',

        created_at TEXT NOT NULL,

        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE

    );



    CREATE TABLE IF NOT EXISTS order_items (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        order_id INTEGER NOT NULL,

        name TEXT NOT NULL,

        price REAL NOT NULL,

        quantity INTEGER NOT NULL,

        subtotal REAL NOT NULL,

        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE

    );

    """)

    conn.commit()

    conn.close()



def now():

    return datetime.utcnow()



def normalize_phone(phone):

    p = re.sub(r"\D", "", str(phone or ""))

    if p.startswith("09") and len(p) == 11:

        return "+63" + p[1:]

    if p.startswith("63") and len(p) == 12:

        return "+" + p

    if p.startswith("+63") and len(p) == 13:

        return p

    return None



def hash_otp(code):

    return hashlib.sha256(code.encode()).hexdigest()



def make_otp():

    return f"{secrets.randbelow(1000000):06d}"



def mask_email(email):

    name, domain = email.split("@", 1)

    return (name[:2] + "***" if len(name) > 2 else "***") + "@" + domain



def mask_phone(phone):

    digits = re.sub(r"\D", "", phone)

    return digits[:2] + "******" + digits[-2:]





def send_email_otp(to_email, code):

    if not EMAIL_USER or not EMAIL_PASS:

        raise RuntimeError(

            "Gmail SMTP is not configured. "

            "Set MAIL_USERNAME and MAIL_PASSWORD in .env."

        )



    msg = EmailMessage()

    msg["Subject"] = "EL BRUSTO - Account Verification OTP"

    msg["From"] = EMAIL_USER

    msg["To"] = to_email

    msg.set_content(

        f"Your EL BRUSTO verification code is: {code}\n\n"

        f"This code expires in {OTP_EXPIRY_MINUTES} minutes. "

        "Do not share it with anyone."

    )



    import ssl



    context = ssl.create_default_context()



    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=30) as smtp:

        smtp.ehlo()

        smtp.starttls(context=context)

        smtp.ehlo()

        smtp.login(EMAIL_USER, EMAIL_PASS)

        smtp.send_message(msg)





def send_sms_otp(to_phone, code):

    if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM]):

        raise RuntimeError("SMS OTP is not configured. Set Twilio credentials in .env.")

    from twilio.rest import Client

    Client(TWILIO_SID, TWILIO_TOKEN).messages.create(

        body=f"EL BRUSTO verification code: {code}. Expires in {OTP_EXPIRY_MINUTES} minutes.",

        from_=TWILIO_FROM,

        to=to_phone

    )



def login_required(fn):

    @wraps(fn)

    def wrapped(*args, **kwargs):

        uid = session.get("user_id")

        if not uid:

            return jsonify(error="LOGIN_REQUIRED"), 401

        return fn(*args, **kwargs)

    return wrapped



@app.route("/")

def index():

    return render_template("index.html")



@app.post("/api/register/start")

def register_start():

    data = request.get_json(force=True)

    required = ["first_name","last_name","age","email","phone","address","postal_code","password","confirm_password"]

    if any(not str(data.get(k, "")).strip() for k in required):

        return jsonify(error="Please complete all registration fields."), 400

    if data["password"] != data["confirm_password"]:

        return jsonify(error="Passwords do not match."), 400

    if len(data["password"]) < 8:

        return jsonify(error="Password must be at least 8 characters."), 400

    try:

        age = int(data["age"])

    except ValueError:

        return jsonify(error="Age must be a number."), 400

    if age < 1 or age > 120:

        return jsonify(error="Please enter a valid age."), 400



    email = str(data["email"]).strip().lower()

    phone = normalize_phone(data["phone"])

    if not phone:

        return jsonify(error="Enter a valid Philippine mobile number such as 09XXXXXXXXX."), 400



    conn = db()

    if conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():

        return jsonify(error="An account with that email already exists."), 400

    if conn.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone():

        return jsonify(error="An account with that phone number already exists."), 400



    email_otp, phone_otp = make_otp(), make_otp()

    token = secrets.token_urlsafe(32)

    payload = {

        "first_name": str(data["first_name"]).strip(),

        "last_name": str(data["last_name"]).strip(),

        "age": age,

        "email": email,

        "phone": phone,

        "address": str(data["address"]).strip(),

        "postal_code": str(data["postal_code"]).strip(),

        "password_hash": generate_password_hash(data["password"])

    }

    expires = now() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    conn.execute("DELETE FROM registration_otps WHERE expires_at < ?", (now().isoformat(),))

    conn.execute(

        """INSERT INTO registration_otps

        (token,payload_json,email_hash,phone_hash,email_otp_hash,phone_otp_hash,expires_at,created_at)

        VALUES (?,?,?,?,?,?,?,?)""",

        (token, __import__("json").dumps(payload), hash_otp(email), hash_otp(phone),

         hash_otp(email_otp), hash_otp(phone_otp), expires.isoformat(), now().isoformat())

    )

    conn.commit()



    send_error = None

    try:

        send_email_otp(email, email_otp)

    except Exception:

        app.logger.exception("Gmail OTP delivery failed")

        send_error = "Gmail OTP could not be sent. Check MAIL_USERNAME and MAIL_PASSWORD in your .env file, then try Resend OTP."



    response = {"token": token, "masked_email": mask_email(email)}

    if send_error:

        response["delivery_error"] = send_error

    if DEV_SHOW_OTP:

        response["dev_email_otp"] = email_otp

    return jsonify(response), 200



@app.post("/api/register/resend")

def register_resend():

    data = request.get_json(force=True)

    row = db().execute("SELECT * FROM registration_otps WHERE token=?", (data.get("token"),)).fetchone()

    if not row:

        return jsonify(error="Registration session expired. Start again."), 400

    import json

    payload = json.loads(row["payload_json"])

    email_otp, phone_otp = make_otp(), make_otp()

    expires = now() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    db().execute(

        "UPDATE registration_otps SET email_otp_hash=?, phone_otp_hash=?, expires_at=?, attempts=0 WHERE token=?",

        (hash_otp(email_otp), hash_otp(phone_otp), expires.isoformat(), row["token"])

    )

    db().commit()

    send_error = None

    try:

        send_email_otp(payload["email"], email_otp)

    except Exception:

        app.logger.exception("Gmail OTP resend failed")

        send_error = "Gmail OTP could not be sent. Check your Gmail SMTP settings in .env and try again."

    response = {"token":row["token"], "masked_email":mask_email(payload["email"])}

    if send_error:

        response["delivery_error"] = send_error

    if DEV_SHOW_OTP:

        response["dev_email_otp"] = email_otp

    return jsonify(response)



@app.post("/api/register/verify")

def register_verify():

    data = request.get_json(force=True)

    row = db().execute("SELECT * FROM registration_otps WHERE token=?", (data.get("token"),)).fetchone()

    if not row:

        return jsonify(error="Registration session expired. Start again."), 400

    if datetime.fromisoformat(row["expires_at"]) < now():

        return jsonify(error="OTP expired. Request a new OTP."), 400

    if row["attempts"] >= 5:

        return jsonify(error="Too many incorrect OTP attempts. Request a new OTP."), 429

    if not re.fullmatch(r"\d{6}", str(data.get("email_otp", ""))) or hash_otp(str(data.get("email_otp",""))) != row["email_otp_hash"]:

        db().execute("UPDATE registration_otps SET attempts=attempts+1 WHERE token=?", (row["token"],))

        db().commit()

        return jsonify(error="One or both OTP codes are incorrect."), 400



    import json

    p = json.loads(row["payload_json"])

    try:

        db().execute(

            """INSERT INTO users

            (first_name,last_name,age,email,phone,address,postal_code,password_hash,email_verified,phone_verified,created_at)

            VALUES (?,?,?,?,?,?,?,?,1,1,?)""",

            (p["first_name"],p["last_name"],p["age"],p["email"],p["phone"],p["address"],p["postal_code"],p["password_hash"],now().isoformat())

        )

        db().execute("DELETE FROM registration_otps WHERE token=?", (row["token"],))

        db().commit()

    except sqlite3.IntegrityError:

        return jsonify(error="Email or phone number is already registered."), 400

    return jsonify(ok=True)



@app.post("/api/login")

def login():

    data = request.get_json(force=True)

    email = str(data.get("email","")).strip().lower()

    user = db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

    if not user or not check_password_hash(user["password_hash"], str(data.get("password",""))):

        return jsonify(error="Incorrect email or password."), 401

    if not user["email_verified"] or not user["phone_verified"]:

        return jsonify(error="This account has not completed verification."), 403

    session.clear()

    session["user_id"] = user["id"]

    return jsonify(ok=True)



@app.post("/api/logout")

def logout():

    session.clear()

    return jsonify(ok=True)



def user_row():

    uid=session.get("user_id")

    if not uid: return None

    return db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()



@app.get("/api/me")

def me():

    u=user_row()

    if not u: return jsonify(logged_in=False)

    return jsonify(logged_in=True,user={

        "id":u["id"],"first_name":u["first_name"],"last_name":u["last_name"],

        "age":u["age"],"email":u["email"],"phone":u["phone"],

        "address":u["address"],"postal_code":u["postal_code"]

    })



@app.put("/api/profile")

@login_required

def profile_update():

    d=request.get_json(force=True)

    first=str(d.get("first_name","")).strip()

    last=str(d.get("last_name","")).strip()

    address=str(d.get("address","")).strip()

    postal=str(d.get("postal_code","")).strip()

    try: age=int(d.get("age"))

    except: return jsonify(error="Age must be a number."),400

    if not first or not last or not address or not postal or not (1<=age<=120):

        return jsonify(error="Please complete the profile fields."),400

    db().execute("UPDATE users SET first_name=?,last_name=?,age=?,address=?,postal_code=? WHERE id=?",

                 (first,last,age,address,postal,session["user_id"]))

    db().commit()

    return jsonify(ok=True)



@app.get("/api/cart")

@login_required

def get_cart():

    rows=db().execute("SELECT * FROM cart_items WHERE user_id=? ORDER BY id", (session["user_id"],)).fetchall()

    items=[]

    total=0

    for r in rows:

        subtotal=r["price"]*r["quantity"]; total+=subtotal

        items.append({"id":r["id"],"name":r["name"],"price":r["price"],"image":r["image"],"quantity":r["quantity"],"subtotal":subtotal})

    return jsonify(items=items,total=total)



@app.post("/api/cart")

@login_required

def add_cart():

    d=request.get_json(force=True)

    try: price=float(d["price"])

    except: return jsonify(error="Invalid product price."),400

    name=str(d.get("name","")).strip()

    image=str(d.get("image","")).strip()

    if not name or not image or price<=0:return jsonify(error="Invalid product."),400

    conn=db()

    row=conn.execute("SELECT id FROM cart_items WHERE user_id=? AND name=?", (session["user_id"],name)).fetchone()

    if row: conn.execute("UPDATE cart_items SET quantity=quantity+1 WHERE id=?", (row["id"],))

    else: conn.execute("INSERT INTO cart_items(user_id,name,price,image,quantity) VALUES(?,?,?,?,1)", (session["user_id"],name,price,image))

    conn.commit()

    return jsonify(ok=True)



@app.put("/api/cart/\<int:item_id>")

@login_required

def update_cart(item_id):

    q=int(request.get_json(force=True).get("quantity",1))

    if q<=0:

        db().execute("DELETE FROM cart_items WHERE id=? AND user_id=?", (item_id,session["user_id"]))

    else:

        db().execute("UPDATE cart_items SET quantity=? WHERE id=? AND user_id=?", (q,item_id,session["user_id"]))

    db().commit()

    return jsonify(ok=True)



@app.delete("/api/cart/\<int:item_id>")

@login_required

def delete_cart(item_id):

    db().execute("DELETE FROM cart_items WHERE id=? AND user_id=?", (item_id,session["user_id"]))

    db().commit()

    return jsonify(ok=True)



@app.post("/api/orders")

@login_required

def create_order():

    d=request.get_json(force=True)

    address=str(d.get("address","")).strip()

    postal=str(d.get("postal_code","")).strip()

    phone=normalize_phone(d.get("phone"))

    note=str(d.get("note","")).strip()

    if not address or not postal or not phone:

        return jsonify(error="Please complete the checkout details."),400

    conn=db()

    items=conn.execute("SELECT * FROM cart_items WHERE user_id=?", (session["user_id"],)).fetchall()

    if not items:return jsonify(error="Your cart is empty."),400

    total=sum(r["price"]*r["quantity"] for r in items)

    cur=conn.execute("INSERT INTO orders(user_id,address,postal_code,phone,note,total,status,created_at) VALUES(?,?,?,?,?,?,?,?)",

                      (session["user_id"],address,postal,phone,note,total,"Pending",now().isoformat()))

    order_id=cur.lastrowid

    for r in items:

        conn.execute("INSERT INTO order_items(order_id,name,price,quantity,subtotal) VALUES(?,?,?,?,?)",

                     (order_id,r["name"],r["price"],r["quantity"],r["price"]*r["quantity"]))

    conn.execute("DELETE FROM cart_items WHERE user_id=?", (session["user_id"],))

    conn.commit()

    return jsonify(ok=True,order_id=order_id,total=total)



@app.get("/api/orders")

@login_required

def orders():

    rows=db().execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (session["user_id"],)).fetchall()

    return jsonify(orders=[dict(r) for r in rows])



if __name__ == "__main__":

    init_db()

    app.run(host="127.0.0.1", port=int(os.getenv("PORT","5000")), debug=True)
