import os
import sqlite3
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    flash
)

from dotenv import load_dotenv
from database import get_db, init_database


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "lbspeed-secret-change-moi"
)

ADMIN_USERNAME = os.getenv(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.getenv(
    "ADMIN_PASSWORD",
    "change-moi"
)

MINIMUM_COMMANDE = 10.00


# ============================================================
# INITIALISATION
# ============================================================

init_database()


# ============================================================
# ADMIN
# ============================================================

def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("admin"):
            return redirect(
                url_for("admin_login")
            )

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# PRIX FINAL D'UN PRODUIT
# ============================================================

def product_final_price(product):

    try:
        price = float(product["price"] or 0)
    except (ValueError, TypeError, KeyError):
        price = 0.00

    try:
        active = int(product["promotion_active"] or 0)
    except (ValueError, TypeError, KeyError):
        active = 0

    try:
        discount = float(
            product["promotion_discount"] or 0
        )
    except (ValueError, TypeError, KeyError):
        discount = 0.00

    discount = min(
        max(discount, 0),
        100
    )

    if active and discount > 0:
        price = price * (
            1 - discount / 100
        )

    return round(
        max(price, 0),
        2
    )


# ============================================================
# CODE PROMO
# ============================================================

def get_active_promo(code):

    if not code:
        return None

    db = get_db()

    promo = db.execute(
        """
        SELECT *
        FROM promos
        WHERE UPPER(code) = ?
        AND active = 1
        LIMIT 1
        """,
        (
            str(code).strip().upper(),
        )
    ).fetchone()

    db.close()

    return promo


# ============================================================
# CALCUL DU PANIER
# ============================================================

def calculate_cart():

    raw_cart = session.get(
        "cart",
        {}
    )

    if not isinstance(raw_cart, dict):
        raw_cart = {}

    cleaned_cart = {}

    items = []

    subtotal = 0.00

    db = get_db()

    # --------------------------------------------------------
    # PRODUITS
    # --------------------------------------------------------

    for product_id, raw_quantity in raw_cart.items():

        try:
            product_id_int = int(product_id)
        except (ValueError, TypeError):
            continue

        try:
            quantity = int(raw_quantity)
        except (ValueError, TypeError):
            continue

        if quantity <= 0:
            continue

        product = db.execute(
            """
            SELECT
                p.*,
                c.name AS category_name,
                c.slug AS category_slug
            FROM products p
            LEFT JOIN categories c
                ON c.id = p.category_id
            WHERE p.id = ?
            """,
            (
                product_id_int,
            )
        ).fetchone()

        # Produit supprimé de la base
        if product is None:
            continue

        try:
            stock = int(
                product["stock"] or 0
            )
        except (ValueError, TypeError):
            stock = 0

        # Produit en rupture
        if stock <= 0:
            continue

        # On ne dépasse jamais le stock
        quantity = min(
            quantity,
            stock
        )

        # Sécurité
        if quantity <= 0:
            continue

        # Prix original
        try:
            original_price = float(
                product["price"] or 0
            )
        except (ValueError, TypeError):
            original_price = 0.00

        original_price = round(
            max(original_price, 0),
            2
        )

        # Prix avec promotion produit
        unit_price = product_final_price(
            product
        )

        line_total = round(
            unit_price * quantity,
            2
        )

        subtotal += line_total

        # Session propre
        cleaned_cart[str(product_id_int)] = quantity

        # ----------------------------------------------------
        # Objet panier
        # ----------------------------------------------------

        items.append({
            "product": product,
            "product_id": product_id_int,
            "quantity": quantity,
            "stock": stock,
            "name": product["name"],
            "description": product["description"],
            "image": product["image"],
            "category_name": product["category_name"],
            "category_slug": product["category_slug"],
            "original_price": original_price,
            "price": unit_price,
            "unit_price": unit_price,
            "subtotal": line_total
        })

    db.close()

    # --------------------------------------------------------
    # NETTOYAGE AUTOMATIQUE DE LA SESSION
    # --------------------------------------------------------

    if cleaned_cart != raw_cart:
        session["cart"] = cleaned_cart
        session.modified = True

    else:
        session["cart"] = cleaned_cart

    # --------------------------------------------------------
    # SOUS-TOTAL
    # --------------------------------------------------------

    subtotal = round(
        subtotal,
        2
    )

    # --------------------------------------------------------
    # CODE PROMO GLOBAL
    # --------------------------------------------------------

    promo = None
    promo_discount = 0.00

    promo_code = session.get(
        "promo_code"
    )

    if promo_code:

        promo = get_active_promo(
            promo_code
        )

        if promo:

            try:
                discount_percent = float(
                    promo["discount"] or 0
                )
            except (ValueError, TypeError):
                discount_percent = 0.00

            discount_percent = min(
                max(discount_percent, 0),
                100
            )

            promo_discount = round(
                subtotal * discount_percent / 100,
                2
            )

        else:

            session.pop(
                "promo_code",
                None
            )

    # --------------------------------------------------------
    # TOTAL
    # --------------------------------------------------------

    total = round(
        max(
            0,
            subtotal - promo_discount
        ),
        2
    )

    # --------------------------------------------------------
    # MINIMUM DE COMMANDE
    # --------------------------------------------------------

    reste_minimum = round(
        max(
            0,
            MINIMUM_COMMANDE - total
        ),
        2
    )

    commande_autorisee = (
        len(items) > 0
        and total >= MINIMUM_COMMANDE
    )

    # --------------------------------------------------------
    # NOMBRE D'ARTICLES
    # --------------------------------------------------------

    cart_count = sum(
        item["quantity"]
        for item in items
    )

    return {
        "items": items,
        "cart": items,
        "cart_count": cart_count,
        "subtotal": subtotal,
        "promo": promo,
        "promo_discount": promo_discount,
        "total": total,
        "reste_minimum": reste_minimum,
        "commande_autorisee": commande_autorisee
    }


# ============================================================
# VARIABLES GLOBALES JINJA
# ============================================================

@app.context_processor
def global_variables():

    data = calculate_cart()

    return {
        "cart_count": data["cart_count"],
        "minimum_commande": MINIMUM_COMMANDE,
        "product_final_price": product_final_price
    }


# ============================================================
# ACCUEIL
# ============================================================

@app.route("/")
def index():

    db = get_db()

    products = db.execute(
        """
        SELECT
            p.*,
            c.name AS category_name,
            c.slug AS category_slug
        FROM products p
        LEFT JOIN categories c
            ON c.id = p.category_id
        ORDER BY p.id DESC
        LIMIT 12
        """
    ).fetchall()

    categories = db.execute(
        """
        SELECT *
        FROM categories
        ORDER BY name ASC
        """
    ).fetchall()

    db.close()

    return render_template(
        "index.html",
        products=products,
        categories=categories
    )


# ============================================================
# BOUTIQUE
# ============================================================

@app.route("/boutique")
def boutique():

    category = request.args.get(
        "category",
        ""
    ).strip()

    search = request.args.get(
        "search",
        ""
    ).strip()

    nouveautes = request.args.get(
        "nouveautes",
        ""
    ).strip()

    db = get_db()

    query = """
        SELECT
            p.*,
            c.name AS category_name,
            c.slug AS category_slug
        FROM products p
        LEFT JOIN categories c
            ON c.id = p.category_id
        WHERE 1 = 1
    """

    params = []

    if category:

        query += """
            AND c.slug = ?
        """

        params.append(category)

    if search:

        query += """
            AND (
                p.name LIKE ?
                OR p.description LIKE ?
            )
        """

        value = f"%{search}%"

        params.extend([
            value,
            value
        ])

    if nouveautes:

        query += """
            ORDER BY p.created_at DESC
        """

    else:

        query += """
            ORDER BY p.id DESC
        """

    products = db.execute(
        query,
        params
    ).fetchall()

    categories = db.execute(
        """
        SELECT *
        FROM categories
        ORDER BY name ASC
        """
    ).fetchall()

    db.close()

    return render_template(
        "boutique.html",
        products=products,
        categories=categories,
        selected_category=category,
        search=search,
        nouveautes=nouveautes
    )


# ============================================================
# PRODUIT
# ============================================================

@app.route("/produit/<int:product_id>")
def product(product_id):

    db = get_db()

    product = db.execute(
        """
        SELECT
            p.*,
            c.name AS category_name,
            c.slug AS category_slug
        FROM products p
        LEFT JOIN categories c
            ON c.id = p.category_id
        WHERE p.id = ?
        """,
        (
            product_id,
        )
    ).fetchone()

    if product is None:

        db.close()

        flash(
            "Produit introuvable.",
            "error"
        )

        return redirect(
            url_for("boutique")
        )

    related_products = []

    if product["category_id"] is not None:

        related_products = db.execute(
            """
            SELECT
                p.*,
                c.name AS category_name,
                c.slug AS category_slug
            FROM products p
            LEFT JOIN categories c
                ON c.id = p.category_id
            WHERE p.category_id = ?
            AND p.id != ?
            ORDER BY p.id DESC
            LIMIT 4
            """,
            (
                product["category_id"],
                product_id
            )
        ).fetchall()

    db.close()

    return render_template(
        "produit.html",
        product=product,
        related_products=related_products
    )


# ============================================================
# PANIER
# ============================================================

@app.route("/panier")
def cart():

    data = calculate_cart()

    return render_template(
        "panier.html",

        # IMPORTANT :
        # panier.html utilise "cart"
        cart=data["cart"],

        items=data["items"],

        cart_count=data["cart_count"],

        subtotal=data["subtotal"],

        promo=data["promo"],

        promo_discount=data["promo_discount"],

        total=data["total"],

        reste_minimum=data["reste_minimum"],

        commande_autorisee=data["commande_autorisee"]
    )


# ============================================================
# AJOUTER AU PANIER
# ============================================================

@app.post("/api/cart/add")
def cart_add():

    data = request.get_json(
        silent=True
    ) or {}

    try:

        product_id = int(
            data.get("product_id")
        )

        quantity = int(
            data.get(
                "quantity",
                1
            )
        )

    except (ValueError, TypeError):

        return jsonify({
            "success": False,
            "message": "Produit ou quantité invalide."
        }), 400

    quantity = max(
        quantity,
        1
    )

    db = get_db()

    product = db.execute(
        """
        SELECT *
        FROM products
        WHERE id = ?
        """,
        (
            product_id,
        )
    ).fetchone()

    db.close()

    if product is None:

        return jsonify({
            "success": False,
            "message": "Produit introuvable."
        }), 404

    try:

        stock = int(
            product["stock"] or 0
        )

    except (ValueError, TypeError):

        stock = 0

    if stock <= 0:

        return jsonify({
            "success": False,
            "message": "Produit en rupture de stock."
        }), 400

    # --------------------------------------------------------
    # PANIER ACTUEL
    # --------------------------------------------------------

    cart = session.get(
        "cart",
        {}
    )

    if not isinstance(cart, dict):
        cart = {}

    key = str(
        product_id
    )

    try:

        current = int(
            cart.get(
                key,
                0
            )
        )

    except (ValueError, TypeError):

        current = 0

    new_quantity = min(
        current + quantity,
        stock
    )

    cart[key] = new_quantity

    session["cart"] = cart
    session.modified = True

    # --------------------------------------------------------
    # RECALCUL PROPRE
    # --------------------------------------------------------

    cart_data = calculate_cart()

    return jsonify({
        "success": True,
        "message": "Produit ajouté au panier.",
        "cart_count": cart_data["cart_count"],
        "quantity": new_quantity
    })


# ============================================================
# MODIFIER LE PANIER
# ============================================================

@app.post("/api/cart/update")
def cart_update():

    data = request.get_json(
        silent=True
    ) or {}

    try:

        product_id = int(
            data.get("product_id")
        )

        quantity = int(
            data.get("quantity")
        )

    except (ValueError, TypeError):

        return jsonify({
            "success": False,
            "message": "Données invalides."
        }), 400

    cart = session.get(
        "cart",
        {}
    )

    if not isinstance(cart, dict):
        cart = {}

    key = str(
        product_id
    )

    # --------------------------------------------------------
    # SUPPRESSION
    # --------------------------------------------------------

    if quantity <= 0:

        cart.pop(
            key,
            None
        )

    else:

        db = get_db()

        product = db.execute(
            """
            SELECT stock
            FROM products
            WHERE id = ?
            """,
            (
                product_id,
            )
        ).fetchone()

        db.close()

        if product is None:

            cart.pop(
                key,
                None
            )

        else:

            try:

                stock = int(
                    product["stock"] or 0
                )

            except (ValueError, TypeError):

                stock = 0

            if stock <= 0:

                cart.pop(
                    key,
                    None
                )

            else:

                cart[key] = min(
                    max(quantity, 1),
                    stock
                )

    session["cart"] = cart
    session.modified = True

    # --------------------------------------------------------
    # RECALCUL
    # --------------------------------------------------------

    cart_data = calculate_cart()

    return jsonify({
        "success": True,
        "cart_count": cart_data["cart_count"],
        "total": cart_data["total"]
    })


# ============================================================
# VIDER LE PANIER
# ============================================================

@app.post("/api/cart/clear")
def cart_clear():

    session["cart"] = {}

    session.pop(
        "promo_code",
        None
    )

    session.modified = True

    return jsonify({
        "success": True,
        "cart_count": 0
    })


# ============================================================
# APPLIQUER CODE PROMO
# ============================================================

@app.post("/promo/appliquer")
def apply_promo():

    code = request.form.get(
        "code",
        ""
    ).strip().upper()

    next_page = request.form.get(
        "next",
        "cart"
    ).strip()

    if not code:

        flash(
            "Entre un code promo.",
            "error"
        )

        if next_page == "checkout":
            return redirect(
                url_for("checkout")
            )

        return redirect(
            url_for("cart")
        )

    promo = get_active_promo(
        code
    )

    if promo is None:

        flash(
            "Code promo invalide ou désactivé.",
            "error"
        )

        if next_page == "checkout":
            return redirect(
                url_for("checkout")
            )

        return redirect(
            url_for("cart")
        )

    session["promo_code"] = code
    session.modified = True

    flash(
        f"Code {code} appliqué : "
        f"-{float(promo['discount']):g} %",
        "success"
    )

    if next_page == "checkout":

        return redirect(
            url_for("checkout")
        )

    return redirect(
        url_for("cart")
    )


# ============================================================
# RETIRER CODE PROMO
# ============================================================

@app.post("/promo/supprimer")
def remove_promo():

    session.pop(
        "promo_code",
        None
    )

    session.modified = True

    flash(
        "Code promo retiré.",
        "success"
    )

    return redirect(
        url_for("checkout")
    )


# ============================================================
# CHECKOUT
# ============================================================

@app.route("/checkout")
def checkout():

    data = calculate_cart()

    if not data["items"]:

        flash(
            "Ton panier est vide.",
            "error"
        )

        return redirect(
            url_for("cart")
        )

    if not data["commande_autorisee"]:

        flash(
            f"Minimum de commande : "
            f"{MINIMUM_COMMANDE:.2f} €. "
            f"Il te manque "
            f"{data['reste_minimum']:.2f} €.",
            "error"
        )

        return redirect(
            url_for("cart")
        )

    return render_template(
        "checkout.html",

        items=data["items"],

        cart=data["items"],

        subtotal=data["subtotal"],

        promo=data["promo"],

        promo_discount=data["promo_discount"],

        total=data["total"],

        minimum_commande=MINIMUM_COMMANDE
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if session.get("admin"):

        return redirect(
            url_for("admin_dashboard")
        )

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):

            session.clear()

            session["admin"] = True

            flash(
                "Connexion réussie.",
                "success"
            )

            return redirect(
                url_for("admin_dashboard")
            )

        flash(
            "Identifiants incorrects.",
            "error"
        )

    return render_template(
        "admin/login.html"
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    db = get_db()

    products_count = db.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]

    categories_count = db.execute(
        "SELECT COUNT(*) FROM categories"
    ).fetchone()[0]

    promos_count = db.execute(
        "SELECT COUNT(*) FROM promos"
    ).fetchone()[0]

    orders_count = db.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

    total_stock = db.execute(
        """
        SELECT COALESCE(SUM(stock), 0)
        FROM products
        """
    ).fetchone()[0]

    total_sales = db.execute(
        """
        SELECT COALESCE(SUM(total), 0)
        FROM orders
        """
    ).fetchone()[0]

    out_of_stock = db.execute(
        """
        SELECT COUNT(*)
        FROM products
        WHERE stock <= 0
        """
    ).fetchone()[0]

    recent_orders = db.execute(
        """
        SELECT *
        FROM orders
        ORDER BY id DESC
        LIMIT 5
        """
    ).fetchall()

    recent_products = db.execute(
        """
        SELECT
            p.*,
            c.name AS category_name
        FROM products p
        LEFT JOIN categories c
            ON c.id = p.category_id
        ORDER BY p.id DESC
        LIMIT 5
        """
    ).fetchall()

    db.close()

    stats = {
        "products": products_count,
        "categories": categories_count,
        "promos": promos_count,
        "orders": orders_count,
        "stock": total_stock,
        "sales": round(
            float(total_sales or 0),
            2
        ),
        "out_of_stock": out_of_stock
    }

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        products_count=products_count,
        categories_count=categories_count,
        promos_count=promos_count,
        orders_count=orders_count,
        total_sales=round(
            float(total_sales or 0),
            2
        ),
        recent_orders=recent_orders,
        recent_products=recent_products
    )


# ============================================================
# ADMIN PRODUITS
# ============================================================

@app.route(
    "/admin/produits",
    methods=["GET", "POST"]
)
@admin_required
def admin_products():

    db = get_db()

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        image = request.form.get(
            "image",
            ""
        ).strip()

        category_id = (
            request.form.get("category_id")
            or None
        )

        try:

            price = float(
                request.form.get(
                    "price",
                    0
                )
            )

            stock = int(
                request.form.get(
                    "stock",
                    0
                )
            )

            promotion_discount = float(
                request.form.get(
                    "promotion_discount",
                    0
                )
            )

        except (ValueError, TypeError):

            db.close()

            flash(
                "Prix, stock ou réduction invalide.",
                "error"
            )

            return redirect(
                url_for("admin_products")
            )

        promotion_active = (
            1
            if request.form.get(
                "promotion_active"
            ) == "1"
            else 0
        )

        if not name:

            db.close()

            flash(
                "Le nom du produit est obligatoire.",
                "error"
            )

            return redirect(
                url_for("admin_products")
            )

        if price < 0:

            db.close()

            flash(
                "Le prix ne peut pas être négatif.",
                "error"
            )

            return redirect(
                url_for("admin_products")
            )

        if stock < 0:

            db.close()

            flash(
                "Le stock ne peut pas être négatif.",
                "error"
            )

            return redirect(
                url_for("admin_products")
            )

        if not 0 <= promotion_discount <= 100:

            db.close()

            flash(
                "La réduction doit être comprise entre 0 et 100 %.",
                "error"
            )

            return redirect(
                url_for("admin_products")
            )

        db.execute(
            """
            INSERT INTO products
            (
                name,
                description,
                price,
                stock,
                image,
                category_id,
                promotion_active,
                promotion_discount
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                description,
                price,
                stock,
                image,
                category_id,
                promotion_active,
                promotion_discount
            )
        )

        db.commit()
        db.close()

        flash(
            "Produit ajouté avec succès.",
            "success"
        )

        return redirect(
            url_for("admin_products")
        )

    products = db.execute(
        """
        SELECT
            p.*,
            c.name AS category_name,
            c.slug AS category_slug
        FROM products p
        LEFT JOIN categories c
            ON c.id = p.category_id
        ORDER BY p.id DESC
        """
    ).fetchall()

    categories = db.execute(
        """
        SELECT *
        FROM categories
        ORDER BY name ASC
        """
    ).fetchall()

    db.close()

    return render_template(
        "admin/produits.html",
        products=products,
        categories=categories
    )


# ============================================================
# ADMIN MODIFIER PRODUIT
# ============================================================

@app.route(
    "/admin/produits/<int:product_id>/modifier",
    methods=["GET", "POST"]
)
@admin_required
def admin_product_edit(product_id):

    db = get_db()

    product = db.execute(
        """
        SELECT *
        FROM products
        WHERE id = ?
        """,
        (
            product_id,
        )
    ).fetchone()

    if product is None:

        db.close()

        flash(
            "Produit introuvable.",
            "error"
        )

        return redirect(
            url_for("admin_products")
        )

    categories = db.execute(
        """
        SELECT *
        FROM categories
        ORDER BY name ASC
        """
    ).fetchall()

    if request.method == "GET":

        db.close()

        return render_template(
            "admin/produit_edit.html",
            product=product,
            categories=categories
        )

    name = request.form.get(
        "name",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    image = request.form.get(
        "image",
        ""
    ).strip()

    category_id = (
        request.form.get("category_id")
        or None
    )

    try:

        price = float(
            request.form.get(
                "price",
                0
            )
        )

        stock = int(
            request.form.get(
                "stock",
                0
            )
        )

        promotion_discount = float(
            request.form.get(
                "promotion_discount",
                0
            )
        )

    except (ValueError, TypeError):

        db.close()

        flash(
            "Prix, stock ou réduction invalide.",
            "error"
        )

        return redirect(
            url_for(
                "admin_product_edit",
                product_id=product_id
            )
        )

    promotion_active = (
        1
        if request.form.get(
            "promotion_active"
        ) == "1"
        else 0
    )

    if not name:

        db.close()

        flash(
            "Le nom du produit est obligatoire.",
            "error"
        )

        return redirect(
            url_for(
                "admin_product_edit",
                product_id=product_id
            )
        )

    if price < 0:

        db.close()

        flash(
            "Le prix ne peut pas être négatif.",
            "error"
        )

        return redirect(
            url_for(
                "admin_product_edit",
                product_id=product_id
            )
        )

    if stock < 0:

        db.close()

        flash(
            "Le stock ne peut pas être négatif.",
            "error"
        )

        return redirect(
            url_for(
                "admin_product_edit",
                product_id=product_id
            )
        )

    if not 0 <= promotion_discount <= 100:

        db.close()

        flash(
            "La réduction doit être comprise entre 0 et 100 %.",
            "error"
        )

        return redirect(
            url_for(
                "admin_product_edit",
                product_id=product_id
            )
        )

    db.execute(
        """
        UPDATE products
        SET
            name = ?,
            description = ?,
            price = ?,
            stock = ?,
            image = ?,
            category_id = ?,
            promotion_active = ?,
            promotion_discount = ?
        WHERE id = ?
        """,
        (
            name,
            description,
            price,
            stock,
            image,
            category_id,
            promotion_active,
            promotion_discount,
            product_id
        )
    )

    db.commit()
    db.close()

    flash(
        "Produit modifié avec succès.",
        "success"
    )

    return redirect(
        url_for("admin_products")
    )


# ============================================================
# ADMIN SUPPRIMER PRODUIT
# ============================================================

@app.post(
    "/admin/produits/<int:product_id>/supprimer"
)
@admin_required
def admin_product_delete(product_id):

    db = get_db()

    db.execute(
        """
        DELETE FROM products
        WHERE id = ?
        """,
        (
            product_id,
        )
    )

    db.commit()
    db.close()

    # --------------------------------------------------------
    # IMPORTANT :
    # si le produit était dans un panier,
    # on le retire également de toutes les nouvelles sessions.
    # Pour la session actuelle, on le retire immédiatement.
    # --------------------------------------------------------

    cart = session.get(
        "cart",
        {}
    )

    if isinstance(cart, dict):

        cart.pop(
            str(product_id),
            None
        )

        session["cart"] = cart
        session.modified = True

    flash(
        "Produit supprimé.",
        "success"
    )

    return redirect(
        url_for("admin_products")
    )


# ============================================================
# ADMIN CATEGORIES
# ============================================================

@app.route(
    "/admin/categories",
    methods=["GET", "POST"]
)
@admin_required
def admin_categories():

    db = get_db()

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        slug = request.form.get(
            "slug",
            ""
        ).strip().lower()

        if not name:

            db.close()

            flash(
                "Le nom de la catégorie est obligatoire.",
                "error"
            )

            return redirect(
                url_for("admin_categories")
            )

        if not slug:

            slug = (
                name
                .lower()
                .replace(" ", "-")
            )

        try:

            db.execute(
                """
                INSERT INTO categories
                (
                    name,
                    slug
                )
                VALUES (?, ?)
                """,
                (
                    name,
                    slug
                )
            )

            db.commit()

            flash(
                "Catégorie créée.",
                "success"
            )

        except sqlite3.IntegrityError:

            flash(
                "Cette catégorie existe déjà.",
                "error"
            )

        db.close()

        return redirect(
            url_for("admin_categories")
        )

    categories = db.execute(
        """
        SELECT *
        FROM categories
        ORDER BY name ASC
        """
    ).fetchall()

    db.close()

    return render_template(
        "admin/categories.html",
        categories=categories
    )


# ============================================================
# SUPPRIMER CATEGORIE
# ============================================================

@app.post(
    "/admin/categories/<int:category_id>/supprimer"
)
@admin_required
def admin_category_delete(category_id):

    db = get_db()

    db.execute(
        """
        DELETE FROM categories
        WHERE id = ?
        """,
        (
            category_id,
        )
    )

    db.commit()
    db.close()

    flash(
        "Catégorie supprimée.",
        "success"
    )

    return redirect(
        url_for("admin_categories")
    )


# ============================================================
# ADMIN PROMOTIONS
# ============================================================

@app.route(
    "/admin/promos",
    methods=["GET", "POST"]
)
@admin_required
def admin_promos():

    db = get_db()

    if request.method == "POST":

        code = request.form.get(
            "code",
            ""
        ).strip().upper()

        try:

            discount = float(
                request.form.get(
                    "discount",
                    0
                )
            )

        except (ValueError, TypeError):

            discount = 0

        if (
            not code
            or discount <= 0
            or discount > 100
        ):

            flash(
                "Code ou réduction invalide.",
                "error"
            )

        else:

            try:

                db.execute(
                    """
                    INSERT INTO promos
                    (
                        code,
                        discount,
                        active
                    )
                    VALUES (?, ?, 1)
                    """,
                    (
                        code,
                        discount
                    )
                )

                db.commit()

                flash(
                    "Code promo créé.",
                    "success"
                )

            except sqlite3.IntegrityError:

                flash(
                    "Ce code promo existe déjà.",
                    "error"
                )

        db.close()

        return redirect(
            url_for("admin_promos")
        )

    promos = db.execute(
        """
        SELECT *
        FROM promos
        ORDER BY id DESC
        """
    ).fetchall()

    db.close()

    return render_template(
        "admin/promos.html",
        promos=promos
    )


# ============================================================
# ACTIVER / DESACTIVER PROMO
# ============================================================

@app.post(
    "/admin/promos/<int:promo_id>/toggle"
)
@admin_required
def admin_promo_toggle(promo_id):

    db = get_db()

    promo = db.execute(
        """
        SELECT active
        FROM promos
        WHERE id = ?
        """,
        (
            promo_id,
        )
    ).fetchone()

    if promo is None:

        db.close()

        flash(
            "Code promo introuvable.",
            "error"
        )

        return redirect(
            url_for("admin_promos")
        )

    new_state = (
        0
        if promo["active"]
        else 1
    )

    db.execute(
        """
        UPDATE promos
        SET active = ?
        WHERE id = ?
        """,
        (
            new_state,
            promo_id
        )
    )

    db.commit()
    db.close()

    flash(
        "Code promo activé."
        if new_state
        else "Code promo désactivé.",
        "success"
    )

    return redirect(
        url_for("admin_promos")
    )


# ============================================================
# SUPPRIMER PROMO
# ============================================================

@app.post(
    "/admin/promos/<int:promo_id>/supprimer"
)
@admin_required
def admin_promo_delete(promo_id):

    db = get_db()

    db.execute(
        """
        DELETE FROM promos
        WHERE id = ?
        """,
        (
            promo_id,
        )
    )

    db.commit()
    db.close()

    flash(
        "Code promo supprimé.",
        "success"
    )

    return redirect(
        url_for("admin_promos")
    )


# ============================================================
# COMMANDES ADMIN
# ============================================================

@app.route("/admin/commandes")
@admin_required
def admin_orders():

    db = get_db()

    orders = db.execute(
        """
        SELECT *
        FROM orders
        ORDER BY id DESC
        """
    ).fetchall()

    db.close()

    return render_template(
        "admin/commandes.html",
        orders=orders
    )


# ============================================================
# LANCEMENT LOCAL
# ============================================================

if __name__ == "__main__":

    print("")
    print("======================================")
    print("          LB'SPEED ONLINE")
    print("======================================")
    print("")
    print("Boutique : http://127.0.0.1:5000")
    print("Admin    : http://127.0.0.1:5000/admin")
    print("")
    print("Compte admin configuré via .env")
    print("")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )