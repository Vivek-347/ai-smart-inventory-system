from database import getConnection
from flask import session


# ==========================
# Today's Sales
# ==========================
def get_today_sales():

    conn = getConnection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT IFNULL(SUM(total_amount),0)
    FROM bills
    WHERE uid=%s
    AND DATE(bill_date)=CURDATE()
    """,
    (
        session["uid"],
    ))

    sales = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return sales

# ==========================
# Total Sales
# ==========================
def get_total_sales():

    conn = getConnection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT IFNULL(SUM(total_amount),0)
    FROM bills
    WHERE uid=%s
    """,
    (
        session["uid"],
    ))

    sales = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return sales

# ==========================
# Total Profit
# ==========================
def get_total_profit():

    conn = getConnection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
    IFNULL(
        SUM(
            (p.selling_price-p.cost_price)
            * bi.quantity
        ),
        0
    )

    FROM bill_items bi

    JOIN products p
    ON bi.product_id=p.pid

    JOIN bills b
    ON bi.bill_id=b.bill_id

    WHERE
        b.uid=%s
        AND bi.uid=%s
        AND p.uid=%s
    """,
    (
        session["uid"],
        session["uid"],
        session["uid"]
    ))

    profit = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return profit


# ==========================
# Low Stock
# ==========================
def get_low_stock():

    conn = getConnection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        product_name,
        stock
    FROM products
    WHERE uid=%s
    AND stock<10
    """,
    (
        session["uid"],
    ))

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return rows


# ==========================
# Total Products
# ==========================
def get_total_products():

    conn = getConnection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT COUNT(*)
    FROM products
    WHERE uid=%s
    """,
    (
        session["uid"],
    ))

    total = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return total

# ==========================
# Top Selling Products
# ==========================
def get_top_products():

    conn = getConnection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        p.product_name,
        SUM(bi.quantity) qty

    FROM bill_items bi

    JOIN products p
    ON bi.product_id=p.pid

    JOIN bills b
    ON bi.bill_id=b.bill_id

    WHERE
        b.uid=%s
        AND bi.uid=%s
        AND p.uid=%s

    GROUP BY p.product_name

    ORDER BY qty DESC

    LIMIT 5
    """,
    (
        session["uid"],
        session["uid"],
        session["uid"]
    ))

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return rows

# ==========================
# CEO Dashboard Summary
# ==========================

def get_ceo_summary():

    sales = get_total_sales()

    profit = get_total_profit()

    products = get_total_products()

    low_stock = get_low_stock()

    top_products = get_top_products()

    summary = f"""

Business Summary

Total Products : {products}

Total Sales : ₹{sales}

Total Profit : ₹{profit}

Low Stock Products :

{low_stock}

Top Selling Products :

{top_products}

"""

    return summary