from database import getConnection


def get_business_context():

    conn = getConnection()
    cursor = conn.cursor()

    # ==========================
    # Total Products
    # ==========================

    cursor.execute("""
    SELECT COUNT(*)
    FROM products
    """)

    total_products = cursor.fetchone()[0]

    # ==========================
    # Total Sales
    # ==========================

    cursor.execute("""
    SELECT SUM(total_amount)
    FROM bills
    """)

    total_sales = cursor.fetchone()[0]

    if total_sales is None:
        total_sales = 0

    # ==========================
    # Total Profit
    # ==========================

    cursor.execute("""
    SELECT SUM(
        (p.selling_price-p.cost_price)
        *bi.quantity
    )
    FROM bill_items bi
    JOIN products p
    ON bi.product_id=p.pid
    """)

    total_profit = cursor.fetchone()[0]

    if total_profit is None:
        total_profit = 0

    # ==========================
    # Low Stock Products
    # ==========================

    cursor.execute("""
    SELECT product_name,stock
    FROM products
    WHERE stock<10
    """)

    low_stock = cursor.fetchall()

    # ==========================
    # Top Selling Products
    # ==========================

    cursor.execute("""
    SELECT
        p.product_name,
        SUM(bi.quantity) qty
    FROM bill_items bi
    JOIN products p
    ON bi.product_id=p.pid
    GROUP BY p.product_name
    ORDER BY qty DESC
    LIMIT 5
    """)

    top_products = cursor.fetchall()

    cursor.close()
    conn.close()

    context = f"""

Business Information

Total Products :
{total_products}

Total Sales :
₹{total_sales}

Total Profit :
₹{total_profit}

Low Stock Products :

{low_stock}

Top Selling Products :

{top_products}

"""

    return context