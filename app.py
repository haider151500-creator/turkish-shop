from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import sqlite3, os
from functools import wraps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = "change-this-in-production"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute(
        '''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            image TEXT,
            category TEXT DEFAULT 'عام'
        );
        '''
    )
    # جدول صور متعددة لكل منتج
    c.execute(
        '''
        CREATE TABLE IF NOT EXISTS product_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
        );
        '''
    )
    # محاولة إضافة العمود عند وجود قواعد بيانات قديمة
    try:
        c.execute("ALTER TABLE products ADD COLUMN category TEXT DEFAULT 'عام'")
    except Exception:
        pass
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

# ========== تم حذف الصفحة الرئيسية (index) ==========
# الصفحة الرئيسية الآن تعيد توجيه إلى صفحة المنتجات
@app.route("/")
def index():
    return redirect(url_for("products"))

@app.route("/product/<int:pid>")
def product_detail(pid):
    conn = get_db()
    item = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    imgs = conn.execute("SELECT id, filename FROM product_images WHERE product_id=? ORDER BY id", (pid,)).fetchall()
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
    items = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("admin_dashboard.html", products=items)

@app.route("/admin/add", methods=["GET", "POST"])
@admin_required
def admin_add():
    conn = get_db()
    # جلب جميع الفئات الموجودة من قاعدة البيانات
    cats = conn.execute("SELECT DISTINCT COALESCE(category,'عام') AS c FROM products ORDER BY c").fetchall()
    categories = [r["c"] for r in cats]
    conn.close()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        category = request.form.get("category", "").strip()  # الفئة المختارة من الواجهة
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
        except ValueError:
            flash("السعر غير صالح.", "danger")
            return redirect(url_for("admin_add"))

        conn = get_db()
        conn.execute(
            "INSERT INTO products (name, description, price, image, category) VALUES (?, ?, ?, ?, ?)",
            (name, description, price_val, image_filename, category)
        )
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        if files:
            for f in files[:5]:
                conn.execute("INSERT INTO product_images (product_id, filename) VALUES (?, ?)", (pid, f.filename))
        conn.commit()
        conn.close()
        flash("تمت إضافة المنتج بنجاح.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("add_product.html", categories=categories)

@app.route("/admin/edit/<int:pid>", methods=["GET", "POST"])
@admin_required
def admin_edit(pid):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not product:
        conn.close()
        flash("المنتج غير موجود.", "danger")
        return redirect(url_for("admin_dashboard"))

    # جلب الصور الإضافية للمنتج
    images = conn.execute("SELECT id, filename FROM product_images WHERE product_id=? ORDER BY id", (pid,)).fetchall()
    # جلب جميع الفئات الموجودة
    cats = conn.execute("SELECT DISTINCT COALESCE(category,'عام') AS c FROM products ORDER BY c").fetchall()
    categories = [r["c"] for r in cats]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        category = request.form.get("category", "").strip()
        remove_image = request.form.get("remove_image", "0") == "1"

        if not name or not price or not category:
            conn.close()
            flash("الاسم والسعر والفئة مطلوبة.", "danger")
            return redirect(url_for("admin_edit", pid=pid))

        # معالجة الصورة الرئيسية
        image_filename = product["image"]
        if remove_image and image_filename:
            # حذف الصورة الرئيسية من الملفات
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
            # إذا تم رفع صور جديدة، استخدم أول صورة كصورة رئيسية
            image_filename = files[0].filename
            for f in files:
                f.save(os.path.join(app.config["UPLOAD_FOLDER"], f.filename))

        try:
            price_val = float(price)
        except ValueError:
            conn.close()
            flash("السعر غير صالح.", "danger")
            return redirect(url_for("admin_edit", pid=pid))

        # تحديث المنتج
        conn.execute(
            "UPDATE products SET name=?, description=?, price=?, image=?, category=? WHERE id=?",
            (name, description, price_val, image_filename, category, pid)
        )

        # إضافة الصور الجديدة (حتى 5 إجمالاً)
        cnt = conn.execute("SELECT COUNT(*) FROM product_images WHERE product_id=?", (pid,)).fetchone()[0]
        slots = max(0, 5 - (cnt or 0))
        if files and slots:
            # نضيف الصور الجديدة (باستثناء أول صورة تم استخدامها كصورة رئيسية)
            new_images = files[:slots] if len(files) > 1 else files
            for f in new_images:
                conn.execute("INSERT INTO product_images (product_id, filename) VALUES (?, ?)", (pid, f.filename))

        conn.commit()
        conn.close()
        flash("تم تعديل المنتج بنجاح.", "success")
        return redirect(url_for("admin_dashboard"))

    conn.close()
    return render_template("edit_product.html", p=product, images=images, categories=categories)

@app.route("/admin/delete/<int:pid>", methods=["POST"])
@admin_required
def admin_delete(pid):
    conn = get_db()
    row = conn.execute("SELECT image FROM products WHERE id=?", (pid,)).fetchone()
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
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
    row = conn.execute("SELECT filename, product_id FROM product_images WHERE id=?", (image_id,)).fetchone()
    if row:
        conn.execute("DELETE FROM product_images WHERE id=?", (image_id,))
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
    cats = conn.execute("SELECT DISTINCT COALESCE(category,'عام') AS c FROM products ORDER BY c").fetchall()
    if cat:
        items = conn.execute("SELECT * FROM products WHERE COALESCE(category,'عام')=? ORDER BY id DESC", (cat,)).fetchall()
    else:
        items = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("products.html", products=items, categories=[r["c"] for r in cats], active_cat=cat)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)