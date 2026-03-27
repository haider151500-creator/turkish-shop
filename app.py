from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import sqlite3, os
import psycopg2
from psycopg2.extras import RealDictCursor
from functools import wraps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = "change-this-in-production"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

def get_db():
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # استخدام PostgreSQL في الإنتاج
        conn = psycopg2.connect(database_url)
        conn.cursor_factory = RealDictCursor
        return conn
    else:
        # استخدام SQLite في التطوير المحلي - تعديل لجعل النتائج قواميس
        conn = sqlite3.connect(DB_PATH)
        # إرجاع قاموس بدلاً من Row لسهولة التحويل إلى JSON
        conn.row_factory = lambda cursor, row: {col[0]: row[i] for i, col in enumerate(cursor.description)}
        return conn

def init_db():
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
    
    conn.commit()
    conn.close()

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

@app.route("/product/<int:pid>")
def product_detail(pid):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id=%s", (pid,))
    item = cursor.fetchone()
    cursor.execute("SELECT id, filename FROM product_images WHERE product_id=%s ORDER BY id", (pid,))
    imgs = cursor.fetchall()
    conn.close()
    if not item:
        flash("المنتج غير موجود.", "danger")
        return redirect(url_for("products"))
    main_image = item["image"] if item["image"] else (imgs[0]["filename"] if imgs else None)
    return render_template("product_detail.html", p=item, images=imgs, main_image=main_image)

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == "1234":
            session["is_admin"] = True
            flash("تم تسجيل الدخول كأدمن.", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("كلمة المرور غير صحيحة.", "danger")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("تم تسجيل الخروج.", "info")
    return redirect(url_for("products"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY id DESC")
    items = cursor.fetchall()
    conn.close()
    return render_template("admin_dashboard.html", products=items)

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
        files = [f for f in files if getattr(f, "filename", "")][:5]
        if files:
            image_filename = files[0].filename
            for f in files:
                f.save(os.path.join(app.config["UPLOAD_FOLDER"], f.filename))

        if not name or not price or not category:
            flash("الاسم والسعر والفئة مطلوبة.", "danger")
            return redirect(url_for("admin_add"))

        try:
            price_val = float(price)
            old_price_val = float(old_price) if old_price else 0
        except ValueError:
            flash("السعر غير صالح.", "danger")
            return redirect(url_for("admin_add"))

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO products (name, description, price, old_price, image, category) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (name, description, price_val, old_price_val, image_filename, category)
        )
        result = cursor.fetchone()
        pid = result['id']
        if files:
            for f in files[:5]:
                cursor.execute("INSERT INTO product_images (product_id, filename) VALUES (%s, %s)", (pid, f.filename))
        conn.commit()
        conn.close()
        flash("تمت إضافة المنتج بنجاح.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("add_product.html", categories=categories)

@app.route("/admin/edit/<int:pid>", methods=["GET", "POST"])
@admin_required
def admin_edit(pid):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id=%s", (pid,))
    product = cursor.fetchone()
    if not product:
        conn.close()
        flash("المنتج غير موجود.", "danger")
        return redirect(url_for("admin_dashboard"))

    cursor.execute("SELECT id, filename FROM product_images WHERE product_id=%s ORDER BY id", (pid,))
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

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE products SET name=%s, description=%s, price=%s, old_price=%s, image=%s, category=%s WHERE id=%s",
            (name, description, price_val, old_price_val, image_filename, category, pid)
        )
        cursor.execute("SELECT COUNT(*) FROM product_images WHERE product_id=%s", (pid,))
        cnt_result = cursor.fetchone()
        cnt = cnt_result['count'] if isinstance(cnt_result, dict) else cnt_result[0]
        slots = max(0, 5 - (cnt or 0))
        if files and slots:
            new_images = files[:slots] if len(files) > 1 else files
            for f in new_images:
                cursor.execute("INSERT INTO product_images (product_id, filename) VALUES (%s, %s)", (pid, f.filename))
        conn.commit()
        conn.close()
        flash("تم تعديل المنتج بنجاح.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("edit_product.html", p=product, images=images, categories=categories)

@app.route("/admin/delete/<int:pid>", methods=["POST"])
@admin_required
def admin_delete(pid):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT image FROM products WHERE id=%s", (pid,))
    row = cursor.fetchone()
    cursor.execute("DELETE FROM products WHERE id=%s", (pid,))
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
    cursor.execute("SELECT filename, product_id FROM product_images WHERE id=%s", (image_id,))
    row = cursor.fetchone()
    if row:
        cursor.execute("DELETE FROM product_images WHERE id=%s", (image_id,))
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

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/work")
def work():
    return render_template("work.html")

@app.route("/pricing")
def pricing():
    return render_template("pricing.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/products")
def products():
    cat = request.args.get("cat")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT COALESCE(category,'عام') AS c FROM products ORDER BY c")
    cats = cursor.fetchall()
    
    if cat:
        cursor.execute("SELECT * FROM products WHERE COALESCE(category,'عام')=%s ORDER BY id DESC", (cat,))
    else:
        cursor.execute("SELECT * FROM products ORDER BY id DESC")
    items = cursor.fetchall()
    conn.close()
    
    # تحويل المنتجات إلى قائمة قواميس (النتائج أصبحت قواميس بالفعل بسبب تعديل row_factory)
    products_list = list(items) if items else []
    
    # التأكد من وجود old_price لكل منتج
    for product in products_list:
        if 'old_price' not in product:
            product['old_price'] = None
    
    categories_list = [r["c"] for r in cats]
    
    return render_template("products.html", products=products_list, categories=categories_list, active_cat=cat)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)