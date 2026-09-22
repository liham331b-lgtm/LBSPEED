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


# =========================================================
# CONFIGURATION
# =========================================================

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

# Minimum obligatoire pour passer commande
MINIMUM_COMMANDE = 10.00

init_database()


# =========================================================
# ADMIN
# =========================================================

def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("admin"):
            return redirect(url_for("admin_login"))

        return function(*args, **kwargs)

    return wrapper


# =========================================================
# VARIABLES GLOBALES
# =========================================================

@app.context_processor
def global_variables():

    cart = session.get(
        "cart",
        {}
    )

    cart_count = sum(
        cart.values()
    )

    return {
        "cart_count": cart_count,
        "minimum_commande": MINIMUM_COMMANDE
    }


# =========================================================
# ACCUEIL
# =========================================================

@app.route("/")
def index():

    db = get_db()

    products = db.execute("""
        SELECT
            p.*,
            c.name AS category_name
        FROM products p
        LEFT JOIN categories c
            ON c.id = p.category_id
        ORDER BY p.id DESC
        LIMIT 8
    """).fetchall()

    categories = db.execute("""
        SELECT *
        FROM categories
        ORDER BY name
    """).fetchall()

    db.close()

    return render_template(
        "index.html",
        products=products,
        categories=categories
    )


# =========================================================
# BOUTIQUE
# =========================================================

@app.route("/boutique")
def boutique():

    category = request.args.get(
        "category",
        ""
    ).strip()

    search = request.args.get(
        "q",
        ""
    ).strip()

    nouveautes = request.args.get(
        "nouveautes",
        ""
    ).strip()

    db = get_db()

    categories = db.execute("""
        SELECT *
        FROM categories
        ORDER BY name
    """).fetchall()

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

        params.append(
            category
        )

    if search:

        query += """
            AND (
                p.name LIKE ?
                OR p.description LIKE ?
            )
        """

        params.append(
            f"%{search}%"
        )

        params.append(
            f"%{search}%"
        )

    if nouveautes == "1":

        query += """
            ORDER BY p.id DESC
            LIMIT 8
        """

    else:

        query += """
            ORDER BY p.id DESC
        """

    products = db.execute(
        query,
        params
    ).fetchall()

    db.close()

    return render_template(
        "boutique.html",
        products=products,
        categories=categories,
        selected_category=category,
        q=search,
        nouveautes=nouveautes
    )


# =========================================================
# PRODUIT
# =========================================================

@app.route("/produit/<int:product_id>")
def product(product_id):

    db = get_db()

    product = db.execute("""
        SELECT
            p.*,
            c.name AS category_name
        FROM products p
        LEFT JOIN categories c
            ON c.id = p.category_id
        WHERE p.id = ?
    """, (
        product_id,
    )).fetchone()

    db.close()

    if product is None:

        return "Produit introuvable", 404

    return render_template(
        "produit.html",
        product=product
    )


# =========================================================
# PANIER
# =========================================================

@app.route("/panier")
def cart():

    cart_data = session.get(
        "cart",
        {}
    )

    db = get_db()

    items = []

    total = 0

    for product_id, quantity in cart_data.items():

        product = db.execute("""
            SELECT *
            FROM products
            WHERE id = ?
        """, (
            product_id,
        )).fetchone()

        if product is None:
            continue

        try:

            quantity = int(
                quantity
            )

        except (ValueError, TypeError):

            quantity = 1

        quantity = max(
            1,
            quantity
        )

        subtotal = (
            product["price"] *
            quantity
        )

        total += subtotal

        items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal
        })

    db.close()

    total = round(
        total,
        2
    )

    reste = max(
        0,
        round(
            MINIMUM_COMMANDE - total,
            2
        )
    )

    return render_template(
        "panier.html",
        items=items,
        total=total,
        reste_minimum=reste,
        commande_autorisee=(
            total >= MINIMUM_COMMANDE
        )
    )


# =========================================================
# CHECKOUT
# =========================================================

