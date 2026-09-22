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
# INITIALISATION DATABASE
# ============================================================

init_database()


# ============================================================
# OUTILS ADMIN
# ============================================================

def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# PRIX FINAL PRODUIT
# ============================================================

def product_final_price(product):
    """
    Calcule le prix final d'un produit avec sa promotion.
    """

    try:
        original_price = float(product["price"] or 0)
    except (KeyError, TypeError, ValueError):
        original_price = 0.00

    promotion_active = 0
    promotion_discount = 0.00

    # Protection si les anciennes DB n'ont pas encore les colonnes
    try:
        promotion_active = int(
            product["promotion_active"] or 0
        )
    except (KeyError, TypeError, ValueError):
        promotion_active = 0

    try:
        promotion_discount = float(
            product["promotion_discount"] or 0
        )
    except (KeyError, TypeError, ValueError):
        promotion_discount = 0.00

    promotion_discount = min(
        max(promotion_discount, 0),
        100
    )

    if promotion_active and promotion_discount > 0:
        return round(
            original_price * (
                1 - promotion_discount / 100
            ),
            2
        )

    return round(
        original_price,
        2
    )


# ============================================================
# CODE PROMO ACTIF
# ============================================================

def get_active_promo(code):

    if not code:
        return None

    db = get_db()

    promo = db.execute("""
        SELECT *
        FROM promos
        WHERE UPPER(code) = ?
          AND active = 1
        LIMIT 1
    """, (
        str(code).strip().upper(),
    )).fetchone()

    db.close()

    return promo


# ============================================================
# CALCUL PANIER
# ============================================================

def calculate_cart():

    cart_data = session.get(
        "cart",
        {}
    )

    db = get_db()

    items = []
    subtotal = 0.00

    for product_id, quantity in cart_data.items():

        product = db.execute("""
            SELECT
                p.*,
                c.name AS category_name,
                c.slug AS category_slug
            FROM products p
            LEFT JOIN categories c
                ON c.id = p.category_id
            WHERE p.id = ?
        """, (
            product_id,
        )).fetchone()

        if product is None:
            continue

        # ----------------------------------------------------
        # QUANTITE
        # ----------------------------------------------------

        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            quantity = 1

        quantity = max(
            1,
            quantity
        )

        # ----------------------------------------------------
        # STOCK
        # ----------------------------------------------------

        try:
            stock = int(
                product["stock"] or 0
            )
        except (ValueError, TypeError):
            stock = 0

        if stock <= 0:
            continue

        quantity = min(
            quantity,
            stock
        )

        # ----------------------------------------------------
        # PRIX
        # ----------------------------------------------------

        try:
            original_price = round(
                float(product["price"] or 0),
                2
            )
        except (ValueError, TypeError):
            original_price = 0.00

        unit_price = product_final_price(
            product
        )

        line_total = round(
            unit_price * quantity,
            2
        )

        subtotal += line_total

        items.append({
            "product": product,
            "quantity": quantity,
            "original_price": original_price,
            "unit_price": unit_price,
            "subtotal": line_total
        })

    db.close()

    subtotal = round(
        subtotal,
        2
    )

    # ========================================================
    # PROMOTION GLOBALE
    # ========================================================

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
                discount_percent = 0

            discount_percent = min(
                max(discount_percent, 0),
                100
            )

            promo_discount = round(
                subtotal *
                discount_percent /
                100,
                2
            )

        else:
            session.pop(
                "promo_code",
                None
            )

    # ========================================================
    # TOTAL
    # ========================================================

    total = round(
        max(
            0,
            subtotal - promo_discount
        ),
        2
    )

    reste_minimum = round(
        max(
            0,
            MINIMUM_COMMANDE - total
        ),
        2
    )

    commande_autorisee = (
        total >= MINIMUM_COMMANDE
    )

    return {
        "items": items,
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

    cart = session.get(
        "cart",
        {}
    )

    cart_count = 0

    for quantity in cart.values():

        try:
            cart_count += int(quantity)
        except (ValueError, TypeError):
            pass

    return {
        "cart_count": cart_count,
        "minimum_commande": MINIMUM_COMMANDE,
        "product_final_price": product_final_price
    }


# ============================================================
# ACCUEIL
# ============================================================

@app.route("/")
def index():

    db = get_db()

    products = db.execute("""
        SELECT
            p.*,
            c.name AS category_name,
            c.slug AS category_slug
        FROM products p
        LEFT JOIN categories c
            ON c.id = p.category_id
        ORDER BY p.id DESC
        LIMIT 12
    """).fetchall()

    categories = db.execute("""
        SELECT *
        FROM categories
        ORDER BY name ASC
    """).fetchall()

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

    # --------------------------------------------------------
    # CATEGORIE
    # --------------------------------------------------------

    if category:

        query += """
            AND c.slug = ?
        """

        params.append(
            category
        )

    # --------------------------------------------------------
    # RECHERCHE
    # --------------------------------------------------------

    if search:

        query += """
            AND (
                p.name LIKE ?
                OR p.description LIKE ?
            )
        """

        search_value = f"%{search}%"

        params.extend([
            search_value,
            search_value
        ])

    # --------------------------------------------------------
    # TRI
    # --------------------------------------------------------

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

    categories = db.execute("""
        SELECT *
        FROM categories
        ORDER BY name ASC
    """).fetchall()

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

    product = db.execute("""
        SELECT
            p.*,
            c.name AS category_name,
            c.slug AS category_slug
        FROM products p
        LEFT JOIN categories c
            ON c.id = p.category_id
        WHERE p.id = ?
    """, (
        product_id,
    )).fetchone()

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

        related_products = db.execute("""
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
        """, (
            product["category_id"],
            product_id
        )).fetchall()

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

    cart_data = calculate_cart()

    return render_template(
        "panier.html",
        items=cart_data["items"],
        subtotal=cart_data["subtotal"],
        promo=cart_data["promo"],
        promo_discount=cart_data["promo_discount"],
        total=cart_data["total"],
        reste_minimum=cart_data["reste_minimum"],
        commande_autorisee=cart_data["commande_autorisee"]
    )


# ============================================================
# AJOUT PANIER
# ============================================================

@app.post("/api/cart/add")
def cart_add():

    data = request.get_json(
        silent=True
    ) or {}

    product_id = data.get(
        "product_id"
    )

    quantity = data.get(
        "quantity",
        1
    )

    try:

        product_id = int(
            product_id
        )

        quantity = int(
            quantity
        )

    except (ValueError, TypeError):

        return jsonify({
            "success": False,
            "message": "Produit ou quantité invalide."
        }), 400

    quantity = max(
        1,
        quantity
    )

    db = get_db()

    product = db.execute("""
        SELECT *
        FROM products
        WHERE id = ?
    """, (
        product_id,
    )).fetchone()

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

    cart = session.get(
        "cart",
        {}
    )

    key = str(
        product_id
    )

    try:
        current_quantity = int(
            cart.get(key, 0)
        )
    except (ValueError, TypeError):
        current_quantity = 0

    new_quantity = min(
        current_quantity + quantity,
        stock
    )

    cart[key] = new_quantity

    session["cart"] = cart
    session.modified = True

    cart_count = 0

    for q in cart.values():

        try:
            cart_count += int(q)
        except (ValueError, TypeError):
            pass

    return jsonify({
        "success": True,
        "message": "Produit ajouté au panier.",
        "cart_count": cart_count
    })


# ============================================================
# MODIFICATION PANIER
# ============================================================

@app.post("/api/cart/update")
def cart_update():

    data = request.get_json(
        silent=True
    ) or {}

    product_id = data.get(
        "product_id"
    )

    quantity = data.get(
        "quantity"
    )

    try:

        product_id = int(
            product_id
        )

        quantity = int(
            quantity
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

    key = str(
        product_id
    )

    if quantity <= 0:

        cart.pop(
            key,
            None
        )

    else:

        db = get_db()

        product = db.execute("""
            SELECT stock
            FROM products
            WHERE id = ?
        """, (
            product_id,
        )).fetchone()

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

            quantity = min(
                quantity,
                stock
            )

            if quantity <= 0:

                cart.pop(
                    key,
                    None
                )

            else:

                cart[key] = quantity

    session["cart"] = cart
    session.modified = True

    cart_count = 0

    for q in cart.values():

        try:
            cart_count += int(q)
        except (ValueError, TypeError):
            pass

    return jsonify({
        "success": True,
        "cart_count": cart_count
    })


# ============================================================
# VIDER PANIER
# ============================================================

@app.post("/api/cart/clear")
def cart_clear():

    session["cart"] = {}
    session.pop(
        "promo_code",
        None
    )

    return jsonify({
        "success": True
    })


# ============================================================
# APPLIQUER PROMO
# ============================================================

@app.post("/promo/appliquer")
def apply_promo():

    code = request.form.get(
        "code",
        ""
    ).strip().upper()

    if not code:

        flash(
            "Entre un code promo.",
            "error"
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

        return redirect(
            url_for("cart")
        )

    session["promo_code"] = code

    flash(
        f"Code {code} appliqué : "
        f"-{float(promo['discount']):g} %",
        "success"
    )

    return redirect(
        url_for("cart")
    )


# ============================================================
# SUPPRIMER PROMO
# ============================================================

@app.post("/promo/supprimer")
def remove_promo():

    session.pop(
        "promo_code",
        None
    )

    flash(
        "Code promo retiré.",
        "success"
    )

    return redirect(
        url_for("cart")
    )


# ============================================================
# CHECKOUT
# ============================================================

@app.route("/checkout")
def checkout():

    cart_data = calculate_cart()

    if not cart_data["items"]:

        flash(
            "Ton panier est vide.",
            "error"
        )

        return redirect(
            url_for("cart")
        )

    if not cart_data["commande_autorisee"]:

        flash(
            f"Minimum de commande : "
            f"{MINIMUM_COMMANDE:.2f} €. "
            f"Il te manque "
            f"{cart_data['reste_minimum']:.2f} €.",
            "error"
        )

        return redirect(
            url_for("cart")
        )

    return render_template(
        "checkout.html",
        items=cart_data["items"],
        subtotal=cart_data["subtotal"],
        promo=cart_data["promo"],
        promo_discount=cart_data["promo_discount"],
        total=cart_data["total"],
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

    # --------------------------------------------------------
    # STATISTIQUES
    # --------------------------------------------------------

    products_count = db.execute("""
        SELECT COUNT(*)
        FROM products
    """).fetchone()[0]

    categories_count = db.execute("""
        SELECT COUNT(*)
        FROM categories
    """).fetchone()[0]

    promos_count = db.execute("""
        SELECT COUNT(*)
        FROM promos
    """).fetchone()[0]

    orders_count = db.execute("""
        SELECT COUNT(*)
        FROM orders
    """).fetchone()[0]

    total_stock = db.execute("""
        SELECT COALESCE(
            SUM(stock),
            0
        )
        FROM products
    """).fetchone()[0]

    total_sales = db.execute("""
        SELECT COALESCE(
            SUM(total),
            0
        )
        FROM orders
    """).fetchone()[0]

    # --------------------------------------------------------
    # PRODUITS EN RUPTURE
    # --------------------------------------------------------

    out_of_stock = db.execute("""
        SELECT COUNT(*)
        FROM products
        WHERE stock <= 0
    """).fetchone()[0]

    # --------------------------------------------------------
    # COMMANDES RECENTES
    # --------------------------------------------------------

    recent_orders = db.execute("""
        SELECT *
        FROM orders
        ORDER BY id DESC
        LIMIT 5
    """).fetchall()

    # --------------------------------------------------------
    # PRODUITS RECENTS
    # --------------------------------------------------------

    recent_products = db.execute("""
        SELECT
            p.*,
            c.name AS category_name
        FROM products p
        LEFT JOIN categories c
            ON c.id = p.category_id
        ORDER BY p.id DESC
        LIMIT 5
    """).fetchall()

    db.close()

    # --------------------------------------------------------
    # DICTIONNAIRE STATS
    # --------------------------------------------------------

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

        # Nouveau système
        stats=stats,

        # Anciennes variables conservées
        # pour compatibilité avec ton template
        products_count=products_count,
        categories_count=categories_count,
        promos_count=promos_count,
        orders_count=orders_count,
        total_sales=round(
            float(total_sales or 0),
            2
        ),

        # Données supplémentaires
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
            request.form.get(
                "category_id"
            )
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

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # CREATION
        # ----------------------------------------------------

        db.execute("""
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
        """, (
            name,
            description,
            price,
            stock,
            image,
            category_id,
            promotion_active,
            promotion_discount
        ))

        db.commit()
        db.close()

        flash(
            "Produit ajouté avec succès.",
            "success"
        )

        return redirect(
            url_for("admin_products")
        )

    # --------------------------------------------------------
    # LISTE PRODUITS
    # --------------------------------------------------------

    products = db.execute("""
        SELECT
            p.*,
            c.name AS category_name,
            c.slug AS category_slug
        FROM products p
        LEFT JOIN categories c
            ON c.id = p.category_id
        ORDER BY p.id DESC
    """).fetchall()

    categories = db.execute("""
        SELECT *
        FROM categories
        ORDER BY name ASC
    """).fetchall()

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

    product = db.execute("""
        SELECT *
        FROM products
        WHERE id = ?
    """, (
        product_id,
    )).fetchone()

    if product is None:

        db.close()

        flash(
            "Produit introuvable.",
            "error"
        )

        return redirect(
            url_for("admin_products")
        )

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    if request.method == "GET":

        categories = db.execute("""
            SELECT *
            FROM categories
            ORDER BY name ASC
        """).fetchall()

        db.close()

        return render_template(
            "admin/produit_edit.html",
            product=product,
            categories=categories
        )

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

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
        request.form.get(
            "category_id"
        )
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

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # UPDATE
    # --------------------------------------------------------

    db.execute("""
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
    """, (
        name,
        description,
        price,
        stock,
        image,
        category_id,
        promotion_active,
        promotion_discount,
        product_id
    ))

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

    db.execute("""
        DELETE FROM products
        WHERE id = ?
    """, (
        product_id,
    ))

    db.commit()
    db.close()

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

            db.execute("""
                INSERT INTO categories
                (
                    name,
                    slug
                )
                VALUES (?, ?)
            """, (
                name,
                slug
            ))

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

    categories = db.execute("""
        SELECT *
        FROM categories
        ORDER BY name ASC
    """).fetchall()

    db.close()

    return render_template(
        "admin/categories.html",
        categories=categories
    )


# ============================================================
# ADMIN SUPPRIMER CATEGORIE
# ============================================================

@app.post(
    "/admin/categories/<int:category_id>/supprimer"
)
@admin_required
def admin_category_delete(category_id):

    db = get_db()

    db.execute("""
        DELETE FROM categories
        WHERE id = ?
    """, (
        category_id,
    ))

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
# ADMIN PROMOS
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

                db.execute("""
                    INSERT INTO promos
                    (
                        code,
                        discount,
                        active
                    )
                    VALUES (?, ?, 1)
                """, (
                    code,
                    discount
                ))

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

    promos = db.execute("""
        SELECT *
        FROM promos
        ORDER BY id DESC
    """).fetchall()

    db.close()

    return render_template(
        "admin/promos.html",
        promos=promos
    )


# ============================================================
# ADMIN TOGGLE PROMO
# ============================================================

@app.post(
    "/admin/promos/<int:promo_id>/toggle"
)
@admin_required
def admin_promo_toggle(promo_id):

    db = get_db()

    promo = db.execute("""
        SELECT active
        FROM promos
        WHERE id = ?
    """, (
        promo_id,
    )).fetchone()

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

    db.execute("""
        UPDATE promos
        SET active = ?
        WHERE id = ?
    """, (
        new_state,
        promo_id
    ))

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
# ADMIN SUPPRIMER PROMO
# ============================================================

@app.post(
    "/admin/promos/<int:promo_id>/supprimer"
)
@admin_required
def admin_promo_delete(promo_id):

    db = get_db()

    db.execute("""
        DELETE FROM promos
        WHERE id = ?
    """, (
        promo_id,
    ))

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
# ADMIN COMMANDES
# ============================================================

@app.route("/admin/commandes")
@admin_required
def admin_orders():

    db = get_db()

    orders = db.execute("""
        SELECT *
        FROM orders
        ORDER BY id DESC
    """).fetchall()

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