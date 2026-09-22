import sqlite3
from pathlib import Path


# ============================================================
# CHEMINS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATABASE_DIR = BASE_DIR / "database"
DATABASE_DIR.mkdir(exist_ok=True)

DATABASE = DATABASE_DIR / "lbspeed.db"


# ============================================================
# CONNEXION
# ============================================================

def get_db():

    db = sqlite3.connect(
        DATABASE
    )

    db.row_factory = sqlite3.Row

    db.execute(
        "PRAGMA foreign_keys = ON"
    )

    return db


# ============================================================
# MIGRATION AUTOMATIQUE
# ============================================================

def ensure_column(
    db,
    table,
    column,
    definition
):

    columns = [
        row["name"]
        for row in db.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    ]

    if column not in columns:

        db.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {column} {definition}
            """
        )

        print(
            f"[DB] Colonne ajoutée : "
            f"{table}.{column}"
        )


# ============================================================
# INITIALISATION
# ============================================================

def init_database():

    db = get_db()

    # ========================================================
    # CATÉGORIES
    # ========================================================

    db.execute("""
        CREATE TABLE IF NOT EXISTS categories (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL UNIQUE,

            slug TEXT NOT NULL UNIQUE

        )
    """)

    # ========================================================
    # PRODUITS
    # ========================================================

    db.execute("""
        CREATE TABLE IF NOT EXISTS products (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            description TEXT DEFAULT '',

            price REAL NOT NULL DEFAULT 0,

            stock INTEGER NOT NULL DEFAULT 0,

            image TEXT DEFAULT '',

            category_id INTEGER,

            created_at
                TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (category_id)
                REFERENCES categories(id)
                ON DELETE SET NULL

        )
    """)

    # ========================================================
    # PROMOTIONS PRODUITS
    # ========================================================

    ensure_column(
        db,
        "products",
        "promotion_active",
        "INTEGER NOT NULL DEFAULT 0"
    )

    ensure_column(
        db,
        "products",
        "promotion_discount",
        "REAL NOT NULL DEFAULT 0"
    )

    # ========================================================
    # CODES PROMO
    # ========================================================

    db.execute("""
        CREATE TABLE IF NOT EXISTS promos (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            code TEXT NOT NULL UNIQUE,

            discount REAL NOT NULL DEFAULT 0,

            active INTEGER NOT NULL DEFAULT 1

        )
    """)

    # ========================================================
    # COMMANDES
    # ========================================================

    db.execute("""
        CREATE TABLE IF NOT EXISTS orders (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            customer_name TEXT NOT NULL,

            customer_email TEXT NOT NULL,

            total REAL NOT NULL DEFAULT 0,

            status TEXT NOT NULL DEFAULT 'Nouvelle',

            created_at
                TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP

        )
    """)

    # ========================================================
    # PRODUITS DES COMMANDES
    # ========================================================

    db.execute("""
        CREATE TABLE IF NOT EXISTS order_items (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            order_id INTEGER NOT NULL,

            product_id INTEGER,

            product_name TEXT NOT NULL,

            quantity INTEGER NOT NULL,

            price REAL NOT NULL,

            FOREIGN KEY (order_id)
                REFERENCES orders(id)
                ON DELETE CASCADE

        )
    """)

    db.commit()

    # ========================================================
    # VÉRIFICATIONS
    # ========================================================

    product_columns = [
        row["name"]
        for row in db.execute(
            "PRAGMA table_info(products)"
        ).fetchall()
    ]

    print("")
    print("================================")
    print("       LB'SPEED DATABASE")
    print("================================")
    print("")
    print(
        "Base de données prête !"
    )
    print(
        f"Emplacement : {DATABASE}"
    )
    print("")

    print(
        "Colonnes produits :"
    )

    for column in product_columns:
        print(
            f"  [OK] {column}"
        )

    print("")

    db.close()


# ============================================================
# LANCEMENT DIRECT
# ============================================================

if __name__ == "__main__":

    init_database()