@app.route("/checkout")
def checkout():

    cart_data = session.get(
        "cart",
        {}
    )

    # -----------------------------------------------------
    # PANIER VIDE
    # -----------------------------------------------------

    if not cart_data:

        flash(
            "Ton panier est vide.",
            "error"
        )

        return redirect(
            url_for("cart")
        )

    db = get_db()

    items = []

    total = 0

    # -----------------------------------------------------
    # CALCUL DU PANIER
    # -----------------------------------------------------

    for product_id, quantity in cart_data.items():

        product = db.execute("""
            SELECT *
            FROM products
            WHERE id = ?
        """, (
            product_id,
        )).fetchone()

        if product is None:
            continue

        try:

            quantity = int(
                quantity
            )

        except (ValueError, TypeError):

            quantity = 1

        quantity = max(
            1,
            quantity
        )

        subtotal = (
            product["price"] *
            quantity
        )

        total += subtotal

        items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal
        })

    db.close()

    total = round(
        total,
        2
    )

    # -----------------------------------------------------
    # MINIMUM DE COMMANDE
    # -----------------------------------------------------

    if total < MINIMUM_COMMANDE:

        reste = round(
            MINIMUM_COMMANDE - total,
            2
        )

        flash(
            f"Minimum de commande : "
            f"{MINIMUM_COMMANDE:.2f} €. "
            f"Il te manque {reste:.2f} €.",
            "error"
        )

        return redirect(
            url_for("cart")
        )

    # -----------------------------------------------------
    # CHECKOUT AUTORISÉ
    # -----------------------------------------------------

    return render_template(
        "checkout.html",
        items=items,
        total=total,
        minimum_commande=MINIMUM_COMMANDE
    )


# =========================================================
# AJOUT PANIER
# =========================================================

@app.post("/api/cart/add")
def cart_add():

    data = request.get_json(
        silent=True
    ) or {}

    product_id = str(
        data.get(
            "product_id",
            ""
        )
    )

    try:

        quantity = int(
            data.get(
                "quantity",
                1
            )
        )

    except (ValueError, TypeError):

        quantity = 1

    quantity = max(
        1,
        quantity
    )

    db = get_db()

    product = db.execute("""
        SELECT
            id,
            stock
        FROM products
        WHERE id = ?
    """, (
        product_id,
    )).fetchone()

    db.close()

    if product is None:

        return jsonify({
            "ok": False,
            "message": "Produit introuvable."
        }), 404

    if product["stock"] <= 0:

        return jsonify({
            "ok": False,
            "message": "Produit en rupture de stock."
        }), 400

    cart = session.get(
        "cart",
        {}
    )

    old_quantity = cart.get(
        product_id,
        0
    )

    new_quantity = (
        old_quantity +
        quantity
    )

    if new_quantity > product["stock"]:

        new_quantity = product["stock"]

    cart[product_id] = new_quantity

    session["cart"] = cart

    return jsonify({
        "ok": True,
        "count": sum(
            cart.values()
        )
    })


# =========================================================
# MODIFICATION PANIER
# =========================================================

@app.post("/api/cart/update")
def cart_update():

    data = request.get_json(
        silent=True
    ) or {}

    product_id = str(
        data.get(
            "product_id",
            ""
        )
    )

    try:

        quantity = int(
            data.get(
                "quantity",
                0
            )
        )

    except (ValueError, TypeError):

        quantity = 0

    cart = session.get(
        "cart",
        {}
    )

    if product_id in cart:

        if quantity <= 0:

            cart.pop(
                product_id
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

            if product:

                quantity = min(
                    quantity,
                    product["stock"]
                )

                if quantity <= 0:

                    cart.pop(
                        product_id,
                        None
                    )

                else:

                    cart[product_id] = quantity

    session["cart"] = cart

    return jsonify({
        "ok": True,
        "count": sum(
            cart.values()
        )
    })


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        )

        password = request.form.get(
            "password",
            ""
        )

        if (
            username == ADMIN_USERNAME
            and
            password == ADMIN_PASSWORD
        ):

            session["admin"] = True

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        flash(
            "Identifiants incorrects.",
            "error"
        )

    return render_template(
        "admin/login.html"
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for(
            "admin_login"
        )
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    db = get_db()

    products = db.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]

    categories = db.execute(
        "SELECT COUNT(*) FROM categories"
    ).fetchone()[0]

    promos = db.execute(
        "SELECT COUNT(*) FROM promos"
    ).fetchone()[0]

    orders = db.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

    low_stock = db.execute(
        "SELECT COUNT(*) FROM products WHERE stock <= 5"
    ).fetchone()[0]

    db.close()

    stats = {
        "products": products,
        "categories": categories,
        "promos": promos,
        "orders": orders,
        "low_stock": low_stock
    }

    return render_template(
        "admin/dashboard.html",
        stats=stats
    )


