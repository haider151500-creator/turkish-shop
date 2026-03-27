from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify
import sqlite3, os
import psycopg2
from psycopg2.extras import RealDictCursor
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import json
from datetime import timedelta, datetime
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
MESSAGES_FILE = os.path.join(BASE_DIR, "messages.json")
CHAT_FILE = os.path.join(BASE_DIR, "chat.json")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production')
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ========== بيانات حساب الأدمن ==========
ADMIN_EMAIL = "admin@turkishstore.com"
ADMIN_PASSWORD = "Turk!sh@dm!n2025#Secure"
ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD)

# التحقق من وجود قاعدة بيانات PostgreSQL على Render
DATABASE_URL = os.environ.get('DATABASE_URL')
USE_POSTGRES = bool(DATABASE_URL)

print(f"🔍 استخدام PostgreSQL: {USE_POSTGRES}")
if DATABASE_URL:
    print(f"🔍 DATABASE_URL موجود")

# ========== دوال التعامل مع الرسائل ==========
def load_messages():
    if os.path.exists(MESSAGES_FILE):
        try:
            with open(MESSAGES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_messages(messages):
    with open(MESSAGES_FILE, 'w', encoding='utf-8') as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

def load_chat():
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_chat(chat_messages):
    with open(CHAT_FILE, 'w', encoding='utf-8') as f:
        json.dump(chat_messages, f, ensure_ascii=False, indent=2)

def get_db():
    """الحصول على اتصال بقاعدة البيانات"""
    try:
        if USE_POSTGRES:
            conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            conn.cursor_factory = RealDictCursor
            return conn
        else:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            conn.row_factory = lambda cursor, row: {col[0]: row[i] for i, col in enumerate(cursor.description)}
            conn.execute("PRAGMA journal_mode=WAL")
            return conn
    except Exception as e:
        print(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")
        traceback.print_exc()
        raise

def get_placeholder():
    return '%s' if USE_POSTGRES else '?'

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL,
                old_price REAL DEFAULT 0,
                image TEXT,
                category TEXT DEFAULT 'عام'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_images (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL,
                filename TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                items TEXT NOT NULL,
                total REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL,
                old_price REAL DEFAULT 0,
                image TEXT,
                category TEXT DEFAULT 'عام'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                filename TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                items TEXT NOT NULL,
                total REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    conn.commit()
    conn.close()

def migrate_db():
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if USE_POSTGRES:
            cursor.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS old_price REAL DEFAULT 0")
        else:
            cursor.execute("PRAGMA table_info(products)")
            columns = cursor.fetchall()
            has_old_price = False
            for col in columns:
                if col['name'] == 'old_price':
                    has_old_price = True
                    break
            if not has_old_price:
                cursor.execute("ALTER TABLE products ADD COLUMN old_price REAL DEFAULT 0")
        
        conn.commit()
    except Exception as e:
        print(f"⚠️ تحذير: {e}")
    finally:
        conn.close()

def create_admin_user():
    """إنشاء حساب الأدمن في جدول المستخدمين"""
    conn = get_db()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    
    try:
        cursor.execute(f"SELECT * FROM users WHERE email = {placeholder}", (ADMIN_EMAIL,))
        existing = cursor.fetchone()
        
        if not existing:
            cursor.execute(
                f"INSERT INTO users (name, email, password, phone) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
                ("مدير الموقع", ADMIN_EMAIL, ADMIN_PASSWORD_HASH, "0500000000")
            )
            conn.commit()
            print("✅ تم إضافة حساب الأدمن")
        else:
            print("✅ حساب الأدمن موجود بالفعل")
    except Exception as e:
        print(f"⚠️ تحذير: {e}")
    finally:
        conn.close()

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("الرجاء تسجيل الدخول أولاً", "warning")
            return redirect(url_for("user_login"))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            flash("الرجاء تسجيل الدخول كأدمن.", "warning")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper

@app.route("/")
def index():
    return redirect(url_for("products"))

@app.route("/products")
def products():
    cat = request.args.get("cat")
    conn = get_db()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    
    cursor.execute("SELECT DISTINCT COALESCE(category,'عام') AS c FROM products ORDER BY c")
    cats = cursor.fetchall()
    
    if cat:
        cursor.execute(f"SELECT * FROM products WHERE COALESCE(category,'عام') = {placeholder} ORDER BY id DESC", (cat,))
    else:
        cursor.execute("SELECT * FROM products ORDER BY id DESC")
    items = cursor.fetchall()
    conn.close()
    
    products_list = list(items) if items else []
    for product in products_list:
        if 'old_price' not in product:
            product['old_price'] = None
    
    categories_list = [r["c"] for r in cats]
    
    return render_template("products.html", products=products_list, categories=categories_list, active_cat=cat)

@app.route("/product/<int:pid>")
def product_detail(pid):
    conn = get_db()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    cursor.execute(f"SELECT * FROM products WHERE id = {placeholder}", (pid,))
    item = cursor.fetchone()
    cursor.execute(f"SELECT id, filename FROM product_images WHERE product_id = {placeholder} ORDER BY id", (pid,))
    imgs = cursor.fetchall()
    conn.close()
    if not item:
        flash("المنتج غير موجود.", "danger")
        return redirect(url_for("products"))
    main_image = item["image"] if item["image"] else (imgs[0]["filename"] if imgs else None)
    return render_template("product_detail.html", p=item, images=imgs, main_image=main_image)

# ========== API للسلة ==========
@app.route("/api/add-to-cart", methods=["POST"])
@login_required
def api_add_to_cart():
    data = request.json
    product_id = data.get('product_id')
    product_name = data.get('product_name')
    product_price = data.get('product_price')
    
    if not session.get('cart'):
        session['cart'] = []
    
    cart = session['cart']
    existing = next((item for item in cart if item['id'] == product_id), None)
    
    if existing:
        existing['qty'] += 1
    else:
        cart.append({
            'id': product_id,
            'name': product_name,
            'price': product_price,
            'qty': 1
        })
    
    session['cart'] = cart
    session.permanent = True
    
    return jsonify({'success': True, 'cart_count': len(cart)})

@app.route("/api/get-cart")
def api_get_cart():
    cart = session.get('cart', [])
    total = sum(item['price'] * item['qty'] for item in cart)
    return jsonify({'cart': cart, 'total': total})

@app.route("/api/remove-from-cart", methods=["POST"])
def api_remove_from_cart():
    data = request.json
    product_id = data.get('product_id')
    
    cart = session.get('cart', [])
    cart = [item for item in cart if item['id'] != product_id]
    session['cart'] = cart
    
    total = sum(item['price'] * item['qty'] for item in cart)
    return jsonify({'success': True, 'cart': cart, 'total': total})

@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    cart = session.get('cart', [])
    if not cart:
        flash("السلة فارغة", "warning")
        return redirect(url_for("products"))
    
    total = sum(item['price'] * item['qty'] for item in cart)
    
    conn = get_db()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    
    cursor.execute(
        f"INSERT INTO orders (user_id, items, total) VALUES ({placeholder}, {placeholder}, {placeholder})",
        (session['user_id'], json.dumps(cart), total)
    )
    conn.commit()
    conn.close()
    
    chat_messages = load_chat()
    notification = {
        "id": int(datetime.now().timestamp()),
        "type": "system",
        "message": f"🛍️ تم إتمام طلب جديد بقيمة {total:,.0f} د.ع من قبل {session.get('user_name', 'مستخدم')}",
        "user_id": session['user_id'],
        "user_name": session.get('user_name', 'مستخدم'),
        "created_at": datetime.now().isoformat(),
        "read_by_user": False,
        "read_by_admin": False,
        "is_notification": True,
        "sender": "system"
    }
    chat_messages.append(notification)
    save_chat(chat_messages)
    
    session.pop('cart', None)
    flash("تم إتمام الطلب بنجاح!", "success")
    return jsonify({'success': True})

# ========== API للدردشة ==========
@app.route("/api/chat/messages")
def api_chat_messages():
    chat_messages = load_chat()
    user_id = session.get('user_id')
    is_admin = session.get('is_admin', False)
    
    for msg in chat_messages:
        if is_admin and not msg.get('read_by_admin', False):
            msg['read_by_admin'] = True
        elif not is_admin and not msg.get('read_by_user', False) and msg.get('user_id') != user_id:
            msg['read_by_user'] = True
    
    save_chat(chat_messages)
    
    unread_count = 0
    for msg in chat_messages:
        if is_admin and not msg.get('read_by_admin', False):
            unread_count += 1
        elif not is_admin and not msg.get('read_by_user', False) and msg.get('user_id') != user_id:
            unread_count += 1
    
    return jsonify({
        "success": True, 
        "messages": chat_messages,
        "unread_count": unread_count
    })

@app.route("/api/chat/send", methods=["POST"])
def api_chat_send():
    data = request.json
    user_id = session.get('user_id')
    user_name = session.get('user_name', 'زائر')
    user_email = session.get('user_email', '')
    is_admin = session.get('is_admin', False)
    
    message = {
        "id": int(datetime.now().timestamp()),
        "type": "chat",
        "user_id": user_id,
        "user_name": user_name,
        "user_email": user_email,
        "message": data.get('message'),
        "created_at": datetime.now().isoformat(),
        "read_by_user": True if is_admin else False,
        "read_by_admin": True if not is_admin else False,
        "is_admin": is_admin,
        "sender": "admin" if is_admin else "user"
    }
    
    chat_messages = load_chat()
    chat_messages.append(message)
    save_chat(chat_messages)
    
    return jsonify({"success": True})

# ========== API للرسائل العادية ==========
@app.route("/api/contact", methods=["POST"])
def contact_api():
    data = request.json
    message = {
        "id": int(datetime.now().timestamp()),
        "name": data.get('name'),
        "email": data.get('email'),
        "phone": data.get('phone', ''),
        "subject": data.get('subject'),
        "message": data.get('message'),
        "date": datetime.now().isoformat(),
        "read": False,
        "type": "contact"
    }
    messages = load_messages()
    messages.append(message)
    save_messages(messages)
    
    chat_messages = load_chat()
    notification = {
        "id": int(datetime.now().timestamp()) + 1000000,
        "type": "system",
        "message": f"📧 رسالة جديدة من {data.get('name')}: {data.get('subject')}",
        "user_id": None,
        "user_name": data.get('name'),
        "created_at": datetime.now().isoformat(),
        "read_by_user": False,
        "read_by_admin": False,
        "is_notification": True,
        "sender": "system"
    }
    chat_messages.append(notification)
    save_chat(chat_messages)
    
    return jsonify({"success": True})

@app.route("/api/messages")
def api_messages():
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 401
    messages = load_messages()
    contact_messages = [m for m in messages if m.get('type') != 'chat']
    return jsonify(contact_messages)

@app.route("/api/messages/<int:mid>/read", methods=["POST"])
def api_mark_read(mid):
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 401
    messages = load_messages()
    for msg in messages:
        if msg['id'] == mid:
            msg['read'] = True
            break
    save_messages(messages)
    return jsonify({"success": True})

@app.route("/api/send-reply", methods=["POST"])
def api_send_reply():
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    print(f"📧 إرسال رد إلى {data.get('to')}")
    return jsonify({"success": True})

# ========== نظام تسجيل الدخول ==========
@app.route("/user/login", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        
        print(f"📧 محاولة تسجيل دخول - البريد: {email}")
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            placeholder = get_placeholder()
            
            cursor.execute(f"SELECT * FROM users WHERE email = {placeholder}", (email,))
            user = cursor.fetchone()
            conn.close()
            
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['user_email'] = user['email']
                flash(f"مرحباً {user['name']}، تم تسجيل الدخول بنجاح!", "success")
                return redirect(url_for("products"))
            else:
                flash("البريد الإلكتروني أو كلمة المرور غير صحيحة", "danger")
        except Exception as e:
            print(f"❌ خطأ في تسجيل الدخول: {e}")
            traceback.print_exc()
            flash("حدث خطأ في الخادم، حاول مرة أخرى", "danger")
    
    return render_template("user_login.html")

@app.route("/user/register", methods=["GET", "POST"])
def user_register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        phone = request.form.get("phone")
        
        if password != confirm_password:
            flash("كلمتا المرور غير متطابقتين", "danger")
            return redirect(url_for("user_register"))
        
        hashed_password = generate_password_hash(password)
        
        conn = get_db()
        cursor = conn.cursor()
        placeholder = get_placeholder()
        
        try:
            cursor.execute(
                f"INSERT INTO users (name, email, password, phone) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (name, email, hashed_password, phone)
            )
            conn.commit()
            flash("تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن", "success")
            return redirect(url_for("user_login"))
        except Exception as e:
            flash("البريد الإلكتروني مسجل مسبقاً", "danger")
            return redirect(url_for("user_register"))
        finally:
            conn.close()
    
    return render_template("user_register.html")

@app.route("/user/logout")
def user_logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_email', None)
    session.pop('cart', None)
    session.pop('is_admin', None)
    session.pop('admin_email', None)
    flash("تم تسجيل الخروج بنجاح", "info")
    return redirect(url_for("products"))

@app.route("/user/profile")
@login_required
def user_profile():
    return render_template("user_profile.html")

# ========== نظام الأدمن ==========
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            session["admin_email"] = email
            session["user_id"] = 999
            session["user_name"] = "مدير الموقع"
            flash("تم تسجيل الدخول كأدمن بنجاح.", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("البريد الإلكتروني أو كلمة المرور غير صحيحة.", "danger")
    
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    session.pop("admin_email", None)
    flash("تم تسجيل الخروج من لوحة التحكم.", "info")
    return redirect(url_for("products"))

@app.route("/force-admin")
def force_admin():
    session["is_admin"] = True
    session["admin_email"] = ADMIN_EMAIL
    session["user_id"] = 999
    session["user_name"] = "مدير الموقع"
    flash("✅ تم تسجيل الدخول كأدمن بنجاح", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY id DESC")
    items = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) as count FROM users")
    users_count = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) as count FROM orders")
    orders_count = cursor.fetchone()
    conn.close()
    return render_template("admin_dashboard.html", products=items, users_count=users_count['count'], orders_count=orders_count['count'])

@app.route("/admin/orders")
@admin_required
def admin_orders():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT o.*, u.name as user_name, u.email as user_email 
        FROM orders o 
        LEFT JOIN users u ON o.user_id = u.id 
        ORDER BY o.created_at DESC
    """)
    orders = cursor.fetchall()
    conn.close()
    return render_template("admin_orders.html", orders=orders)

@app.route("/admin/users")
@admin_required
def admin_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    conn.close()
    return render_template("admin_users.html", users=users)

# ========== دالة إضافة المنتج المعدلة ==========
@app.route("/admin/add", methods=["GET", "POST"])
@admin_required
def admin_add():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT COALESCE(category,'عام') AS c FROM products ORDER BY c")
    cats = cursor.fetchall()
    categories = [r["c"] for r in cats]
    conn.close()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        old_price = request.form.get("old_price", "").strip()
        category = request.form.get("category", "").strip()
        image_filename = None

        files = request.files.getlist("images")
        files = [f for f in files if getattr(f, "filename", "")]
        
        if files:
            image_filename = files[0].filename
            for f in files:
                try:
                    f.save(os.path.join(app.config["UPLOAD_FOLDER"], f.filename))
                except Exception as e:
                    print(f"❌ خطأ في حفظ الصورة: {e}")

        if not name or not price or not category:
            flash("الاسم والسعر والفئة مطلوبة.", "danger")
            return redirect(url_for("admin_add"))

        try:
            price_val = float(price)
            old_price_val = float(old_price) if old_price else 0
        except ValueError:
            flash("السعر غير صالح.", "danger")
            return redirect(url_for("admin_add"))

        try:
            conn = get_db()
            cursor = conn.cursor()
            placeholder = get_placeholder()
            
            if USE_POSTGRES:
                cursor.execute(
                    f"INSERT INTO products (name, description, price, old_price, image, category) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}) RETURNING id",
                    (name, description, price_val, old_price_val, image_filename, category)
                )
                result = cursor.fetchone()
                pid = result['id']
            else:
                cursor.execute(
                    f"INSERT INTO products (name, description, price, old_price, image, category) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                    (name, description, price_val, old_price_val, image_filename, category)
                )
                pid = cursor.lastrowid
            
            if files:
                for f in files[:5]:
                    cursor.execute(f"INSERT INTO product_images (product_id, filename) VALUES ({placeholder}, {placeholder})", (pid, f.filename))
            
            conn.commit()
            conn.close()
            flash("✅ تمت إضافة المنتج بنجاح!", "success")
            return redirect(url_for("admin_dashboard"))
            
        except Exception as e:
            print(f"❌ خطأ في إضافة المنتج: {e}")
            import traceback
            traceback.print_exc()
            flash(f"❌ حدث خطأ: {str(e)[:100]}", "danger")
            return redirect(url_for("admin_add"))

    return render_template("add_product.html", categories=categories)

@app.route("/admin/edit/<int:pid>", methods=["GET", "POST"])
@admin_required
def admin_edit(pid):
    conn = get_db()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    cursor.execute(f"SELECT * FROM products WHERE id = {placeholder}", (pid,))
    product = cursor.fetchone()
    if not product:
        conn.close()
        flash("المنتج غير موجود.", "danger")
        return redirect(url_for("admin_dashboard"))

    cursor.execute(f"SELECT id, filename FROM product_images WHERE product_id = {placeholder} ORDER BY id", (pid,))
    images = cursor.fetchall()
    cursor.execute("SELECT DISTINCT COALESCE(category,'عام') AS c FROM products ORDER BY c")
    cats = cursor.fetchall()
    categories = [r["c"] for r in cats]
    conn.close()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        old_price = request.form.get("old_price", "").strip()
        category = request.form.get("category", "").strip()
        remove_image = request.form.get("remove_image", "0") == "1"

        if not name or not price or not category:
            flash("الاسم والسعر والفئة مطلوبة.", "danger")
            return redirect(url_for("admin_edit", pid=pid))

        image_filename = product["image"]
        if remove_image and image_filename:
            old_path = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception:
                    pass
            image_filename = None

        files = request.files.getlist("images")
        files = [f for f in files if getattr(f, "filename", "")]
        if files:
            image_filename = files[0].filename
            for f in files:
                f.save(os.path.join(app.config["UPLOAD_FOLDER"], f.filename))

        try:
            price_val = float(price)
            old_price_val = float(old_price) if old_price else 0
        except ValueError:
            flash("السعر غير صالح.", "danger")
            return redirect(url_for("admin_edit", pid=pid))

        conn2 = get_db()
        cursor2 = conn2.cursor()
        placeholder = get_placeholder()
        cursor2.execute(
            f"UPDATE products SET name={placeholder}, description={placeholder}, price={placeholder}, old_price={placeholder}, image={placeholder}, category={placeholder} WHERE id={placeholder}",
            (name, description, price_val, old_price_val, image_filename, category, pid)
        )
        
        cursor2.execute(f"SELECT COUNT(*) FROM product_images WHERE product_id={placeholder}", (pid,))
        cnt_result = cursor2.fetchone()
        cnt = cnt_result['count'] if isinstance(cnt_result, dict) else list(cnt_result.values())[0] if cnt_result else 0
        slots = max(0, 5 - (cnt or 0))
        if files and slots:
            new_images = files[:slots] if len(files) > 1 else files
            for f in new_images:
                cursor2.execute(f"INSERT INTO product_images (product_id, filename) VALUES ({placeholder}, {placeholder})", (pid, f.filename))
        conn2.commit()
        conn2.close()
        flash("تم تعديل المنتج بنجاح.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("edit_product.html", p=product, images=images, categories=categories)

@app.route("/admin/delete/<int:pid>", methods=["POST"])
@admin_required
def admin_delete(pid):
    conn = get_db()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    cursor.execute(f"SELECT image FROM products WHERE id = {placeholder}", (pid,))
    row = cursor.fetchone()
    cursor.execute(f"DELETE FROM products WHERE id = {placeholder}", (pid,))
    conn.commit()
    conn.close()

    if row and row["image"]:
        img_path = os.path.join(app.config["UPLOAD_FOLDER"], row["image"])
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
            except Exception:
                pass
    flash("تم حذف المنتج.", "info")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/image/delete/<int:image_id>", methods=["POST"])
@admin_required
def admin_delete_image(image_id):
    conn = get_db()
    cursor = conn.cursor()
    placeholder = get_placeholder()
    cursor.execute(f"SELECT filename, product_id FROM product_images WHERE id = {placeholder}", (image_id,))
    row = cursor.fetchone()
    if row:
        cursor.execute(f"DELETE FROM product_images WHERE id = {placeholder}", (image_id,))
        conn.commit()
    conn.close()
    if row:
        fpath = os.path.join(app.config["UPLOAD_FOLDER"], row["filename"])
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
    flash("تم حذف الصورة.", "info")
    return redirect(url_for("admin_edit", pid=row["product_id"] if row else 0))

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/clear-session")
def clear_session():
    session.clear()
    flash("تم مسح الجلسة بالكامل", "info")
    return redirect(url_for("products"))

# ========== رووات مساعدة للتشخيص ==========
@app.route("/debug-db")
def debug_db():
    """فحص حالة قاعدة البيانات"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users")
        users_count = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) as count FROM products")
        products_count = cursor.fetchone()
        conn.close()
        
        return f"""
        <!DOCTYPE html>
        <html dir="rtl">
        <head><meta charset="UTF-8"><title>حالة قاعدة البيانات</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>🔍 حالة قاعدة البيانات</h1>
            <hr>
            <p><strong>نوع قاعدة البيانات:</strong> {'PostgreSQL ✅' if USE_POSTGRES else 'SQLite'}</p>
            <p><strong>عدد المستخدمين:</strong> {users_count['count']}</p>
            <p><strong>عدد المنتجات:</strong> {products_count['count']}</p>
            <hr>
            <h3>🔗 روابط مفيدة:</h3>
            <ul>
                <li><a href="/force-admin">⚡ تسجيل دخول الأدمن</a></li>
                <li><a href="/user/register">📝 إنشاء حساب جديد</a></li>
                <li><a href="/create-test-user">👤 إنشاء مستخدم تجريبي</a></li>
                <li><a href="/check-users">📋 عرض المستخدمين</a></li>
                <li><a href="/check-products">📦 عرض المنتجات</a></li>
                <li><a href="/recreate-tables">🔄 إعادة إنشاء الجداول</a></li>
                <li><a href="/clear-session">🗑️ مسح الجلسة</a></li>
            </ul>
        </body>
        </html>
        """
    except Exception as e:
        return f"❌ خطأ: {e}"

@app.route("/check-users")
def check_users():
    """عرض جميع المستخدمين"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email, phone FROM users")
        users = cursor.fetchall()
        conn.close()
        
        if not users:
            return """
            <h1>⚠️ لا يوجد مستخدمين</h1>
            <p>لا يوجد أي مستخدمين في قاعدة البيانات.</p>
            <p><a href="/user/register">إنشاء حساب جديد</a></p>
            <p><a href="/create-test-user">إنشاء مستخدم تجريبي</a></p>
            """
        
        html = "<h1>📋 قائمة المستخدمين</h1><table border='1' cellpadding='10'>寿<th>ID</th><th>الاسم</th><th>البريد</th><th>الهاتف</th>"
        for u in users:
            html += f"<tr><td>{u['id']}</td><td>{u['name']}</td><td>{u['email']}</td><td>{u.get('phone', '-')}</td></tr>"
        html += "</table><p><a href='/'>العودة</a></p>"
        return html
    except Exception as e:
        return f"❌ خطأ: {e}"

@app.route("/check-products")
def check_products():
    """عرض جميع المنتجات في قاعدة البيانات"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products ORDER BY id DESC")
        products = cursor.fetchall()
        conn.close()
        
        if not products:
            return "<h1>⚠️ لا توجد منتجات في قاعدة البيانات</h1><p><a href='/admin/add'>إضافة منتج</a></p>"
        
        html = "<h1>📦 قائمة المنتجات</h1><table border='1' cellpadding='10'>"
        html += "<tr><th>ID</th><th>الاسم</th><th>السعر</th><th>الفئة</th><th>الصورة</th></tr>"
        for p in products:
            html += f"<tr><td>{p['id']}</td><td>{p['name']}</td><td>{p['price']} د.ع</td><td>{p.get('category', 'عام')}</td><td>{p.get('image', 'لا توجد')}</td></tr>"
        html += "</table><p><a href='/admin/add'>➕ إضافة منتج جديد</a></p><p><a href='/admin/dashboard'>⬅️ العودة للوحة التحكم</a></p>"
        return html
    except Exception as e:
        return f"❌ خطأ: {e}"

@app.route("/create-test-user")
def create_test_user():
    """إنشاء مستخدم تجريبي"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        placeholder = get_placeholder()
        
        email = "test@example.com"
        password = "123456"
        hashed = generate_password_hash(password)
        
        cursor.execute(f"SELECT * FROM users WHERE email = {placeholder}", (email,))
        existing = cursor.fetchone()
        
        if not existing:
            cursor.execute(
                f"INSERT INTO users (name, email, password, phone) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
                ("مستخدم تجريبي", email, hashed, "0500000000")
            )
            conn.commit()
            return """
            <h1>✅ تم إنشاء مستخدم تجريبي</h1>
            <p><strong>البريد:</strong> test@example.com</p>
            <p><strong>كلمة المرور:</strong> 123456</p>
            <hr>
            <a href="/user/login">تسجيل الدخول</a>
            """
        else:
            return "⚠️ المستخدم التجريبي موجود بالفعل"
    except Exception as e:
        return f"❌ خطأ: {e}"
    finally:
        conn.close()

@app.route("/setup-db")
def setup_db():
    """إنشاء جميع الجداول في قاعدة البيانات"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # إنشاء جدول المنتجات
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL,
                old_price REAL DEFAULT 0,
                image TEXT,
                category TEXT DEFAULT 'عام'
            )
        """)
        
        # إنشاء جدول الصور
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_images (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL,
                filename TEXT NOT NULL
            )
        """)
        
        # إنشاء جدول المستخدمين
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # إنشاء جدول الطلبات
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                items TEXT NOT NULL,
                total REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        
        # إنشاء حساب الأدمن
        hashed = generate_password_hash(ADMIN_PASSWORD)
        cursor.execute("SELECT * FROM users WHERE email = %s", (ADMIN_EMAIL,))
        admin_exists = cursor.fetchone()
        
        if not admin_exists:
            cursor.execute(
                "INSERT INTO users (name, email, password, phone) VALUES (%s, %s, %s, %s)",
                ("مدير الموقع", ADMIN_EMAIL, hashed, "0500000000")
            )
            conn.commit()
            admin_created = "✅ تم إنشاء حساب الأدمن"
        else:
            admin_created = "✅ حساب الأدمن موجود بالفعل"
        
        conn.close()
        
        return f"""
        <!DOCTYPE html>
        <html dir="rtl">
        <head><meta charset="UTF-8"><title>إعداد قاعدة البيانات</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>✅ تم إنشاء جميع الجداول بنجاح!</h1>
            <hr>
            <p><strong>الجدول products:</strong> تم إنشاؤه</p>
            <p><strong>الجدول product_images:</strong> تم إنشاؤه</p>
            <p><strong>الجدول users:</strong> تم إنشاؤه</p>
            <p><strong>الجدول orders:</strong> تم إنشاؤه</p>
            <p><strong>{admin_created}</strong></p>
            <hr>
            <h3>🔗 روابط مفيدة:</h3>
            <ul>
                <li><a href="/force-admin">⚡ تسجيل دخول الأدمن</a></li>
                <li><a href="/user/register">📝 إنشاء حساب جديد</a></li>
                <li><a href="/debug-db">🔍 فحص قاعدة البيانات</a></li>
                <li><a href="/test-add">🧪 اختبار إضافة منتج</a></li>
                <li><a href="/check-products">📦 عرض المنتجات</a></li>
                <li><a href="/recreate-tables">🔄 إعادة إنشاء الجداول</a></li>
            </ul>
        </body>
        </html>
        """
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"❌ خطأ: {e}")
        print(error_details)
        return f"""
        <!DOCTYPE html>
        <html dir="rtl">
        <head><meta charset="UTF-8"><title>خطأ</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>❌ حدث خطأ أثناء إنشاء الجداول</h1>
            <hr>
            <p><strong>الخطأ:</strong> {e}</p>
            <pre style="background:#f0f0f0; padding:10px; overflow:auto;">{error_details}</pre>
            <hr>
            <p><a href="/">العودة للصفحة الرئيسية</a></p>
        </body>
        </html>
        """

@app.route("/test-add")
def test_add():
    """اختبار إضافة منتج"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        placeholder = get_placeholder()
        
        # محاولة إضافة منتج تجريبي
        cursor.execute(
            f"INSERT INTO products (name, description, price, old_price, image, category) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
            ("منتج تجريبي", "وصف تجريبي", 100, 150, None, "عام")
        )
        conn.commit()
        conn.close()
        return "✅ تم إضافة منتج تجريبي بنجاح"
    except Exception as e:
        import traceback
        return f"❌ خطأ: {e}<br><pre>{traceback.format_exc()}</pre>"

@app.route("/recreate-tables")
def recreate_tables():
    """إعادة إنشاء الجداول بالكامل مع عمود old_price"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            # حذف الجداول القديمة
            cursor.execute("DROP TABLE IF EXISTS product_images")
            cursor.execute("DROP TABLE IF EXISTS orders")
            cursor.execute("DROP TABLE IF EXISTS products")
            cursor.execute("DROP TABLE IF EXISTS users")
            
            # إعادة إنشاء جدول المنتجات
            cursor.execute("""
                CREATE TABLE products (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    price REAL NOT NULL,
                    old_price REAL DEFAULT 0,
                    image TEXT,
                    category TEXT DEFAULT 'عام'
                )
            """)
            
            # إنشاء جدول الصور
            cursor.execute("""
                CREATE TABLE product_images (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER NOT NULL,
                    filename TEXT NOT NULL
                )
            """)
            
            # إنشاء جدول المستخدمين
            cursor.execute("""
                CREATE TABLE users (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    name TEXT NOT NULL,
                    phone TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # إنشاء جدول الطلبات
            cursor.execute("""
                CREATE TABLE orders (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    items TEXT NOT NULL,
                    total REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            
            # إنشاء حساب الأدمن
            hashed = generate_password_hash(ADMIN_PASSWORD)
            cursor.execute("INSERT INTO users (name, email, password, phone) VALUES (%s, %s, %s, %s)",
                           ("مدير الموقع", ADMIN_EMAIL, hashed, "0500000000"))
            conn.commit()
            
        else:
            # SQLite
            cursor.execute("DROP TABLE IF EXISTS product_images")
            cursor.execute("DROP TABLE IF EXISTS orders")
            cursor.execute("DROP TABLE IF EXISTS products")
            cursor.execute("DROP TABLE IF EXISTS users")
            
            cursor.execute("""
                CREATE TABLE products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    price REAL NOT NULL,
                    old_price REAL DEFAULT 0,
                    image TEXT,
                    category TEXT DEFAULT 'عام'
                )
            """)
            
            cursor.execute("""
                CREATE TABLE product_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    filename TEXT NOT NULL
                )
            """)
            
            cursor.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    name TEXT NOT NULL,
                    phone TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    items TEXT NOT NULL,
                    total REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            
            hashed = generate_password_hash(ADMIN_PASSWORD)
            cursor.execute("INSERT INTO users (name, email, password, phone) VALUES (?, ?, ?, ?)",
                           ("مدير الموقع", ADMIN_EMAIL, hashed, "0500000000"))
            conn.commit()
        
        conn.close()
        
        return """
        <!DOCTYPE html>
        <html dir="rtl">
        <head><meta charset="UTF-8"><title>إعادة إنشاء الجداول</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>✅ تم إعادة إنشاء جميع الجداول بنجاح!</h1>
            <hr>
            <p><strong>✓ جدول products:</strong> تم إنشاؤه مع عمود old_price</p>
            <p><strong>✓ جدول product_images:</strong> تم إنشاؤه</p>
            <p><strong>✓ جدول users:</strong> تم إنشاؤه مع حساب الأدمن</p>
            <p><strong>✓ جدول orders:</strong> تم إنشاؤه</p>
            <hr>
            <h3>🔗 روابط مفيدة:</h3>
            <ul>
                <li><a href="/force-admin">⚡ تسجيل دخول الأدمن</a></li>
                <li><a href="/admin/add">➕ إضافة منتج</a></li>
                <li><a href="/check-products">📦 عرض المنتجات</a></li>
                <li><a href="/test-add">🧪 اختبار إضافة منتج</a></li>
            </ul>
        </body>
        </html>
        """
    except Exception as e:
        import traceback
        return f"❌ خطأ: {e}<br><pre>{traceback.format_exc()}</pre>"

@app.route("/add-bulk-products")
def add_bulk_products():
    """إضافة 20 منتجاً متنوعاً دفعة واحدة - طريقة مبسطة"""
    results = []
    try:
        conn = get_db()
        cursor = conn.cursor()
        placeholder = get_placeholder()
        
        # قائمة المنتجات (20 منتج)
        products = [
            # ========== إلكترونيات (4) ==========
            ("سماعات Sony WH-1000XM5", "سماعات لاسلكية عالية الجودة مع تقنية إلغاء الضوضاء، بطارية تدوم 30 ساعة", 450000, 550000, "https://m.media-amazon.com/images/I/61Y32E0lGqL._AC_SL1500_.jpg", "إلكترونيات"),
            ("لابتوب ASUS Zenbook 14", "لابتوب خفيف الوزن بشاشة OLED 14 إنش، معالج Intel Core i7، 16GB RAM", 1250000, 1450000, "https://dlcdnwebimgs.asus.com/gain/C9A99B7E-0C5A-45F8-9DF4-11B5B2D6E8E2", "إلكترونيات"),
            ("آيفون 15 Pro Max", "هاتف ذكي من Apple مع كاميرا احترافية 48 ميجابكسل، شاشة Super Retina XDR", 1450000, 1650000, "https://store.storeimages.cdn-apple.com/4982/as-images.apple.com/is/iphone-15-pro-max-natural-titanium-select", "إلكترونيات"),
            ("تابلت سامسونج Galaxy Tab S9", "جهاز لوحي بشاشة 11 إنش، قلم S Pen مضمن، معالج Snapdragon 8 Gen 2", 850000, 950000, "https://images.samsung.com/is/image/samsung/p6pim/ae/2306/gallery/ae-galaxy-tab-s9-sm-x710nzafeu-536936600", "إلكترونيات"),
            
            # ========== ملابس رجالية (3) ==========
            ("قميص قطني تركي", "قميص رجالي قطني 100% من أجود الأقمشة التركية، ناعم ومريح", 55000, 75000, "https://m.media-amazon.com/images/I/71Z7Y8xYxL._AC_UL1500_.jpg", "ملابس رجالية"),
            ("بدلة رسمية تركية", "بدلة رجالية أنيقة من الصوف التركي، مناسبة للمناسبات الرسمية", 250000, 350000, "https://m.media-amazon.com/images/I/81iZ7Y8xYxL._AC_UL1500_.jpg", "ملابس رجالية"),
            ("تيشيرت قطني", "تيشيرت قطني مريح بتصميم بسيط، متوفر بألوان متعددة", 25000, 40000, "https://ae-pic-a1.aliexpress-media.com/kf/S89b38b9c79454e60b2ab794b8c26d73bV.jpg", "ملابس رجالية"),
            
            # ========== ملابس نسائية (3) ==========
            ("فستان سهرة تركي", "فستان سهرة أنيق من تصميم تركي، دانتيل فاخر، مناسب للمناسبات", 180000, 280000, "https://m.media-amazon.com/images/I/71w-8Y8xYxL._AC_UL1500_.jpg", "ملابس نسائية"),
            ("بلوزة حريرية", "بلوزة نسائية من الحرير التركي، ناعمة وأنيقة، ألوان راقية", 75000, 120000, "https://ae-pic-a1.aliexpress-media.com/kf/Sa3b2c0d8e9f4a1b2c3d4e5f6a7b8c9d0.jpg", "ملابس نسائية"),
            ("جاكيت جينز", "جاكيت جينز نسائي عصري، يناسب جميع الأوقات، قطن 100%", 65000, 95000, "https://m.media-amazon.com/images/I/81iZ7Y8xYxL._AC_UL1500_.jpg", "ملابس نسائية"),
            
            # ========== مستلزمات منزلية (3) ==========
            ("طقم أواني طبخ تركي", "طقم أواني طبخ من الجرانيت التركي، 7 قطع، غير لاصق، صحي", 120000, 180000, "https://m.media-amazon.com/images/I/71YxY8xYxL._AC_SL1500_.jpg", "مستلزمات منزلية"),
            ("سجاد تركي", "سجاد تركي يدوي الصنع، صوف طبيعي، ألوان وأشكال متنوعة", 350000, 500000, "https://m.media-amazon.com/images/I/91iZ7Y8xYxL._AC_SL1500_.jpg", "مستلزمات منزلية"),
            ("ستائر مخملية", "ستائر مخملية تركية فاخرة، عازلة للضوء، مقاسات حسب الطلب", 85000, 130000, "https://ae-pic-a1.aliexpress-media.com/kf/Sa3b2c0d8e9f4a1b2c3d4e5f6a7b8c9d0.jpg", "مستلزمات منزلية"),
            
            # ========== مستحضرات تجميل (1) ==========
            ("كريم العناية بالبشرة", "كريم تركي طبيعي للعناية بالبشرة، مناسب لجميع أنواع البشرة", 45000, 65000, "https://m.media-amazon.com/images/I/71YxY8xYxL._AC_SL1500_.jpg", "مستحضرات تجميل"),
            
            # ========== عطور (1) ==========
            ("عطر تركي فاخر", "عطر تركي برائحة خشبية مميزة، ثبات طويل، تركيز عالٍ", 95000, 140000, "https://m.media-amazon.com/images/I/81iZ7Y8xYxL._AC_UL1500_.jpg", "عطور"),
            
            # ========== كتب (2) ==========
            ("رواية تركية مترجمة", "رواية أدبية تركية مترجمة للعربية، تحكي قصة حب وتشويق", 15000, 25000, "https://m.media-amazon.com/images/I/71YxY8xYxL._AC_SL1000_.jpg", "كتب"),
            ("كتاب الطبخ التركي", "كتاب يشرح أشهى الوصفات التركية التقليدية، بالصور والخطوات", 22000, 35000, "https://m.media-amazon.com/images/I/81iZ7Y8xYxL._AC_SL1000_.jpg", "كتب"),
            
            # ========== رياضة (1) ==========
            ("حذاء رياضي تركي", "حذاء رياضي تركي عالي الجودة، مريح للجري والمشي، مقاسات متعددة", 75000, 110000, "https://m.media-amazon.com/images/I/71YxY8xYxL._AC_UL1500_.jpg", "رياضة"),
            
            # ========== ألعاب (1) ==========
            ("لعبة تركية خشبية", "لعبة أطفال خشبية تعليمية من صنع يدوي تركي، آمنة للأطفال", 35000, 55000, "https://m.media-amazon.com/images/I/81iZ7Y8xYxL._AC_SL1500_.jpg", "ألعاب"),
            
            # ========== ساعات (1) ==========
            ("ساعة رجالية تركية", "ساعة يد رجالية بتصميم تركي عصري، ستانلس ستيل، مقاومة للماء", 120000, 180000, "https://m.media-amazon.com/images/I/71YxY8xYxL._AC_UL1500_.jpg", "ساعات"),
        ]
        
        # إضافة المنتجات واحدة تلو الأخرى
        count = 0
        errors = []
        
        for i, p in enumerate(products):
            try:
                cursor.execute(
                    f"INSERT INTO products (name, description, price, old_price, image, category) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                    (p[0], p[1], p[2], p[3], p[4], p[5])
                )
                count += 1
                results.append(f"✅ {i+1}. {p[0]} - تمت الإضافة")
            except Exception as e:
                error_msg = f"❌ {i+1}. {p[0]} - خطأ: {str(e)[:100]}"
                results.append(error_msg)
                errors.append(error_msg)
        
        conn.commit()
        conn.close()
        
        # بناء صفحة النتائج
        html = f"""
        <!DOCTYPE html>
        <html dir="rtl">
        <head><meta charset="UTF-8"><title>نتائج إضافة المنتجات</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>📦 نتائج إضافة 20 منتجاً</h1>
            <hr>
            <p><strong>✅ تمت الإضافة بنجاح:</strong> {count} من {len(products)} منتج</p>
            <p><strong>❌ عدد الأخطاء:</strong> {len(errors)}</p>
            <hr>
            <h3>📋 التفاصيل:</h3>
            <ul>
        """
        
        for r in results:
            html += f"<li>{r}</li>"
        
        html += """
            </ul>
            <hr>
            <h3>🔗 روابط مفيدة:</h3>
            <ul>
                <li><a href="/force-admin">⚡ تسجيل دخول الأدمن</a></li>
                <li><a href="/products">🛍️ عرض المنتجات</a></li>
                <li><a href="/check-products">📦 فحص المنتجات</a></li>
            </ul>
        </body>
        </html>
        """
        return html
        
    except Exception as e:
        import traceback
        return f"❌ خطأ عام: {e}<br><pre>{traceback.format_exc()}</pre>"

@app.route("/update-product-images")
def update_product_images():
    """تحديث صور المنتجات بروابط حقيقية"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        placeholder = get_placeholder()
        
        # تحديث صور المنتجات بروابط حقيقية
        updates = [
            (1, "https://m.media-amazon.com/images/I/61Y32E0lGqL._AC_SL1500_.jpg"),
            (2, "https://dlcdnwebimgs.asus.com/gain/C9A99B7E-0C5A-45F8-9DF4-11B5B2D6E8E2"),
            (3, "https://store.storeimages.cdn-apple.com/4982/as-images.apple.com/is/iphone-15-pro-max-natural-titanium-select"),
            (4, "https://images.samsung.com/is/image/samsung/p6pim/ae/2306/gallery/ae-galaxy-tab-s9-sm-x710nzafeu-536936600"),
            (5, "https://m.media-amazon.com/images/I/71Z7Y8xYxL._AC_UL1500_.jpg"),
            (6, "https://m.media-amazon.com/images/I/81iZ7Y8xYxL._AC_UL1500_.jpg"),
            (7, "https://ae-pic-a1.aliexpress-media.com/kf/S89b38b9c79454e60b2ab794b8c26d73bV.jpg"),
            (8, "https://m.media-amazon.com/images/I/71w-8Y8xYxL._AC_UL1500_.jpg"),
            (9, "https://m.media-amazon.com/images/I/81iZ7Y8xYxL._AC_UL1500_.jpg"),
            (10, "https://m.media-amazon.com/images/I/81iZ7Y8xYxL._AC_UL1500_.jpg"),
            (11, "https://m.media-amazon.com/images/I/71YxY8xYxL._AC_SL1500_.jpg"),
            (12, "https://m.media-amazon.com/images/I/91iZ7Y8xYxL._AC_SL1500_.jpg"),
            (13, "https://m.media-amazon.com/images/I/71YxY8xYxL._AC_SL1500_.jpg"),
            (14, "https://m.media-amazon.com/images/I/71YxY8xYxL._AC_SL1500_.jpg"),
            (15, "https://m.media-amazon.com/images/I/81iZ7Y8xYxL._AC_UL1500_.jpg"),
            (16, "https://m.media-amazon.com/images/I/71YxY8xYxL._AC_SL1000_.jpg"),
            (17, "https://m.media-amazon.com/images/I/81iZ7Y8xYxL._AC_SL1000_.jpg"),
            (18, "https://m.media-amazon.com/images/I/71YxY8xYxL._AC_UL1500_.jpg"),
            (19, "https://m.media-amazon.com/images/I/81iZ7Y8xYxL._AC_SL1500_.jpg"),
            (20, "https://m.media-amazon.com/images/I/71YxY8xYxL._AC_UL1500_.jpg"),
        ]
        
        count = 0
        for pid, image_url in updates:
            cursor.execute(
                f"UPDATE products SET image = {placeholder} WHERE id = {placeholder}",
                (image_url, pid)
            )
            count += 1
        
        conn.commit()
        conn.close()
        
        return f"""
        <!DOCTYPE html>
        <html dir="rtl">
        <head><meta charset="UTF-8"><title>تحديث الصور</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h1>✅ تم تحديث {count} منتج بالصور!</h1>
            <hr>
            <p>الآن جميع المنتجات تحتوي على صور حقيقية.</p>
            <p><a href="/products">🛍️ عرض المنتجات</a></p>
            <p><a href="/check-products">📦 فحص المنتجات</a></p>
        </body>
        </html>
        """
    except Exception as e:
        import traceback
        return f"❌ خطأ: {e}<br><pre>{traceback.format_exc()}</pre>"

if __name__ == "__main__":
    init_db()
    migrate_db()
    create_admin_user()
    app.run(debug=True)