# =========================================================
# ADMIN PRODUITS
# =========================================================

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

        except (ValueError, TypeError):

            flash(
                "Prix ou stock invalide.",
                "error"
            )

            db.close()

            return redirect(
                url_for(
                    "admin_products"
                )
            )

        category_id = (
            request.form.get(
                "category_id"
            )
            or None
        )

        if not name:

            flash(
                "Le nom du produit est obligatoire.",
                "error"
            )

        else:

            db.execute("""
                INSERT INTO products
                (
                    name,
                    description,
                    price,
                    stock,
                    image,
                    category_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                name,
                description,
                price,
                stock,
                image,
                category_id
            ))

            db.commit()

            flash(
                "Produit ajouté avec succès.",
                "success"
            )

        db.close()

        return redirect(
            url_for(
                "admin_products"
            )
        )

    products = db.execute("""
        SELECT
            p.*,
            c.name AS category_name
        FROM products p
        LEFT JOIN categories c
            ON c.id = p.category_id
        ORDER BY p.id DESC
    """).fetchall()

    categories = db.execute("""
        SELECT *
        FROM categories
        ORDER BY name
    """).fetchall()

    db.close()

    return render_template(
        "admin/produits.html",
        products=products,
        categories=categories
    )


# =========================================================
# MODIFIER PRODUIT
# =========================================================

@app.post(
    "/admin/produits/<int:product_id>/modifier"
)
@admin_required
def admin_product_edit(product_id):

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

    except (ValueError, TypeError):

        flash(
            "Prix ou stock invalide.",
            "error"
        )

        return redirect(
            url_for(
                "admin_products"
            )
        )

    category_id = (
        request.form.get(
            "category_id"
        )
        or None
    )

    db = get_db()

    db.execute("""
        UPDATE products
        SET
            name = ?,
            description = ?,
            price = ?,
            stock = ?,
            image = ?,
            category_id = ?
        WHERE id = ?
    """, (
        name,
        description,
        price,
        stock,
        image,
        category_id,
        product_id
    ))

    db.commit()
    db.close()

    flash(
        "Produit modifié.",
        "success"
    )

    return redirect(
        url_for(
            "admin_products"
        )
    )


# =========================================================
# SUPPRIMER PRODUIT
# =========================================================

@app.post(
    "/admin/produits/<int:product_id>/supprimer"
)
@admin_required
def admin_product_delete(product_id):

    db = get_db()

    db.execute(
        "DELETE FROM products WHERE id = ?",
        (product_id,)
    )

    db.commit()
    db.close()

    flash(
        "Produit supprimé.",
        "success"
    )

    return redirect(
        url_for(
            "admin_products"
        )
    )


# =========================================================
# CATÉGORIES
# =========================================================

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

        slug = (
            name
            .lower()
            .replace(" ", "-")
        )

        if not name:

            flash(
                "Le nom est obligatoire.",
                "error"
            )

        else:

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
            url_for(
                "admin_categories"
            )
        )

    categories = db.execute("""
        SELECT *
        FROM categories
        ORDER BY name
    """).fetchall()

    db.close()

    return render_template(
        "admin/categories.html",
        categories=categories
    )


# =========================================================
# SUPPRIMER CATÉGORIE
# =========================================================

@app.post(
    "/admin/categories/<int:category_id>/supprimer"
)
@admin_required
def admin_category_delete(category_id):

    db = get_db()

    db.execute(
        "DELETE FROM categories WHERE id = ?",
        (category_id,)
    )

    db.commit()
    db.close()

    flash(
        "Catégorie supprimée.",
        "success"
    )

    return redirect(
        url_for(
            "admin_categories"
        )
    )


# =========================================================
# PROMOS
# =========================================================

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
            url_for(
                "admin_promos"
            )
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


# =========================================================
# SUPPRIMER PROMO
# =========================================================

@app.post(
    "/admin/promos/<int:promo_id>/supprimer"
)
@admin_required
def admin_promo_delete(promo_id):

    db = get_db()

    db.execute(
        "DELETE FROM promos WHERE id = ?",
        (promo_id,)
    )

    db.commit()
    db.close()

    flash(
        "Code promo supprimé.",
        "success"
    )

    return redirect(
        url_for(
            "admin_promos"
        )
    )


# =========================================================
# COMMANDES
# =========================================================

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


# =========================================================
# LANCEMENT
# =========================================================

if __name__ == "__main__":

    print("")
    print("======================================")
    print("          LB'SPEED ONLINE")
    print("======================================")
    print("")
    print("Boutique : http://127.0.0.1:5000")
    print("Admin    : http://127.0.0.1:5000/admin")
    print("Minimum  : 10.00 €")
    print("")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )