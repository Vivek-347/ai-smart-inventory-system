from flask import Flask, render_template, request, session, redirect, flash
from database import getConnection
from functools import wraps
from flask import send_file
from reportlab.pdfgen import canvas
from datetime import datetime, timedelta
from flask import send_file
from reportlab.pdfgen import canvas

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from functools import wraps

from ai import ask_ai
from flask import jsonify
from business_context import get_business_context
from business_context import get_business_context
from business_tools import (
    get_today_sales,
    get_total_sales,
    get_total_profit,
    get_low_stock,
    get_total_products,
    get_top_products
)
from business_tools import (
    get_today_sales,
    get_total_sales,
    get_total_profit,
    get_low_stock,
    get_total_products,
    get_top_products,
    get_ceo_summary
)
import os
from werkzeug.utils import secure_filename
from ocr import extract_purchase_bill
from matching import find_best_product
from classifier import detect_product_details





app = Flask(__name__)
app.secret_key = "inventory123"


# ==========================
# LOGIN REQUIRED DECORATOR
# ==========================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if 'user' not in session:
            return redirect('/login')

        return f(*args, **kwargs)

    return decorated_function


# ==========================
# HOME PAGE
# ==========================
@app.route('/')
def home():
    return redirect('/login')


# ==========================
# REGISTER PAGE
# ==========================
@app.route('/register')
def register():
    return render_template('register.html')


# ==========================
# REGISTER USER
# ==========================
@app.route('/register', methods=['POST'])
def registerUser():

    name = request.form["name"].strip()
    business_name = request.form["business_name"].strip()
    gst_number = request.form.get("gst_number", "").strip()
    fssai_number = request.form.get("fssai_number", "").strip()
    phone = request.form["phone"].strip()
    email = request.form["email"].strip()
    address = request.form["address"].strip()
    city = request.form["city"].strip()
    state = request.form["state"].strip()
    pincode = request.form["pincode"].strip()
    invoice_prefix = request.form["invoice_prefix"].strip()
    password = request.form["password"]

    conn = None
    cursor = None

    try:
        conn = getConnection()
        cursor = conn.cursor()

        # Check whether email already exists
        cursor.execute(
            "SELECT * FROM users WHERE email = %s",
            (email,)
        )

        existing_user = cursor.fetchone()

        if existing_user:
            flash("This email is already registered. Please login.", "error")
            return redirect("/register")

        sql = """
        INSERT INTO users
        (
            name,
            business_name,
            gst_number,
            fssai_number,
            phone,
            email,
            address,
            city,
            state,
            pincode,
            invoice_prefix,
            password
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(
            sql,
            (
                name,
                business_name,
                gst_number,
                fssai_number,
                phone,
                email,
                address,
                city,
                state,
                pincode,
                invoice_prefix,
                password
            )
        )

        conn.commit()

        flash("Registration successful! Please login.", "success")
        return redirect("/login")

    except Exception as e:
        if conn:
            conn.rollback()

        print("Registration Error:", e)

        flash("Registration failed. Please check your details and try again.", "error")
        return redirect("/register")

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

# ==========================
# LOGIN PAGE
# ==========================
@app.route('/login')
def login():
    return render_template('login.html')


# ==========================
# LOGIN USER
# ==========================
@app.route('/login', methods=['POST'])
def loginUser():

    email = request.form['email'].strip()
    password = request.form['password']

    conn = None
    cursor = None

    try:
        conn = getConnection()
        cursor = conn.cursor()

        sql = """
        SELECT * FROM users
        WHERE email = %s AND password = %s
        """

        cursor.execute(sql, (email, password))
        user = cursor.fetchone()

        if user:
            session["uid"] = user[0]
            session["user"] = email
            session["name"] = user[1]

            return redirect("/dashboard")

        flash("Invalid email or password. Please try again.", "error")
        return redirect("/login")

    except Exception as e:
        print("Login Error:", e)

        flash("Something went wrong. Please try again.", "error")
        return redirect("/login")

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()
# ==========================
# DASHBOARD
# ==========================

@app.route('/dashboard')
@login_required
def dashboard():

    conn = getConnection()
    cursor = conn.cursor()

    # ==========================
    # Dashboard Filter
    # ==========================

    period = request.args.get(
        "period",
        "today"
    )

    condition = ""

    dashboard_title = ""

    if period == "today":

        condition = """
        DATE(b.bill_date)=CURDATE()
        """

        dashboard_title = "Today's"

    elif period == "7days":

        condition = """
        b.bill_date >= NOW() - INTERVAL 7 DAY
        """

        dashboard_title = "Last 7 Days"

    elif period == "30days":

        condition = """
        b.bill_date >= NOW() - INTERVAL 30 DAY
        """

        dashboard_title = "Last 30 Days"

    elif period == "6months":

        condition = """
        b.bill_date >= NOW() - INTERVAL 6 MONTH
        """

        dashboard_title = "Last 6 Months"

    elif period == "year":

        condition = """
        YEAR(b.bill_date)=YEAR(CURDATE())
        """

        dashboard_title = "This Year"

    else:

        condition = "1=1"

        dashboard_title = "Lifetime"

    # ==========================
    # Total Products
    # ==========================

    cursor.execute("""
    SELECT COUNT(*)
    FROM products
    WHERE uid=%s
    """,
    (
        session["uid"],
    ))

    total_products = cursor.fetchone()[0]

    # ==========================
    # Total Sales
    # ==========================

    cursor.execute(f"""
    SELECT IFNULL(
        SUM(total_amount),
        0
    )
    FROM bills b
    WHERE
        b.uid=%s
    AND
        {condition}
    """,
    (
        session["uid"],
    ))

    total_sales = cursor.fetchone()[0]

    # ==========================
    # Total Profit
    # ==========================

    cursor.execute(f"""
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

        AND {condition}

    """,
    (

        session["uid"],

        session["uid"],

        session["uid"]

    ))

    total_profit = cursor.fetchone()[0]

    # ==========================
    # Total Bills
    # ==========================

    cursor.execute(f"""
    SELECT COUNT(*)

    FROM bills b

    WHERE

        b.uid=%s

        AND {condition}

    """,
    (
        session["uid"],
    ))

    total_bills = cursor.fetchone()[0]

    # ==========================
    # Low Stock
    # ==========================

    dashboard_settings = get_user_settings(session["uid"])
    low_stock_threshold = int(dashboard_settings.get("low_stock_threshold", 10))
    cursor.execute("""
    SELECT COUNT(*) FROM products
    WHERE uid=%s AND stock > 0 AND stock < %s
    """, (session["uid"], low_stock_threshold))

    low_stock = cursor.fetchone()[0]

    # ==========================
    # BUSINESS HEALTH SCORE
    # ==========================

    if total_products == 0:

        inventory_score = 0

    elif low_stock == total_products:

        inventory_score = 50

    else:

        inventory_score = int(
            (
                (total_products - low_stock)
                / total_products
            ) * 100
        )

    # Sales Score

    sales_target = max(

        total_products * 25000,

        25000

    )

    sales_score = min(

        int(
            (total_sales / sales_target) * 100
        ),

        100

    )

    # Profit Score

    if total_sales == 0:

        profit_score = 0

    else:

        profit_margin = (

            total_profit

            / total_sales

        ) * 100

        profit_score = min(

            int(profit_margin * 2),

            100

        )

    # Final Score

    business_health = int(

        (

            inventory_score * 0.30 +

            sales_score * 0.35 +

            profit_score * 0.35

        )

    )

    cursor.close()

    conn.close()

    return render_template(

        "dashboard.html",

        total_products=total_products,

        total_sales=total_sales,

        total_profit=total_profit,

        total_bills=total_bills,

        low_stock=low_stock,

        business_health=business_health,

        inventory_score=inventory_score,

        sales_score=sales_score,

        profit_score=profit_score,

        dashboard_title=dashboard_title,

        selected_period=period

    )
# =========================================================
# 🤖 AI BUSINESS COPILOT / SMART PREDICTION
# =========================================================

@app.route("/prediction")
@login_required
def prediction():

    conn = getConnection()
    cursor = conn.cursor(dictionary=True)

    try:

        # =================================================
        # GET PRODUCT + 30 DAY SALES DATA
        # =================================================

        cursor.execute("""
            SELECT
                p.pid,
                p.product_name,
                p.stock,
                p.cost_price,
                p.selling_price,

                COALESCE(s.sold_qty, 0) AS sold_qty,
                s.last_sale

            FROM products p

            LEFT JOIN (

                SELECT
                    product_id,
                    SUM(quantity) AS sold_qty,
                    MAX(sale_date) AS last_sale

                FROM bill_items

                WHERE sale_date >= NOW() - INTERVAL 30 DAY
                AND uid=%s

                GROUP BY product_id

            ) s

            ON p.pid = s.product_id

            WHERE p.uid=%s

            ORDER BY p.product_name
        """, (
            session["uid"],
            session["uid"]
        ))

        products = cursor.fetchall()

        # =================================================
        # VARIABLES
        # =================================================

        predictions = []

        total_30_day_sales = 0

        critical_products = 0
        high_risk_products = 0
        fast_products = 0
        purchase_items = 0

        no_demand_products = 0
        dead_stock_products = 0


        # =================================================
        # ANALYZE EVERY PRODUCT
        # =================================================

        for product in products:

            pid = product["pid"]

            name = product["product_name"]

            stock = int(product["stock"] or 0)

            cost_price = float(
                product["cost_price"] or 0
            )

            selling_price = float(
                product["selling_price"] or 0
            )

            sold_qty = int(
                product["sold_qty"] or 0
            )

            last_sale = product["last_sale"]


            total_30_day_sales += sold_qty


            # =================================================
            # DAILY DEMAND
            # =================================================

            avg_daily_demand = sold_qty / 30


            # =================================================
            # DEMAND CLASSIFICATION
            # =================================================

            if sold_qty == 0:

                demand_level = "NO SALES"
                demand_class = "secondary"

                no_demand_products += 1

            elif sold_qty <= 3:

                demand_level = "LOW"
                demand_class = "info"

            elif sold_qty <= 15:

                demand_level = "MODERATE"
                demand_class = "warning"

            else:

                demand_level = "HIGH"
                demand_class = "success"

                fast_products += 1


            # =================================================
            # STOCK OUT CALCULATION
            # =================================================

            if avg_daily_demand > 0:

                days_until_stockout = (
                    stock / avg_daily_demand
                )

            else:

                days_until_stockout = None


            # =================================================
            # STOCK RISK
            # =================================================

            if stock <= 0:

                risk = "OUT OF STOCK"
                risk_class = "danger"

                critical_products += 1

            elif (
                days_until_stockout is not None
                and days_until_stockout <= 3
            ):

                risk = "CRITICAL"
                risk_class = "danger"

                critical_products += 1

            elif (
                days_until_stockout is not None
                and days_until_stockout <= 7
            ):

                risk = "HIGH"
                risk_class = "warning"

                high_risk_products += 1

            elif (
                days_until_stockout is not None
                and days_until_stockout <= 14
            ):

                risk = "MEDIUM"
                risk_class = "info"

            elif sold_qty == 0:

                risk = "NO DEMAND"
                risk_class = "secondary"

            else:

                risk = "HEALTHY"
                risk_class = "success"


            # =================================================
            # DEAD STOCK
            # =================================================

            dead_stock = False

            days_since_sale = None

            if last_sale:

                from datetime import datetime

                try:

                    if isinstance(last_sale, str):

                        last_sale_date = datetime.strptime(
                            last_sale[:19],
                            "%Y-%m-%d %H:%M:%S"
                        )

                    else:

                        last_sale_date = last_sale

                    days_since_sale = (
                        datetime.now() - last_sale_date
                    ).days

                    if days_since_sale >= 15:

                        dead_stock = True

                        dead_stock_products += 1

                except Exception:

                    pass

            else:

                # No sale in recent history
                dead_stock = True
                dead_stock_products += 1


            # =================================================
            # FORECAST
            # =================================================

            forecast_7_days = (
                avg_daily_demand * 7
            )

            forecast_30_days = (
                avg_daily_demand * 30
            )


            # =================================================
            # SMART PURCHASE RECOMMENDATION
            # =================================================

            if avg_daily_demand > 0:

                # 30 days expected demand
                expected_demand = (
                    avg_daily_demand * 30
                )

                # 10% safety stock
                safety_stock = (
                    expected_demand * 0.10
                )

                target_stock = (
                    expected_demand
                    + safety_stock
                )

                recommended_purchase = max(
                    0,
                    int(
                        round(
                            target_stock - stock
                        )
                    )
                )

            else:

                # No demand = don't blindly purchase
                recommended_purchase = 0


            if recommended_purchase > 0:

                purchase_items += 1


            # =================================================
            # FORECAST CONFIDENCE
            # =================================================

            if sold_qty == 0:

                forecast_confidence = "VERY LOW"

            elif sold_qty <= 3:

                forecast_confidence = "LOW"

            elif sold_qty <= 15:

                forecast_confidence = "MEDIUM"

            else:

                forecast_confidence = "HIGH"


            # =================================================
            # FAST / SLOW MOVEMENT
            # =================================================

            if sold_qty >= 30:

                movement = "FAST"

            elif sold_qty >= 10:

                movement = "MEDIUM"

            elif sold_qty > 0:

                movement = "SLOW"

            else:

                movement = "NO SALES"


            # =================================================
            # FORECAST REVENUE
            # =================================================

            forecast_revenue = (
                forecast_7_days
                * selling_price
            )


            # =================================================
            # APPEND RESULT
            # =================================================

            predictions.append({

                "pid": pid,

                "name": name,

                "stock": stock,

                "sold_qty": sold_qty,

                "avg_daily_demand": round(
                    avg_daily_demand,
                    2
                ),

                "days_until_stockout": (
                    round(
                        days_until_stockout,
                        1
                    )
                    if days_until_stockout
                    is not None
                    else None
                ),

                "risk": risk,

                "risk_class": risk_class,

                "demand_level": demand_level,

                "demand_class": demand_class,

                "movement": movement,

                "dead_stock": dead_stock,

                "days_since_sale": days_since_sale,

                "recommended_purchase":
                    recommended_purchase,

                "forecast_7_days":
                    round(
                        forecast_7_days,
                        1
                    ),

                "forecast_30_days":
                    round(
                        forecast_30_days,
                        1
                    ),

                "forecast_revenue":
                    round(
                        forecast_revenue,
                        2
                    ),

                "forecast_confidence":
                    forecast_confidence,

                "cost_price":
                    cost_price,

                "selling_price":
                    selling_price

            })


        # =================================================
        # OVERALL FORECAST
        # =================================================

        average_daily_sales = (
            total_30_day_sales / 30
        )

        forecast_7_day_sales = (
            average_daily_sales * 7
        )


        # =================================================
        # FAST MOVING PRODUCTS
        # =================================================

        fast_moving = sorted(
            predictions,
            key=lambda x: x["sold_qty"],
            reverse=True
        )[:5]


        # =================================================
        # PURCHASE ADVISOR
        # =================================================

        purchase_advisor = [

            p for p in predictions

            if p["recommended_purchase"] > 0

        ]


        purchase_advisor = sorted(

            purchase_advisor,

            key=lambda x: (
                x["recommended_purchase"],
                x["sold_qty"]
            ),

            reverse=True

        )[:10]


        # =================================================
        # DEAD STOCK
        # =================================================

        dead_stock_list = [

            p for p in predictions

            if p["dead_stock"]

        ]


        dead_stock_list = sorted(

            dead_stock_list,

            key=lambda x: x["sold_qty"]

        )[:10]


        # =================================================
        # AI BUSINESS INSIGHT
        # =================================================

        ai_insight = None

        try:

            critical_names = [

                p["name"]

                for p in predictions

                if p["risk"]
                in ["CRITICAL", "OUT OF STOCK"]

            ][:5]


            dead_names = [

                p["name"]

                for p in dead_stock_list

            ][:5]


            fast_names = [

                p["name"]

                for p in fast_moving

                if p["sold_qty"] > 0

            ]


            prompt = f"""

You are an AI Business Intelligence assistant
inside an Inventory Management System.

Analyze this REAL inventory data.

Total products:
{len(products)}

Sales in last 30 days:
{total_30_day_sales}

Predicted sales for next 7 days:
{round(forecast_7_day_sales, 1)}

Critical / out-of-stock products:
{", ".join(critical_names) if critical_names else "None"}

Dead / inactive products:
{", ".join(dead_names) if dead_names else "None"}

Fast-moving products:
{", ".join(fast_names) if fast_names else "None"}

Products with no recent demand:
{no_demand_products}

Products classified as dead stock:
{dead_stock_products}

Give the business owner a SHORT and useful insight.

Format:

1. Sales Situation:
2. Biggest Risk:
3. Recommended Action:

Rules:
- Be realistic.
- Do not invent sales.
- Do not claim high demand when sales are low.
- If data is insufficient, explicitly say confidence is low.
- Focus on actionable business decisions.
- Keep the response under 120 words.
"""


            ai_insight = ask_ai(prompt)


        except Exception as e:

            print(
                "AI Insight Error:",
                e
            )

            ai_insight = (
                "AI insight is temporarily "
                "unavailable. Please review "
                "the stock and demand indicators."
            )


        # =================================================
        # RENDER PAGE
        # =================================================

        return render_template(

            "prediction.html",

            predictions=predictions,

            critical_products=
                critical_products,

            high_risk_products=
                high_risk_products,

            fast_products=
                fast_products,

            purchase_items=
                purchase_items,

            no_demand_products=
                no_demand_products,

            dead_stock_products=
                dead_stock_products,

            total_products=
                len(products),

            total_30_day_sales=
                total_30_day_sales,

            forecast_7_day_sales=
                round(
                    forecast_7_day_sales,
                    1
                ),

            fast_moving=
                fast_moving,

            purchase_advisor=
                purchase_advisor,

            dead_stock_list=
                dead_stock_list,

            ai_insight=
                ai_insight
        )


    except Exception as e:

        print(
            "Prediction Error:",
            e
        )

        return f"""
        <h3>AI Prediction Error</h3>
        <p>{str(e)}</p>
        """


    finally:

        cursor.close()
        conn.close()

# =========================================================
# 🎯 WHAT-IF BUSINESS SIMULATOR
# =========================================================

@app.route("/api/simulate-business", methods=["POST"])
@login_required
def simulate_business():

    conn = getConnection()
    cursor = conn.cursor(dictionary=True)

    try:

        data = request.get_json() or {}

        # -------------------------------------------------
        # INPUTS
        # -------------------------------------------------

        product_id = int(
            data.get("product_id", 0)
        )

        demand_increase = float(
            data.get("demand_increase", 0)
        )

        additional_purchase = int(
            data.get("additional_purchase", 0)
        )


        # Prevent invalid values
        demand_increase = max(
            0,
            min(demand_increase, 500)
        )

        additional_purchase = max(
            0,
            additional_purchase
        )


        # -------------------------------------------------
        # GET PRODUCT
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                pid,
                product_name,
                stock,
                cost_price,
                selling_price
            FROM products
            WHERE pid = %s
        """, (product_id,))

        product = cursor.fetchone()


        if not product:

            return jsonify({
                "success": False,
                "message": "Product not found."
            }), 404


        # -------------------------------------------------
        # GET LAST 30 DAYS SALES
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COALESCE(SUM(quantity), 0) AS sold_qty
            FROM bill_items
            WHERE product_id = %s
            AND sale_date >= NOW() - INTERVAL 30 DAY
        """, (product_id,))

        sales = cursor.fetchone()

        sold_30_days = int(
            sales["sold_qty"] or 0
        )


        # -------------------------------------------------
        # CURRENT PRODUCT DATA
        # -------------------------------------------------

        current_stock = int(
            product["stock"] or 0
        )

        cost_price = float(
            product["cost_price"] or 0
        )

        selling_price = float(
            product["selling_price"] or 0
        )


        # -------------------------------------------------
        # CURRENT DAILY DEMAND
        # -------------------------------------------------

        current_daily_demand = (
            sold_30_days / 30
        )


        # -------------------------------------------------
        # PROJECTED DEMAND
        # -------------------------------------------------

        demand_multiplier = (
            1 + (demand_increase / 100)
        )

        projected_daily_demand = (
            current_daily_demand
            * demand_multiplier
        )


        projected_30_day_sales = (
            projected_daily_demand * 30
        )


        projected_7_day_sales = (
            projected_daily_demand * 7
        )


        # -------------------------------------------------
        # STOCK AFTER PURCHASE
        # -------------------------------------------------

        simulated_stock = (
            current_stock
            + additional_purchase
        )


        # -------------------------------------------------
        # STOCK AFTER 30 DAYS
        # -------------------------------------------------

        stock_after_30_days = (
            simulated_stock
            - projected_30_day_sales
        )


        # -------------------------------------------------
        # STOCK OUT DAYS
        # -------------------------------------------------

        if projected_daily_demand > 0:

            stock_coverage_days = (
                simulated_stock
                / projected_daily_demand
            )

        else:

            stock_coverage_days = None


        # -------------------------------------------------
        # REVENUE
        # -------------------------------------------------

        projected_revenue = (
            projected_30_day_sales
            * selling_price
        )


        # -------------------------------------------------
        # COST
        # -------------------------------------------------

        projected_cost = (
            projected_30_day_sales
            * cost_price
        )


        # -------------------------------------------------
        # PROFIT
        # -------------------------------------------------

        projected_profit = (
            projected_revenue
            - projected_cost
        )


        # -------------------------------------------------
        # CURRENT 30 DAY REVENUE
        # -------------------------------------------------

        current_revenue = (
            sold_30_days
            * selling_price
        )


        current_profit = (
            sold_30_days
            * (selling_price - cost_price)
        )


        # -------------------------------------------------
        # PROFIT CHANGE
        # -------------------------------------------------

        profit_change = (
            projected_profit
            - current_profit
        )


        # -------------------------------------------------
        # BUSINESS STATUS
        # -------------------------------------------------

        if stock_after_30_days < 0:

            stock_status = "STOCK OUT RISK"
            stock_status_class = "danger"

        elif (
            stock_coverage_days is not None
            and stock_coverage_days <= 7
        ):

            stock_status = "HIGH RISK"
            stock_status_class = "warning"

        elif (
            stock_coverage_days is not None
            and stock_coverage_days <= 14
        ):

            stock_status = "MEDIUM RISK"
            stock_status_class = "info"

        else:

            stock_status = "HEALTHY"
            stock_status_class = "success"


        # -------------------------------------------------
        # AI-STYLE RECOMMENDATION
        # -------------------------------------------------

        if stock_after_30_days < 0:

            recommendation = (
                "⚠️ Stock may run out within the "
                "simulation period. Consider increasing "
                "the purchase quantity."
            )

        elif profit_change > 0:

            recommendation = (
                "📈 This scenario increases the "
                "projected profit. The additional stock "
                "may be commercially worthwhile."
            )

        elif projected_30_day_sales == 0:

            recommendation = (
                "📉 There is currently no recorded demand "
                "for this product. Avoid purchasing extra "
                "stock until demand improves."
            )

        else:

            recommendation = (
                "🟢 The simulated inventory level appears "
                "reasonable for the projected demand."
            )


        # -------------------------------------------------
        # RETURN RESULT
        # -------------------------------------------------

        return jsonify({

            "success": True,

            "product_name":
                product["product_name"],

            "current_stock":
                current_stock,

            "additional_purchase":
                additional_purchase,

            "simulated_stock":
                simulated_stock,

            "current_30_day_sales":
                sold_30_days,

            "current_daily_demand":
                round(
                    current_daily_demand,
                    2
                ),

            "demand_increase":
                demand_increase,

            "projected_daily_demand":
                round(
                    projected_daily_demand,
                    2
                ),

            "projected_7_day_sales":
                round(
                    projected_7_day_sales,
                    1
                ),

            "projected_30_day_sales":
                round(
                    projected_30_day_sales,
                    1
                ),

            "stock_after_30_days":
                round(
                    stock_after_30_days,
                    1
                ),

            "stock_coverage_days":
                (
                    round(
                        stock_coverage_days,
                        1
                    )
                    if stock_coverage_days
                    is not None
                    else None
                ),

            "selling_price":
                selling_price,

            "cost_price":
                cost_price,

            "projected_revenue":
                round(
                    projected_revenue,
                    2
                ),

            "projected_cost":
                round(
                    projected_cost,
                    2
                ),

            "projected_profit":
                round(
                    projected_profit,
                    2
                ),

            "current_profit":
                round(
                    current_profit,
                    2
                ),

            "profit_change":
                round(
                    profit_change,
                    2
                ),

            "stock_status":
                stock_status,

            "stock_status_class":
                stock_status_class,

            "recommendation":
                recommendation
        })


    except Exception as e:

        print(
            "Business Simulator Error:",
            e
        )

        return jsonify({

            "success": False,

            "message":
                str(e)

        }), 500


    finally:

        cursor.close()
        conn.close()        

# =========================================================
# 🔍 AI PRODUCT EXPLANATION
# =========================================================

@app.route("/api/product-explanation", methods=["POST"])
@login_required
def product_explanation():

    conn = None
    cursor = None

    try:

        # -------------------------------------------------
        # DATABASE CONNECTION
        # -------------------------------------------------

        conn = getConnection()
        cursor = conn.cursor(dictionary=True)

        uid = session["uid"]

        data = request.get_json(silent=True) or {}

        product_id = data.get("product_id")

        if not product_id:
            return jsonify({
                "success": False,
                "message": "Product ID is missing."
            }), 400

        try:
            product_id = int(product_id)
        except:
            return jsonify({
                "success": False,
                "message": "Invalid Product ID."
            }), 400


        # -------------------------------------------------
        # GET PRODUCT
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                pid,
                product_name,
                stock,
                cost_price,
                selling_price
            FROM products
            WHERE pid=%s
            AND uid=%s
        """, (
            product_id,
            uid
        ))

        product = cursor.fetchone()

        if not product:

            return jsonify({
                "success": False,
                "message": "Product not found."
            }), 404


        # -------------------------------------------------
        # LAST 30 DAYS SALES
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COALESCE(SUM(quantity), 0) AS sold_qty,
                MAX(sale_date) AS last_sale
            FROM bill_items
            WHERE product_id=%s
            AND sale_date >= NOW() - INTERVAL 30 DAY
        """, (
            product_id,
        ))

        sales = cursor.fetchone()


        sold_qty = int(
            sales["sold_qty"] or 0
        )

        last_sale = sales["last_sale"]


        # -------------------------------------------------
        # CURRENT STOCK
        # -------------------------------------------------

        stock = int(
            product["stock"] or 0
        )


        # -------------------------------------------------
        # DAILY DEMAND
        # -------------------------------------------------

        avg_daily_demand = (
            sold_qty / 30
        )


        # -------------------------------------------------
        # STOCK COVERAGE
        # -------------------------------------------------

        if avg_daily_demand > 0:

            days_left = (
                stock / avg_daily_demand
            )

        else:

            days_left = None


        # -------------------------------------------------
        # DEMAND LEVEL
        # -------------------------------------------------

        if sold_qty == 0:

            demand_level = "NO SALES"

        elif sold_qty <= 3:

            demand_level = "LOW"

        elif sold_qty <= 10:

            demand_level = "MODERATE"

        else:

            demand_level = "HIGH"


        # -------------------------------------------------
        # RISK
        # -------------------------------------------------

        if stock <= 0:

            risk = "OUT OF STOCK"

        elif days_left is not None and days_left <= 7:

            risk = "CRITICAL"

        elif days_left is not None and days_left <= 15:

            risk = "HIGH"

        elif days_left is not None and days_left <= 30:

            risk = "MEDIUM"

        elif sold_qty == 0:

            risk = "NO DEMAND"

        else:

            risk = "HEALTHY"


        # -------------------------------------------------
        # AI CONFIDENCE
        # -------------------------------------------------

        if sold_qty == 0:

            confidence = "VERY LOW"

        elif sold_qty <= 3:

            confidence = "LOW"

        elif sold_qty <= 10:

            confidence = "MEDIUM"

        else:

            confidence = "HIGH"


        # -------------------------------------------------
        # REASONS
        # -------------------------------------------------

        reasons = []


        if stock <= 0:

            reasons.append(
                "❌ Current stock is zero or below."
            )

        elif days_left is not None and days_left <= 7:

            reasons.append(
                f"⚠️ Current stock may last only about {round(days_left, 1)} days."
            )

        elif days_left is not None and days_left <= 15:

            reasons.append(
                f"⚠️ Stock coverage is around {round(days_left, 1)} days."
            )

        elif days_left is not None:

            reasons.append(
                f"📦 Current stock can cover approximately {round(days_left, 1)} days of demand."
            )


        if sold_qty == 0:

            reasons.append(
                "📉 No sales were recorded for this product during the last 30 days."
            )

        elif sold_qty <= 3:

            reasons.append(
                f"📊 Only {sold_qty} unit(s) were sold during the last 30 days."
            )

        else:

            reasons.append(
                f"📈 {sold_qty} unit(s) were sold during the last 30 days."
            )


        if last_sale:

            reasons.append(
                f"🛒 Last recorded sale: {last_sale}"
            )

        else:

            reasons.append(
                "🛒 No recent sale was found."
            )


        # -------------------------------------------------
        # RECOMMENDATION
        # -------------------------------------------------

        if stock <= 0:

            recommendation = (
                "🚨 Restock this product immediately "
                "if customer demand continues."
            )

        elif sold_qty == 0:

            recommendation = (
                "📉 Avoid purchasing additional stock "
                "until demand improves. Consider a discount "
                "or promotional offer."
            )

        elif days_left is not None and days_left <= 7:

            recommendation = (
                "⚠️ Consider restocking soon because "
                "current inventory may run out quickly."
            )

        elif days_left is not None and days_left <= 15:

            recommendation = (
                "🟡 Monitor this product closely and "
                "plan a purchase if demand continues."
            )

        else:

            recommendation = (
                "🟢 Current inventory appears healthy "
                "for the recent demand level."
            )


        # -------------------------------------------------
        # AI SUMMARY
        # -------------------------------------------------

        ai_summary = (
            f"{product['product_name']} currently has "
            f"{stock} unit(s) in stock. "
            f"During the last 30 days, {sold_qty} unit(s) "
            f"were sold. "
            f"Demand is classified as {demand_level.lower()} "
            f"and the current inventory risk is {risk.lower()}. "
            f"{recommendation}"
        )


        # -------------------------------------------------
        # RETURN
        # -------------------------------------------------

        return jsonify({

            "success": True,

            "product_name":
                product["product_name"],

            "stock":
                stock,

            "sold_qty":
                sold_qty,

            "avg_daily_demand":
                round(
                    avg_daily_demand,
                    2
                ),

            "days_left":
                (
                    round(
                        days_left,
                        1
                    )
                    if days_left is not None
                    else None
                ),

            "demand_level":
                demand_level,

            "risk":
                risk,

            "confidence":
                confidence,

            "reasons":
                reasons,

            "recommendation":
                recommendation,

            "ai_summary":
                ai_summary

        })


    except Exception as e:

        print(
            "=========================================="
        )

        print(
            "AI PRODUCT EXPLANATION ERROR:"
        )

        print(e)

        print(
            "=========================================="
        )

        return jsonify({

            "success": False,

            "message":
                "AI Product Explanation Error: "
                + str(e)

        }), 500


    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()

            
# ==========================
# PRODUCT PAGE
# ==========================
@app.route('/products')
@login_required
def products():
    return render_template('products.html')


# ==========================
# ADD PRODUCT
# ==========================
@app.route('/addProduct', methods=['POST'])
@login_required
def addProduct():

    product_name = request.form['product_name']
    category = request.form['category']
    cost_price = request.form['cost_price']
    selling_price = request.form['selling_price']
    stock = request.form['stock']

    conn = getConnection()
    cursor = conn.cursor()

    sql = """
    INSERT INTO products
        (
        uid,
        product_name,
        category,
        cost_price,
        selling_price,
        stock
        )
        VALUES
        (
        %s,%s,%s,%s,%s,%s
        )
    """

    cursor.execute(
        sql,
        (
        session["uid"],
        product_name,
        category,
        cost_price,
        selling_price,
        stock
        )
        )

    conn.commit()

    cursor.close()
    conn.close()

    return "Product Added Successfully"

# ==========================
# ANDROID API AUTH HELPERS
# ==========================
# The website continues to use its existing Flask session. Android uses a
# signed, time-limited bearer token so mobile API calls can identify the user.
_ANDROID_TOKEN_SALT = "android-api-v1"
_ANDROID_TOKEN_MAX_AGE = 24 * 60 * 60  # 24 hours

def create_android_token(user_id):
    serializer = URLSafeTimedSerializer(app.secret_key, salt=_ANDROID_TOKEN_SALT)
    return serializer.dumps({"uid": user_id})

def get_android_user_id():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    serializer = URLSafeTimedSerializer(app.secret_key, salt=_ANDROID_TOKEN_SALT)
    try:
        payload = serializer.loads(token, max_age=_ANDROID_TOKEN_MAX_AGE)
        return payload.get("uid")
    except (BadSignature, SignatureExpired, TypeError, AttributeError):
        return None

# ==========================
# ANDROID: VIEW PRODUCTS API
# ==========================
@app.route('/api/products', methods=['GET'])
def android_get_products():
    uid = get_android_user_id()
    if uid is None:
        return jsonify({"success": False, "message": "Authentication required. Please log in again."}), 401

    conn = None
    cursor = None
    try:
        conn = getConnection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pid, product_name, category, cost_price, selling_price, stock
            FROM products
            WHERE uid = %s
            ORDER BY pid DESC
        """, (uid,))
        rows = cursor.fetchall()
        products_list = []
        for row in rows:
            products_list.append({
                "pid": row[0],
                "product_name": row[1],
                "category": row[2],
                "cost_price": float(row[3] or 0),
                "selling_price": float(row[4] or 0),
                "stock": int(row[5] or 0)
            })
        return jsonify({"success": True, "products": products_list}), 200
    except Exception:
        app.logger.exception("Android products API error")
        return jsonify({"success": False, "message": "Unable to load products"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==========================
# ANDROID: ADD PRODUCT API
# ==========================
@app.route('/api/products/add', methods=['POST'])
def android_add_product():
    uid = get_android_user_id()
    if uid is None:
        return jsonify({"success": False, "message": "Authentication required. Please log in again."}), 401

    conn = None
    cursor = None
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "Invalid request data"}), 400

        product_name = str(data.get("product_name", "")).strip()
        category = str(data.get("category", "")).strip()
        if not product_name or not category:
            return jsonify({"success": False, "message": "Product name and category are required"}), 400

        try:
            cost_price = float(data.get("cost_price"))
            selling_price = float(data.get("selling_price"))
            stock_value = float(data.get("stock"))
            if not stock_value.is_integer():
                raise ValueError("Stock must be a whole number")
            stock = int(stock_value)
        except (TypeError, ValueError, OverflowError):
            return jsonify({"success": False, "message": "Enter valid prices and whole-number stock"}), 400

        if not all(map(lambda value: value == value and abs(value) != float('inf'), (cost_price, selling_price))):
            return jsonify({"success": False, "message": "Enter valid finite prices"}), 400
        if cost_price < 0 or selling_price < 0 or stock < 0:
            return jsonify({"success": False, "message": "Prices and stock cannot be negative"}), 400

        conn = getConnection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products
                (uid, product_name, category, cost_price, selling_price, stock)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (uid, product_name, category, cost_price, selling_price, stock))
        conn.commit()
        return jsonify({"success": True, "message": "Product added successfully", "pid": cursor.lastrowid}), 201
    except Exception:
        app.logger.exception("Android add product API error")
        if conn:
            conn.rollback()
        return jsonify({"success": False, "message": "Unable to add product"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# =========================================================
# 🤖 AI SMART PURCHASE PLANNER
# =========================================================

@app.route("/api/smart-purchase-plan", methods=["GET"])
@login_required
def smart_purchase_plan():

    conn = None
    cursor = None

    try:

        conn = getConnection()
        cursor = conn.cursor(dictionary=True)

        uid = session["uid"]

        # =================================================
        # GET USER PRODUCTS + LAST 30 DAYS SALES
        # =================================================

        cursor.execute("""
            SELECT
                p.pid,
                p.product_name,
                p.stock,
                p.cost_price,
                p.selling_price,

                COALESCE(s.sold_qty, 0) AS sold_qty

            FROM products p

            LEFT JOIN (

                SELECT
                    product_id,
                    SUM(quantity) AS sold_qty

                FROM bill_items

                WHERE uid=%s
                AND sale_date >= NOW() - INTERVAL 30 DAY

                GROUP BY product_id

            ) s

            ON p.pid = s.product_id

            WHERE p.uid=%s

            ORDER BY p.product_name

        """, (
            uid,
            uid
        ))

        products = cursor.fetchall()


        # =================================================
        # PLAN CATEGORIES
        # =================================================

        buy_now = []
        consider_buying = []
        do_not_buy = []


        total_investment = 0
        expected_revenue = 0
        expected_profit = 0


        # =================================================
        # ANALYZE PRODUCTS
        # =================================================

        for product in products:

            pid = product["pid"]

            name = product["product_name"]

            stock = int(
                product["stock"] or 0
            )

            cost_price = float(
                product["cost_price"] or 0
            )

            selling_price = float(
                product["selling_price"] or 0
            )

            sold_qty = int(
                product["sold_qty"] or 0
            )


            # -------------------------------------------------
            # DAILY DEMAND
            # -------------------------------------------------

            daily_demand = sold_qty / 30


            # -------------------------------------------------
            # NO DEMAND
            # -------------------------------------------------

            if sold_qty == 0:

                do_not_buy.append({

                    "pid": pid,

                    "name": name,

                    "stock": stock,

                    "recommended_qty": 0,

                    "reason":
                        "No sales in the last 30 days."

                })

                continue


            # -------------------------------------------------
            # STOCK COVERAGE
            # -------------------------------------------------

            if daily_demand > 0:

                stock_coverage = (
                    stock / daily_demand
                )

            else:

                stock_coverage = 9999


            # -------------------------------------------------
            # TARGET STOCK
            # -------------------------------------------------

            # 30 days expected demand
            expected_demand = (
                daily_demand * 30
            )

            # 10% safety stock
            safety_stock = (
                expected_demand * 0.10
            )

            target_stock = (
                expected_demand
                + safety_stock
            )


            # -------------------------------------------------
            # RECOMMENDED PURCHASE
            # -------------------------------------------------

            recommended_qty = max(
                0,
                int(
                    round(
                        target_stock - stock
                    )
                )
            )


            # -------------------------------------------------
            # BUY NOW
            # -------------------------------------------------

            if stock <= 0:

                recommended_qty = max(
                    recommended_qty,
                    int(
                        max(
                            1,
                            round(
                                expected_demand
                            )
                        )
                    )
                )

                reason = (
                    "Product is out of stock "
                    "but has recent demand."
                )

                buy_now.append({

                    "pid": pid,
                    "name": name,
                    "stock": stock,
                    "sold_qty": sold_qty,
                    "recommended_qty": recommended_qty,
                    "reason": reason

                })


            elif stock_coverage <= 7:

                recommended_qty = max(
                    recommended_qty,
                    int(
                        max(
                            1,
                            round(
                                expected_demand
                            )
                        )
                    )

                )

                reason = (
                    f"Current stock may last only "
                    f"{round(stock_coverage, 1)} days."
                )

                buy_now.append({

                    "pid": pid,
                    "name": name,
                    "stock": stock,
                    "sold_qty": sold_qty,
                    "recommended_qty": recommended_qty,
                    "reason": reason

                })


            # -------------------------------------------------
            # CONSIDER BUYING
            # -------------------------------------------------

            elif (
                stock_coverage <= 30
                and recommended_qty > 0
            ):

                reason = (
                    f"Moderate demand with approximately "
                    f"{round(stock_coverage, 1)} days "
                    f"of stock coverage."
                )

                consider_buying.append({

                    "pid": pid,
                    "name": name,
                    "stock": stock,
                    "sold_qty": sold_qty,
                    "recommended_qty": recommended_qty,
                    "reason": reason

                })


            # -------------------------------------------------
            # HEALTHY STOCK
            # -------------------------------------------------

            else:

                do_not_buy.append({

                    "pid": pid,
                    "name": name,
                    "stock": stock,
                    "recommended_qty": 0,
                    "reason":
                        "Current stock is sufficient "
                        "for recent demand."

                })


            # -------------------------------------------------
            # FINANCIAL CALCULATION
            # -------------------------------------------------

            if recommended_qty > 0:

                investment = (
                    recommended_qty
                    * cost_price
                )

                revenue = (
                    recommended_qty
                    * selling_price
                )

                profit = (
                    revenue
                    - investment
                )

                total_investment += investment

                expected_revenue += revenue

                expected_profit += profit


        # =================================================
        # SORT
        # =================================================

        buy_now = sorted(

            buy_now,

            key=lambda x: (
                x["recommended_qty"],
                x["sold_qty"]
            ),

            reverse=True

        )[:10]


        consider_buying = sorted(

            consider_buying,

            key=lambda x: (
                x["recommended_qty"],
                x["sold_qty"]
            ),

            reverse=True

        )[:10]


        do_not_buy = sorted(

            do_not_buy,

            key=lambda x: x["stock"]

        )[:10]


        # =================================================
        # AI BUSINESS DECISION
        # =================================================

        ai_summary = ""

        try:

            buy_names = ", ".join(
                item["name"]
                for item in buy_now
            )

            consider_names = ", ".join(
                item["name"]
                for item in consider_buying
            )

            avoid_names = ", ".join(
                item["name"]
                for item in do_not_buy
            )


            prompt = f"""
You are an AI inventory purchasing advisor.

Analyze this REAL inventory data.

BUY NOW:
{buy_names if buy_names else "None"}

CONSIDER BUYING:
{consider_names if consider_names else "None"}

DO NOT BUY:
{avoid_names if avoid_names else "None"}

Estimated investment:
₹{round(total_investment, 2)}

Expected revenue:
₹{round(expected_revenue, 2)}

Expected profit:
₹{round(expected_profit, 2)}

Give a short business recommendation.

Rules:
- Do not invent products.
- Do not invent sales.
- Do not recommend buying products with no demand.
- Focus on cash flow and inventory risk.
- Maximum 80 words.

Format:

Priority:
Action:
Reason:
"""

            ai_summary = ask_ai(prompt)


        except Exception as e:

            print(
                "Smart Purchase AI Error:",
                e
            )

            if buy_now:

                ai_summary = (
                    "Prioritize products with "
                    "low stock coverage and "
                    "recent demand. Avoid purchasing "
                    "products with no recent sales."
                )

            else:

                ai_summary = (
                    "Current inventory does not "
                    "require urgent purchasing."
                )


        # =================================================
        # RESPONSE
        # =================================================

        return jsonify({

            "success": True,

            "buy_now":
                buy_now,

            "consider_buying":
                consider_buying,

            "do_not_buy":
                do_not_buy,

            "total_investment":
                round(
                    total_investment,
                    2
                ),

            "expected_revenue":
                round(
                    expected_revenue,
                    2
                ),

            "expected_profit":
                round(
                    expected_profit,
                    2
                ),

            "ai_summary":
                ai_summary

        })


    except Exception as e:

        print(
            "Smart Purchase Planner Error:",
            e
        )

        return jsonify({

            "success": False,

            "message":
                str(e)

        }), 500


    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()

# ==========================
#  PRODUCT LIST
# ==========================

@app.route('/productList')
@login_required
def productList():

    conn = getConnection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM products
        WHERE uid=%s
        """,
        (session["uid"],)
    )

    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'productList.html',
        products=products
    )

# ==========================
# DELETE PRODUCT
# ==========================

@app.route('/deleteProduct/<int:id>')
@login_required
def deleteProduct(id):

    conn = getConnection()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM products
        WHERE pid=%s
        AND uid=%s
        """,
        (
            id,
            session["uid"]
        )
    )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect('/productList')


# ==========================
# EDIT PRODUCT
# ==========================

@app.route('/editProduct/<int:id>')
@login_required
def editProduct(id):

    conn = getConnection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM products
        WHERE pid=%s
        AND uid=%s
        """,
        (
            id,
            session["uid"]
        )
    )

    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if product is None:
        return "Product Not Found"

    return render_template(
        'editProduct.html',
        product=product
    )


# ==========================
# UPDATE PRODUCT
# ==========================

@app.route('/updateProduct', methods=['POST'])
@login_required
def updateProduct():

    pid = request.form['pid']
    product_name = request.form['product_name']
    category = request.form['category']
    cost_price = request.form['cost_price']
    selling_price = request.form['selling_price']
    stock = request.form['stock']

    conn = getConnection()
    cursor = conn.cursor()

    sql = """
    UPDATE products
    SET
        product_name=%s,
        category=%s,
        cost_price=%s,
        selling_price=%s,
        stock=%s
    WHERE
        pid=%s
        AND uid=%s
    """

    cursor.execute(
        sql,
        (
            product_name,
            category,
            cost_price,
            selling_price,
            stock,
            pid,
            session["uid"]
        )
    )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect('/productList')


# ==========================
# BILLING PAGE
# ==========================

@app.route('/billing')
@login_required
def billing():

    conn = getConnection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM products
        WHERE uid=%s
        ORDER BY product_name
        """,
        (session["uid"],)
    )

    products = cursor.fetchall()

    cursor.close()
    conn.close()

    billing_settings = get_user_settings(session["uid"])

    return render_template(
        "billing.html",
        products=products,
        gst_rate=float(billing_settings.get("gst_rate", 18) or 0)
    )

# ==========================
# GENERATE BILL
# ==========================

@app.route('/generateBill', methods=['POST'])
@login_required
def generateBill():

    from datetime import datetime

    # ==========================
    # CUSTOMER DETAILS
    # ==========================

    customer_name = request.form["customer_name"]
    customer_phone = request.form["customer_phone"]
    customer_address = request.form["customer_address"]
    customer_gst = request.form["customer_gst"]
    payment_method = request.form["payment_method"]

    try:
        discount = max(float(request.form.get("discount", 0) or 0), 0)
    except (TypeError, ValueError):
        return "Discount must be a valid number.", 400

    billing_settings = get_user_settings(session["uid"])
    try:
        gst_percentage = float(request.form.get(
            "gst_percentage", billing_settings.get("gst_rate", 18)
        ))
    except (TypeError, ValueError):
        return "GST rate must be a valid number.", 400
    if not 0 <= gst_percentage <= 100:
        return "GST rate must be between 0 and 100.", 400

    product_ids = request.form.getlist("product_id[]")
    quantities = request.form.getlist("quantity[]")

    conn = getConnection()
    cursor = conn.cursor()

    # ==========================
    # BUSINESS DETAILS
    # ==========================

    cursor.execute("""
    SELECT
        business_name,
        gst_number,
        fssai_number,
        phone,
        address,
        city,
        state,
        pincode,
        invoice_prefix
    FROM users
    WHERE email=%s
    """,(session["user"],))

    business = cursor.fetchone()

    business_name = business[0]
    gst_number = business[1]
    fssai_number = business[2]
    business_phone = business[3]
    business_address = business[4]
    business_city = business[5]
    business_state = business[6]
    business_pincode = business[7]
    invoice_prefix = business[8]
    bill_settings = get_user_settings(session["uid"])
    show_fssai_on_bill = bool(
    bill_settings.get("show_fssai_on_bill", 1)
)
    # ==========================
    # BILL VARIABLES
    # ==========================

    invoice_items = []

    subtotal = 0

    # ==========================
    # READ ALL PRODUCTS
    # ==========================

    for i in range(len(product_ids)):

        pid = product_ids[i]

        qty = int(quantities[i])

        cursor.execute("""
        SELECT *
        FROM products
        WHERE pid=%s
        """,(pid,))

        product = cursor.fetchone()

        if product is None:

            continue

        product_name = product[1]

        selling_price = float(product[4])

        stock = int(product[5])

        if qty > stock:

            cursor.close()

            conn.close()

            return f"Insufficient Stock : {product_name}"

        item_total = selling_price * qty

        subtotal += item_total

        invoice_items.append({

            "pid":pid,

            "name":product_name,

            "qty":qty,

            "price":selling_price,

            "stock":stock,

            "total":item_total

        })

    # ==========================
    # GST CALCULATION
    # ==========================

    taxable_amount = max(subtotal - discount, 0)
    gst_amount = taxable_amount * gst_percentage / 100

    cgst = gst_amount / 2

    sgst = gst_amount / 2

    grand_total = taxable_amount + gst_amount


    # ==========================
    # NEXT INVOICE NUMBER
    # ==========================

    cursor.execute("""
    SELECT IFNULL(MAX(invoice_no),0)+1
    FROM bills
    WHERE uid=%s
    """,
    (
        session["uid"],
    ))

    invoice_no = cursor.fetchone()[0]

    # ==========================
    # SAVE BILL
    # ==========================

    cursor.execute("""
  INSERT INTO bills
    (
    uid,
    invoice_no,
    customer_name,
    customer_phone,
    customer_address,
    customer_gst,
    payment_method,
    subtotal,
    cgst,
    sgst,
    discount,
    grand_total,
    total_amount
    )
    VALUES
    (
    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
    )
    """,
    (
    session["uid"],
    invoice_no,
    customer_name,
    customer_phone,
    customer_address,
    customer_gst,
    payment_method,
    subtotal,
    cgst,
    sgst,
    discount,
    grand_total,
    grand_total
    ))
    conn.commit()

    bill_id = cursor.lastrowid

        # ==========================
    # SAVE ALL BILL ITEMS
    # ==========================

    for item in invoice_items:

        item_gst = (item["total"] * gst_percentage) / 100

        cursor.execute("""
        INSERT INTO bill_items
        (
            uid,
            bill_id,
            product_id,
            product_name,
            quantity,
            price,
            gst_percentage,
            gst_amount,
            total_amount,
            sale_date
        )
        VALUES
        (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()
        )
        """,
        (
            session["uid"],
            bill_id,
            item["pid"],
            item["name"],
            item["qty"],
            item["price"],
            gst_percentage,
            item_gst,
            item["total"] + item_gst
        ))

        # ==========================
        # UPDATE STOCK
        # ==========================

        new_stock = item["stock"] - item["qty"]

        cursor.execute("""
        UPDATE products
        SET stock=%s
        WHERE pid=%s
        AND uid=%s
        """,
        (
            new_stock,
            item["pid"],
            session["uid"]
        ))

    conn.commit()

    # ==========================
    # CLOSE CONNECTION
    # ==========================

    cursor.close()

    conn.close()

    # ==========================
    # SHOW INVOICE
    # ==========================

    return render_template(

        "invoice.html",

        bill_id=bill_id,

        invoice_prefix=invoice_prefix,

        date=datetime.now().strftime("%d-%m-%Y"),

        business_name=business_name,

        gst_number=gst_number,

        fssai_number=fssai_number,
        show_fssai_on_bill=show_fssai_on_bill,

        phone=business_phone,

        address=business_address,

        city=business_city,

        state=business_state,

        pincode=business_pincode,

        customer_name=customer_name,

        customer_phone=customer_phone,

        customer_address=customer_address,

        customer_gst=customer_gst,

        payment_method=payment_method,

        invoice_items=invoice_items,

        subtotal=subtotal,

        gst_percentage=gst_percentage,

        gst_half_percentage=gst_percentage / 2,

        gst_amount=gst_amount,

        cgst=cgst,

        sgst=sgst,

        discount=discount,

        grand_total=grand_total
    )

# ==========================
# SALES HISTORY
# ==========================

@app.route('/salesHistory')
@login_required
def salesHistory():

    period = request.args.get("period", "today")

    if period == "today":

        condition = "DATE(bill_date)=CURDATE()"
        title = "Today's"

    elif period == "7days":

        condition = "bill_date >= NOW() - INTERVAL 7 DAY"
        title = "Last 7 Days"

    elif period == "30days":

        condition = "bill_date >= NOW() - INTERVAL 30 DAY"
        title = "Last 30 Days"

    elif period == "6months":

        condition = "bill_date >= NOW() - INTERVAL 6 MONTH"
        title = "Last 6 Months"

    elif period == "year":

        condition = "YEAR(bill_date)=YEAR(CURDATE())"
        title = "This Year"

    else:

        condition = "1=1"
        title = "Lifetime"

    conn = getConnection()
    cursor = conn.cursor()

    # ==========================
    # USER INVOICE PREFIX
    # ==========================

    cursor.execute("""
    SELECT invoice_prefix
    FROM users
    WHERE id=%s
    """,
    (
        session["uid"],
    ))

    row = cursor.fetchone()

    if row:
        invoice_prefix = row[0]
    else:
        invoice_prefix = "INV"

    # ==========================
    # TOTAL REVENUE
    # ==========================

    cursor.execute(f"""
    SELECT IFNULL(SUM(total_amount),0)
    FROM bills
    WHERE uid=%s
    AND {condition}
    """,
    (
        session["uid"],
    ))

    total_revenue = cursor.fetchone()[0]

    # ==========================
    # TOTAL CUSTOMERS
    # ==========================

    cursor.execute(f"""
    SELECT COUNT(DISTINCT customer_phone)
    FROM bills
    WHERE uid=%s
    AND {condition}
    """,
    (
        session["uid"],
    ))

    total_customers = cursor.fetchone()[0]

    # ==========================
    # TOTAL BILLS
    # ==========================

    cursor.execute(f"""
    SELECT COUNT(*)
    FROM bills
    WHERE uid=%s
    AND {condition}
    """,
    (
        session["uid"],
    ))

    total_bills = cursor.fetchone()[0]

    # ==========================
    # BILL LIST
    # ==========================

    cursor.execute(f"""
    SELECT *
    FROM bills
    WHERE uid=%s
    AND {condition}
    ORDER BY invoice_no DESC
    """,
    (
        session["uid"],
    ))

    bills = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(

        "salesHistory.html",

        bills=bills,

        invoice_prefix=invoice_prefix,

        total_revenue=total_revenue,

        total_customers=total_customers,

        total_bills=total_bills,

        dashboard_title=title,

        selected_period=period

    )
# ==========================
# INVOICE PDF
# ==========================

@app.route('/downloadInvoice/<int:bill_id>')
@login_required
def downloadInvoice(bill_id):

    conn = getConnection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT *
    FROM bills
    WHERE bill_id=%s
    AND uid=%s
    """,
    (
        bill_id,
        session["uid"]
    ))

    bill = cursor.fetchone()

    if bill is None:

        cursor.close()
        conn.close()

        return "Invoice Not Found"

    cursor.close()
    conn.close()

    # Include FSSAI only when the account has enabled it in Billing Settings.
    settings_conn = getConnection()
    settings_cursor = settings_conn.cursor(dictionary=True)
    try:
        ensure_user_settings_table(settings_cursor)
        settings_cursor.execute("SELECT fssai_number FROM users WHERE id=%s", (session["uid"],))
        business_info = settings_cursor.fetchone() or {}
        bill_settings = get_user_settings(session["uid"], settings_cursor)
        fssai_number = business_info.get("fssai_number", "") if bill_settings.get("show_fssai_on_bill", 1) else ""
    finally:
        settings_cursor.close()
        settings_conn.close()

    pdf_file = f"invoice_{bill_id}.pdf"

    c = canvas.Canvas(pdf_file)

    c.setFont("Helvetica-Bold",18)
    c.drawString(210,800,"INVOICE")

    c.setFont("Helvetica",12)

    c.drawString(50,760,f"Invoice No : {bill[0]}")
    if fssai_number:
        c.drawString(50,785,f"FSSAI License No : {fssai_number}")
    c.drawString(50,735,f"Customer : {bill[2]}")
    c.drawString(50,710,f"Grand Total : Rs.{bill[10]}")
    c.drawString(50,685,f"Payment : {bill[6]}")

    c.save()

    return send_file(
        pdf_file,
        as_attachment=True
    )

# ==========================
# DEAD STOCK
# ==========================

@app.route('/deadStock')
@login_required
def deadStock():

    conn = getConnection()
    cursor = conn.cursor()

    dead_settings = get_user_settings(session["uid"])
    dead_days_threshold = int(dead_settings.get("dead_stock_days", 15))
    cursor.execute("""
    SELECT p.pid, p.product_name, MAX(bi.sale_date)
    FROM products p
    LEFT JOIN bill_items bi ON p.pid=bi.product_id AND bi.uid=%s
    WHERE p.uid=%s
    GROUP BY p.pid, p.product_name
    """, (session["uid"], session["uid"]))

    products = cursor.fetchall()

    dead_products = []

    from datetime import datetime

    for product in products:

        pid = product[0]

        name = product[1]

        last_sale = product[2]

        if last_sale is None:

            dead_products.append(
                (
                    pid,
                    name,
                    "Never Sold",
                    "Dead Stock",
                    "Promote Product"
                )
            )

        else:

            days = (
                datetime.now() -
                last_sale
            ).days

            if days >= dead_days_threshold:

                dead_products.append(
                    (
                        pid,
                        name,
                        f"{days} Days Ago",
                        "Dead Stock",
                        "Offer Discount"
                    )
                )

    cursor.close()
    conn.close()

    return render_template(
        "deadStock.html",
        dead_products=dead_products
    )

# ==========================
# REPORTS
# ==========================

@app.route('/reports')
@login_required
def reports():

    return render_template("reports.html")

@app.route('/generateReport', methods=['POST'])
@login_required
def generateReport():

    report_type = request.form['report_type']

    conn = getConnection()
    cursor = conn.cursor()

    if report_type == "today":
        condition = "DATE(b.bill_date)=CURDATE()"

    elif report_type == "7days":
        condition = "b.bill_date >= NOW() - INTERVAL 7 DAY"

    elif report_type == "30days":
        condition = "b.bill_date >= NOW() - INTERVAL 30 DAY"

    elif report_type == "6months":
        condition = "b.bill_date >= NOW() - INTERVAL 6 MONTH"

    else:
        condition = "1=1"

    # ==========================
    # TOTAL SALES
    # ==========================

    cursor.execute(f"""
    SELECT IFNULL(SUM(total_amount),0)
    FROM bills b
    WHERE b.uid=%s
    AND {condition}
    """,
    (
        session["uid"],
    ))

    total_sales = cursor.fetchone()[0]

    # ==========================
    # TOTAL BILLS
    # ==========================

    cursor.execute(f"""
    SELECT COUNT(*)
    FROM bills b
    WHERE b.uid=%s
    AND {condition}
    """,
    (
        session["uid"],
    ))

    total_bills = cursor.fetchone()[0]

    # ==========================
    # AVERAGE BILL
    # ==========================

    average_bill = 0

    if total_bills > 0:

        average_bill = round(
            total_sales / total_bills,
            2
        )

    # ==========================
    # TOTAL PROFIT
    # ==========================

    cursor.execute(f"""
    SELECT IFNULL(
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
        AND {condition}
    """,
    (
        session["uid"],
        session["uid"],
        session["uid"]
    ))

    total_profit = cursor.fetchone()[0]

    # ==========================
    # TOP SELLING PRODUCT
    # ==========================

    cursor.execute(f"""
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

        AND {condition}

    GROUP BY p.product_name

    ORDER BY qty DESC

    LIMIT 1
    """,
    (
        session["uid"],
        session["uid"],
        session["uid"]
    ))

    top_product = cursor.fetchone()

    if top_product:

        top_product = top_product[0]

    else:

        top_product = "No Data"

    cursor.close()
    conn.close()

    return render_template(

        "reportResult.html",

        report_type=report_type,

        total_sales=total_sales,

        total_profit=total_profit,

        total_bills=total_bills,

        average_bill=average_bill,

        top_product=top_product

    )

@app.route('/generateCustomReport', methods=['POST'])
@login_required
def generateCustomReport():

    from_date = request.form['from_date']
    to_date = request.form['to_date']

    conn = getConnection()
    cursor = conn.cursor()

    # ==========================
    # TOTAL SALES
    # ==========================

    cursor.execute("""
    SELECT IFNULL(SUM(total_amount),0)
    FROM bills
    WHERE uid=%s
    AND DATE(bill_date)
    BETWEEN %s AND %s
    """,
    (
        session["uid"],
        from_date,
        to_date
    ))

    total_sales = cursor.fetchone()[0]

    # ==========================
    # TOTAL BILLS
    # ==========================

    cursor.execute("""
    SELECT COUNT(*)
    FROM bills
    WHERE uid=%s
    AND DATE(bill_date)
    BETWEEN %s AND %s
    """,
    (
        session["uid"],
        from_date,
        to_date
    ))

    total_bills = cursor.fetchone()[0]

    # ==========================
    # AVERAGE BILL
    # ==========================

    average_bill = 0

    if total_bills > 0:

        average_bill = round(
            total_sales / total_bills,
            2
        )

    # ==========================
    # TOTAL PROFIT
    # ==========================

    cursor.execute("""
    SELECT IFNULL(
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

        AND DATE(b.bill_date)
        BETWEEN %s AND %s
    """,
    (
        session["uid"],
        session["uid"],
        session["uid"],
        from_date,
        to_date
    ))

    total_profit = cursor.fetchone()[0]

    # ==========================
    # TOP SELLING PRODUCT
    # ==========================

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

        AND DATE(b.bill_date)
        BETWEEN %s AND %s

    GROUP BY p.product_name

    ORDER BY qty DESC

    LIMIT 1
    """,
    (
        session["uid"],
        session["uid"],
        session["uid"],
        from_date,
        to_date
    ))

    product = cursor.fetchone()

    if product:

        top_product = product[0]

    else:

        top_product = "No Data"

    cursor.close()
    conn.close()

    return render_template(

        "reportResult.html",

        report_type=f"{from_date} To {to_date}",

        total_sales=total_sales,

        total_profit=total_profit,

        total_bills=total_bills,

        average_bill=average_bill,

        top_product=top_product

    )

# ==========================
# REPORT PDF
# ==========================

@app.route('/downloadReport/<report_type>')
@login_required
def downloadReport(report_type):

    conn = getConnection()
    cursor = conn.cursor()

    if report_type == "today":
        condition = "DATE(b.bill_date)=CURDATE()"

    elif report_type == "7days":
        condition = "b.bill_date >= NOW() - INTERVAL 7 DAY"

    elif report_type == "30days":
        condition = "b.bill_date >= NOW() - INTERVAL 30 DAY"

    else:
        condition = "b.bill_date >= NOW() - INTERVAL 6 MONTH"

    # ==========================
    # TOTAL SALES
    # ==========================

    cursor.execute(f"""
    SELECT IFNULL(SUM(total_amount),0)
    FROM bills b
    WHERE b.uid=%s
    AND {condition}
    """,
    (
        session["uid"],
    ))

    total_sales = cursor.fetchone()[0]

    # ==========================
    # TOTAL PROFIT
    # ==========================

    cursor.execute(f"""
    SELECT IFNULL(
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

        AND {condition}
    """,
    (
        session["uid"],
        session["uid"],
        session["uid"]
    ))

    total_profit = cursor.fetchone()[0]

    # ==========================
    # TOTAL BILLS
    # ==========================

    cursor.execute(f"""
    SELECT COUNT(*)
    FROM bills b
    WHERE b.uid=%s
    AND {condition}
    """,
    (
        session["uid"],
    ))

    total_bills = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    pdf_file = f"{report_type}_report.pdf"

    c = canvas.Canvas(pdf_file)

    c.setFont("Helvetica-Bold",18)
    c.drawString(180,800,"BUSINESS REPORT")

    c.setFont("Helvetica",12)

    c.drawString(50,740,f"Report Type : {report_type}")
    c.drawString(50,710,f"Total Sales : Rs.{total_sales}")
    c.drawString(50,680,f"Total Profit : Rs.{total_profit}")
    c.drawString(50,650,f"Total Bills : {total_bills}")

    c.save()

    return send_file(
        pdf_file,
        as_attachment=True
    )


from ai import ask_ai
from business_context import get_business_context
from flask import jsonify

@app.route("/testAI")
def testAI():

    answer = ask_ai(
        "Say Hello Vivek. Gemini connection successful."
    )

    return answer

@app.route('/askAI', methods=['POST'])
@login_required
def askAI():

    message = request.form['message'].lower()

    # ==========================================
    # AI ACTION CENTER
    # ==========================================

    if "open billing" in message or "billing" == message:

        return jsonify({
            "reply": "💰 Opening Billing Module...",
            "action": "billing"
        })

    elif "open products" in message or "product list" in message:

        return jsonify({
            "reply": "📦 Opening Product List...",
            "action": "products"
        })

    elif "open reports" in message or "reports" == message:

        return jsonify({
            "reply": "📊 Opening Reports...",
            "action": "reports"
        })

    elif "open dashboard" in message:

        return jsonify({
            "reply": "🏠 Opening Dashboard...",
            "action": "dashboard"
        })

    elif "open dead stock" in message:

        return jsonify({
            "reply": "⚠ Opening Dead Stock Detector...",
            "action": "deadstock"
        })

    elif "open prediction" in message:

        return jsonify({
            "reply": "🤖 Opening AI Prediction...",
            "action": "prediction"
        })

    elif "open sales history" in message:

        return jsonify({
            "reply": "📈 Opening Sales History...",
            "action": "saleshistory"
        })

    elif "logout" == message:

        return jsonify({
            "reply": "👋 Logging Out...",
            "action": "logout"
        })

    prompt = ""

    # ==========================================
    # TODAY SALES
    # ==========================================

    if "today" in message and "sale" in message:

        sales = get_today_sales()

        prompt = f"""
        You are an AI Business Consultant.

        Today's Total Sales : ₹{sales}

        Explain today's business performance professionally.
        Give 2-3 useful business suggestions.
        """

    # ==========================================
    # TOTAL SALES
    # ==========================================

    elif "total sales" in message:

        sales = get_total_sales()

        prompt = f"""
        Total Sales : ₹{sales}

        Explain this professionally.
        """

    # ==========================================
    # PROFIT
    # ==========================================

    elif "profit" in message:

        profit = get_total_profit()

        prompt = f"""
        Total Profit : ₹{profit}

        Explain whether this is good.

        Give business suggestions.
        """

    # ==========================================
    # LOW STOCK
    # ==========================================

    elif "low stock" in message or "restock" in message:

        rows = get_low_stock()

        if len(rows) == 0:

            return jsonify({
                "reply":
                "✅ Excellent! No products are currently low in stock."
            })

        stock_text = ""

        for p in rows:

            stock_text += f"{p[0]} : {p[1]} units\n"

        prompt = f"""
        These products are running low.

        {stock_text}

        Suggest what should be restocked first
        and why.
        """

    # ==========================================
    # TOP PRODUCTS
    # ==========================================

    elif "top product" in message or "best selling" in message:

        products = get_top_products()

        text = ""

        for p in products:

            text += f"{p[0]} Sold : {p[1]}\n"

        prompt = f"""
        These are the best selling products.

        {text}

        Explain the sales trend professionally.
        """

    # ==========================================
    # BUSINESS ANALYSIS
    # ==========================================

    elif "analyze" in message or "business" in message:

        sales = get_total_sales()

        profit = get_total_profit()

        products = get_total_products()

        low_stock = get_low_stock()

        top_products = get_top_products()

        prompt = f"""
        You are a Senior AI Business Consultant.

        Business Data

        Total Products :
        {products}

        Total Sales :
        ₹{sales}

        Total Profit :
        ₹{profit}

        Low Stock Products :

        {low_stock}

        Top Selling Products :

        {top_products}

        Give complete business analysis.

        Include:

        ✔ Strengths

        ✔ Weakness

        ✔ Opportunities

        ✔ Recommendations

        ✔ Overall Business Rating /10
        """

    # ==========================================
    # CEO MODE
    # ==========================================

    elif (
        "good morning" in message or
        "hello" in message or
        "hi" in message or
        "dashboard summary" in message or
        "ceo summary" in message
    ):

        summary = get_ceo_summary()

        prompt = f"""
        You are the CEO AI Assistant.

        {summary}

        Prepare a beautiful Daily Business Summary.

        Include:

        🌅 Greeting

        📈 Sales

        💰 Profit

        📦 Products

        ⚠ Low Stock

        🏆 Top Selling Products

        💡 Business Recommendations

        📊 Overall Business Health
        """        

    # ==========================================
    # GENERAL AI
    # ==========================================

    else:

        prompt = f"""
        You are an AI Business Assistant.

        User Question:

        {message}

        Give professional answer.
        """

    answer = ask_ai(prompt)

    return jsonify({
    "reply": answer,
    "action": "none"
})


@app.route("/uploadPurchaseBill", methods=["POST"])
@login_required
def uploadPurchaseBill():

    if "bill" not in request.files:

        return "No File Uploaded"

    file = request.files["bill"]

    if file.filename == "":

        return "No File Selected"

    filename = secure_filename(
        file.filename
    )

    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )

    file.save(filepath)

    return redirect(
        "/processOCR/" + filename
    )

@app.route("/processOCR/<filename>")
@login_required
def processOCR(filename):

    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )

    ocr_settings = get_user_settings(session["uid"])
    if not ocr_settings.get("ai_ocr", 1):
        return "AI OCR is disabled in Settings. Enable it under Settings > AI Features before uploading bills.", 403

    bill = extract_purchase_bill(filepath)

    session["ocr_bill"] = bill

    return render_template(
        "purchasePreview.html",
        bill=bill
    )

import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
# PURCHASE OCR PAGE
# ==========================================

@app.route("/purchaseOCR")
@login_required
def purchaseOCR():

    return render_template("purchaseOCR.html")

# ==========================================
# CONFIRM PURCHASE IMPORT
# ==========================================

@app.route("/confirmPurchaseImport", methods=["POST"])
@login_required
def confirmPurchaseImport():

    bill = session.get("ocr_bill")

    if not bill:

        return """
        <script>
        alert("No OCR Data Found.");
        window.location="/purchaseOCR";
        </script>
        """

    supplier = str(
        bill.get("supplier", "")
    ).strip()

    invoice_number = str(
        bill.get("invoice_number", "")
    ).strip()

    invoice_date = str(
        bill.get("invoice_date", "")
    ).strip()

    from datetime import datetime

    # ==========================================
    # DATE FORMAT FIX
    # ==========================================

    formats = [

    "%d %b %Y",
    "%d %B %Y",

    "%d-%b-%Y",
    "%d-%B-%Y",

    "%d-%b-%y",    
    "%d-%B-%y",

    "%d-%m-%Y",
    "%d-%m-%y",

    "%d/%m/%Y",
    "%d/%m/%y",

    "%Y-%m-%d"

]

    original_date = invoice_date

    converted = False

    for fmt in formats:

        try:

            invoice_date = datetime.strptime(
                invoice_date,
                fmt
            ).strftime("%Y-%m-%d")

            converted = True

            break

        except Exception:
            pass

    print("=" * 60)
    print("OCR DATE :", original_date)
    print("MYSQL DATE :", invoice_date)
    print("=" * 60)

    if not converted:

        return f"""
        <script>

        alert("Invalid Invoice Date : {original_date}");

        window.location="/purchaseOCR";

        </script>
        """

    conn = getConnection()

    cursor = conn.cursor()

    # ==========================================
    # DUPLICATE CHECK
    # ==========================================

    cursor.execute("""

    SELECT COUNT(*)

    FROM purchase_history

    WHERE uid=%s

    AND supplier=%s

    AND invoice_number=%s

    AND invoice_date=%s

    """,
    (

        session["uid"],

        supplier,

        invoice_number,

        invoice_date

    ))

    already = cursor.fetchone()[0]

    if already > 0:

        cursor.close()

        conn.close()

        return """
        <script>

        alert("⚠ This Purchase Invoice Already Exists.");

        window.location="/purchaseOCR";

        </script>
        """

    # ==========================================
    # SUPPLIER CHECK
    # ==========================================

    cursor.execute("""

    SELECT supplier_id

    FROM suppliers

    WHERE uid=%s

    AND LOWER(supplier_name)=LOWER(%s)

    """,
    (

        session["uid"],

        supplier

    ))

    supplier_data = cursor.fetchone()

    if supplier_data is None:

        cursor.execute("""

        INSERT INTO suppliers
        (
            uid,
            supplier_name
        )
        VALUES
        (
            %s,
            %s
        )

        """,
        (

            session["uid"],

            supplier

        ))

        conn.commit()

    # ==========================================
    # PURCHASE SUMMARY
    # ==========================================

    total_products = len(
        bill.get("items", [])
    )

    total_quantity = 0

    total_amount = 0

    for item in bill.get("items", []):

        qty = int(
            item.get("quantity", 1)
        )

        price = float(
            item.get("cost_price", 0)
        )

        total_quantity += qty

        total_amount += qty * price

    print("=" * 60)
    print("TOTAL PRODUCTS :", total_products)
    print("TOTAL QUANTITY :", total_quantity)
    print("TOTAL AMOUNT :", total_amount)
    print("=" * 60)

    # ==========================================
    # SAVE PURCHASE HISTORY
    # ==========================================

    cursor.execute("""

    INSERT INTO purchase_history
    (

    uid,

    supplier,

    invoice_number,

    invoice_date,

    total_products,

    total_quantity,

    total_amount,

    purchase_status

    )

    VALUES

    (

    %s,

    %s,

    %s,

    %s,

    %s,

    %s,

    %s,

    %s

    )

    """,
    (

        session["uid"],

        supplier,

        invoice_number,

        invoice_date,

        total_products,

        total_quantity,

        total_amount,

        "Imported"

    ))

    conn.commit()

    purchase_id = cursor.lastrowid

    print("=" * 60)
    print("PURCHASE HISTORY SAVED")
    print("PURCHASE ID :", purchase_id)
    print("=" * 60)



    # ==========================================
    # LOAD DATABASE PRODUCT LIST
    # ==========================================

    cursor.execute("""

    SELECT

        product_name,

        brand,

        category,

        model_number

    FROM products

    WHERE uid=%s

    """,
    (
        session["uid"],
    ))

    rows = cursor.fetchall()

    database_products = []

    for r in rows:

        database_products.append({

            "product": str(r[0] or "").strip(),

            "brand": str(r[1] or "").strip(),

            "category": str(r[2] or "").strip(),

            "model_number": str(r[3] or "").strip()

        })

    print("=" * 70)
    print("DATABASE PRODUCTS")
    print(database_products)
    print("=" * 70)

    # ==========================================
    # START IMPORT
    # ==========================================

    for item in bill.get("items", []):

        print("=" * 70)
        print("OCR ITEM :", item)
        print("=" * 70)

        ocr_product = str(
            item.get("product", "")
        ).strip()

        quantity = int(
            item.get("quantity", 1)
        )

        cost_price = float(
            item.get("cost_price", 0)
        )

        brand = str(
            item.get("brand", "")
        ).strip()

        category = str(
            item.get("category", "General")
        ).strip()

        sub_category = str(
            item.get("sub_category", "")
        ).strip()

        model_number = str(
            item.get("model_number", "")
        ).strip()

        color = str(
            item.get("color", "")
        ).strip()

        warranty = str(
            item.get("warranty", "")
        ).strip()

        gst = int(
            item.get("gst", 18)
        )

        print("OCR PRODUCT :", ocr_product)
        print("MODEL :", model_number)

        # ==========================================
        # AI PRODUCT MATCHING
        # ==========================================

        matching_settings = get_user_settings(session["uid"])
        if matching_settings.get("ai_product_matching", 1):
            result = find_best_product(
                {"product": ocr_product, "brand": brand, "category": category, "model_number": model_number},
                [f'{p["product"]} | {p["brand"]} | {p["category"]} | {p["model_number"]}' for p in database_products]
            )
        else:
            result = {"match": "NEW PRODUCT", "confidence": 0}

        print("AI RESULT :", result)

        matched_product = result.get(
            "match",
            "NEW PRODUCT"
        )

        confidence = int(
            result.get(
                "confidence",
                0
            )
        )

        if matched_product != "NEW PRODUCT":

            product_name = matched_product

        else:

            product_name = ocr_product

        print("FINAL PRODUCT :", product_name)
        print("CONFIDENCE :", confidence)

        cursor.execute("""

        SELECT

            pid,

            stock,

            cost_price,

            brand,

            category,

            model_number

        FROM products

        WHERE uid=%s

        AND LOWER(product_name)=LOWER(%s)

        """,
        (
            session["uid"],
            product_name
        ))

        product = cursor.fetchone()

        print("DB PRODUCT :", product)



            # ==========================================
        # SAME PRODUCT FOUND
        # ==========================================

        if product:

            print("EXISTING PRODUCT FOUND")

            pid = product[0]
            current_stock = int(product[1])
            new_stock = current_stock + quantity

            cursor.execute("""
            UPDATE products
            SET
                stock=%s,
                cost_price=%s,
                supplier=%s,
                last_purchase_price=%s,
                last_purchase_date=%s
            WHERE pid=%s
            AND uid=%s
            """,
            (
                new_stock,
                cost_price,
                supplier,
                cost_price,
                invoice_date,
                pid,
                session["uid"]
            ))

            print("PRODUCT UPDATED")

        else:

            print("NEW PRODUCT INSERT")

            selling_price = round(cost_price * 1.30, 2)

            cursor.execute("""
            INSERT INTO products
            (
                uid,
                product_name,
                brand,
                category,
                sub_category,
                model_number,
                color,
                warranty,
                gst,
                supplier,
                last_purchase_price,
                last_purchase_date,
                cost_price,
                selling_price,
                stock,
                created_date
            )
            VALUES
            (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()
            )
            """,
            (
                session["uid"],
                product_name,
                brand,
                category,
                sub_category,
                model_number,
                color,
                warranty,
                gst,
                supplier,
                cost_price,
                invoice_date,
                cost_price,
                selling_price,
                quantity
            ))

            pid = cursor.lastrowid
            print("NEW PRODUCT ID :", pid)

        total_price = quantity * cost_price

        cursor.execute("""
        INSERT INTO purchase_items
        (
            uid,
            purchase_id,
            product_id,
            product_name,
            brand,
            category,
            model_number,
            quantity,
            cost_price,
            total_price
        )
        VALUES
        (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        """,
        (
            session["uid"],
            purchase_id,
            pid,
            product_name,
            brand,
            category,
            model_number,
            quantity,
            cost_price,
            total_price
        ))

        print("PURCHASE ITEM SAVED")

    # ==========================================
    # IMPORT COMPLETED
    # ==========================================

    conn.commit()

    print("=" * 60)
    print("PURCHASE IMPORT SUCCESS")
    print("=" * 60)

    cursor.close()
    conn.close()

    session.pop("ocr_bill", None)

    return """
    <script>
    alert("✅ Purchase Imported Successfully.");
    window.location="/productList";
    </script>
    """

# ==========================================
# PURCHASE CENTER
# ==========================================

@app.route("/purchaseCenter")
@login_required
def purchaseCenter():

    conn = getConnection()
    cursor = conn.cursor(dictionary=True)

    uid = session["uid"]

    # ==========================================
    # TODAY'S PURCHASE
    # ==========================================

    cursor.execute("""
        SELECT IFNULL(SUM(total_amount), 0) AS total
        FROM purchase_history
        WHERE uid=%s
        AND invoice_date=CURDATE()
    """, (uid,))

    today_purchase = cursor.fetchone()["total"]


    # ==========================================
    # TOTAL PURCHASE VALUE
    # ==========================================

    cursor.execute("""
        SELECT IFNULL(SUM(total_amount), 0) AS total
        FROM purchase_history
        WHERE uid=%s
    """, (uid,))

    total_purchase = cursor.fetchone()["total"]


    # ==========================================
    # TOTAL SUPPLIERS
    # ==========================================

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM suppliers
        WHERE uid=%s
    """, (uid,))

    total_suppliers = cursor.fetchone()["total"]


    # ==========================================
    # TOTAL INVOICES
    # ==========================================

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM purchase_history
        WHERE uid=%s
    """, (uid,))

    total_invoices = cursor.fetchone()["total"]


    # ==========================================
    # RECENT PURCHASES
    # ==========================================

    cursor.execute("""
        SELECT
            purchase_id,
            invoice_number,
            supplier,
            invoice_date,
            total_products,
            total_amount
        FROM purchase_history
        WHERE uid=%s
        ORDER BY invoice_date DESC
        LIMIT 10
    """, (uid,))

    recent_purchase = cursor.fetchall()


    # ==========================================
    # SUPPLIER TABLE
    # ==========================================

    cursor.execute("""
        SELECT
            s.supplier_id,
            s.supplier_name,

            (
                SELECT COUNT(*)
                FROM purchase_history ph
                WHERE ph.uid=%s
                AND LOWER(ph.supplier)=LOWER(s.supplier_name)
            ) AS total_invoice,

            (
                SELECT IFNULL(SUM(pi.quantity), 0)
                FROM purchase_history ph
                JOIN purchase_items pi
                    ON pi.purchase_id = ph.purchase_id
                WHERE ph.uid=%s
                AND pi.uid=%s
                AND LOWER(ph.supplier)=LOWER(s.supplier_name)
            ) AS total_products,

            (
                SELECT IFNULL(SUM(pi.total_price), 0)
                FROM purchase_history ph
                JOIN purchase_items pi
                    ON pi.purchase_id = ph.purchase_id
                WHERE ph.uid=%s
                AND pi.uid=%s
                AND LOWER(ph.supplier)=LOWER(s.supplier_name)
            ) AS purchase_value,

            (
                SELECT MAX(ph.invoice_date)
                FROM purchase_history ph
                WHERE ph.uid=%s
                AND LOWER(ph.supplier)=LOWER(s.supplier_name)
            ) AS last_purchase

        FROM suppliers s
        WHERE s.uid=%s
        ORDER BY s.supplier_name
    """, (
        uid,
        uid, uid,
        uid, uid,
        uid,
        uid
    ))

    suppliers = cursor.fetchall()


    # ==========================================
    # PURCHASE HISTORY
    # ==========================================

    cursor.execute("""
        SELECT
            purchase_id,
            invoice_number,
            supplier,
            invoice_date,
            total_products,
            total_amount,
            purchase_status
        FROM purchase_history
        WHERE uid=%s
        ORDER BY invoice_date DESC
    """, (uid,))

    purchase_history = cursor.fetchall()


    cursor.close()
    conn.close()


    return render_template(
        "purchaseCenter.html",

        today_purchase=today_purchase,

        total_purchase=total_purchase,

        total_suppliers=total_suppliers,

        total_invoices=total_invoices,

        recent_purchase=recent_purchase,

        suppliers=suppliers,

        purchase_history=purchase_history
    )

# ==========================================
# SUPPLIER DETAILS
# ==========================================

@app.route("/supplierDetails/<int:supplier_id>")
@login_required
def supplierDetails(supplier_id):

    conn = getConnection()
    cursor = conn.cursor(dictionary=True)

    uid = session["uid"]

    # ==========================================
    # SUPPLIER INFORMATION
    # ==========================================

    cursor.execute("""
        SELECT
            supplier_id,
            supplier_name
        FROM suppliers
        WHERE supplier_id=%s
        AND uid=%s
    """, (
        supplier_id,
        uid
    ))

    supplier = cursor.fetchone()

    if supplier is None:

        cursor.close()
        conn.close()

        return "Supplier Not Found"


    # ==========================================
    # PURCHASE HISTORY OF SUPPLIER
    # ==========================================

    cursor.execute("""
        SELECT
            purchase_id,
            invoice_number,
            invoice_date,
            total_products,
            total_quantity,
            total_amount,
            purchase_status
        FROM purchase_history
        WHERE uid=%s
        AND supplier=%s
        ORDER BY invoice_date DESC
    """, (
        uid,
        supplier["supplier_name"]
    ))

    purchases = cursor.fetchall()


    # ==========================================
    # SUPPLIER TOTALS
    # ==========================================

    total_invoices = len(purchases)

    total_products = 0
    total_quantity = 0
    total_purchase = 0

    for purchase in purchases:

        total_products += int(
            purchase["total_products"] or 0
        )

        total_quantity += int(
            purchase["total_quantity"] or 0
        )

        total_purchase += float(
            purchase["total_amount"] or 0
        )


    # ==========================================
    # CLOSE CONNECTION
    # ==========================================

    cursor.close()
    conn.close()


    # ==========================================
    # SUPPLIER DETAILS PAGE
    # ==========================================

    return render_template(
        "supplierDetails.html",

        supplier=supplier,

        purchases=purchases,

        total_invoices=total_invoices,

        total_products=total_products,

        total_quantity=total_quantity,

        total_purchase=total_purchase
    )


# ==========================================
# SUPPLIER DETAILS BY NAME
# ==========================================

@app.route("/supplierDetailsByName/<path:supplier_name>")
@login_required
def supplierDetailsByName(supplier_name):

    conn = getConnection()
    cursor = conn.cursor(dictionary=True)

    uid = session["uid"]


    # ==========================================
    # FIND SUPPLIER
    # ==========================================

    cursor.execute("""
        SELECT
            supplier_id,
            supplier_name
        FROM suppliers
        WHERE uid=%s
        AND LOWER(supplier_name)=LOWER(%s)
    """, (
        uid,
        supplier_name
    ))

    supplier = cursor.fetchone()


    if supplier is None:

        cursor.close()
        conn.close()

        return "Supplier Not Found"


    # ==========================================
    # PURCHASE HISTORY
    # ==========================================

    cursor.execute("""
        SELECT
            purchase_id,
            invoice_number,
            invoice_date,
            total_products,
            total_quantity,
            total_amount,
            purchase_status
        FROM purchase_history
        WHERE uid=%s
        AND LOWER(supplier)=LOWER(%s)
        ORDER BY invoice_date DESC
    """, (
        uid,
        supplier_name
    ))

    purchases = cursor.fetchall()


    # ==========================================
    # TOTALS
    # ==========================================

    total_invoices = len(purchases)

    total_products = 0
    total_quantity = 0
    total_purchase = 0

    for purchase in purchases:

        total_products += int(
            purchase["total_products"] or 0
        )

        total_quantity += int(
            purchase["total_quantity"] or 0
        )

        total_purchase += float(
            purchase["total_amount"] or 0
        )


    cursor.close()
    conn.close()


    return render_template(
        "supplierDetails.html",

        supplier=supplier,

        purchases=purchases,

        total_invoices=total_invoices,

        total_products=total_products,

        total_quantity=total_quantity,

        total_purchase=total_purchase
    )

# ==========================================
# NOTIFICATIONS API
# ==========================================

@app.route("/api/notifications")
@login_required
def notifications():
    conn = getConnection()
    cursor = conn.cursor(dictionary=True)
    uid = session["uid"]
    notifications = []
    try:
        settings_data = get_user_settings(uid, cursor)
        threshold = int(settings_data.get("low_stock_threshold", 10))
        dead_days = int(settings_data.get("dead_stock_days", 15))

        if settings_data.get("out_of_stock_alert", 1):
            cursor.execute("SELECT COUNT(*) AS count FROM products WHERE uid=%s AND stock<=0", (uid,))
            count = cursor.fetchone()["count"]
            if count:
                notifications.append({"type":"danger", "icon":"ti-package-off", "title":"Out of Stock",
                    "message":f"{count} product(s) are out of stock.", "link":"/productList"})

        if settings_data.get("low_stock_alert", 1):
            cursor.execute("SELECT COUNT(*) AS count FROM products WHERE uid=%s AND stock>0 AND stock<%s", (uid, threshold))
            count = cursor.fetchone()["count"]
            if count:
                notifications.append({"type":"warning", "icon":"ti-alert-triangle", "title":"Low Stock",
                    "message":f"{count} product(s) are below your threshold of {threshold}.", "link":"/productList"})

        if settings_data.get("dead_stock_alert", 1):
            cursor.execute("""SELECT COUNT(*) AS count FROM products p WHERE p.uid=%s AND NOT EXISTS
                (SELECT 1 FROM bill_items bi WHERE bi.uid=p.uid AND bi.product_id=p.pid
                AND bi.sale_date >= NOW() - INTERVAL %s DAY)""", (uid, dead_days))
            count = cursor.fetchone()["count"]
            if count:
                notifications.append({"type":"info", "icon":"ti-package", "title":"Dead Stock",
                    "message":f"{count} product(s) have no sales in the last {dead_days} days.", "link":"/deadStock"})

        if settings_data.get("ai_recommendation_alert", 1) and settings_data.get("ai_recommendations", 1):
            cursor.execute("SELECT COUNT(*) AS count FROM products WHERE uid=%s AND stock>0 AND stock<%s", (uid, threshold))
            low_stock = cursor.fetchone()["count"]
            if low_stock >= 5:
                notifications.append({"type":"ai", "icon":"ti-robot", "title":"AI Recommendation",
                    "message":"Several products are running low. Consider restocking soon.", "link":"/productList"})
        return jsonify({"notifications": notifications, "count": len(notifications)})
    finally:
        cursor.close()
        conn.close()

# ==========================================
# SETTINGS HELPERS + SETTINGS ROUTES
# ==========================================

def ensure_user_settings_table(cursor):
    """Create settings storage and add missing columns for older installations."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            setting_id INT AUTO_INCREMENT PRIMARY KEY,
            uid INT NOT NULL UNIQUE,
            low_stock_threshold INT NOT NULL DEFAULT 10,
            dead_stock_days INT NOT NULL DEFAULT 15,
            currency VARCHAR(8) NOT NULL DEFAULT 'INR',
            gst_rate DECIMAL(5,2) NOT NULL DEFAULT 18.00,
            show_fssai_on_bill TINYINT(1) NOT NULL DEFAULT 1,
            low_stock_alert TINYINT(1) NOT NULL DEFAULT 1,
            out_of_stock_alert TINYINT(1) NOT NULL DEFAULT 1,
            dead_stock_alert TINYINT(1) NOT NULL DEFAULT 1,
            ai_recommendation_alert TINYINT(1) NOT NULL DEFAULT 1,
            ai_recommendations TINYINT(1) NOT NULL DEFAULT 1,
            ai_ocr TINYINT(1) NOT NULL DEFAULT 1,
            ai_product_matching TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)
    # Existing deployments may already have a smaller user_settings table.
    columns = {
        "low_stock_threshold": "INT NOT NULL DEFAULT 10",
        "dead_stock_days": "INT NOT NULL DEFAULT 15",
        "currency": "VARCHAR(8) NOT NULL DEFAULT 'INR'",
        "gst_rate": "DECIMAL(5,2) NOT NULL DEFAULT 18.00",
        "show_fssai_on_bill": "TINYINT(1) NOT NULL DEFAULT 1",
        "low_stock_alert": "TINYINT(1) NOT NULL DEFAULT 1",
        "out_of_stock_alert": "TINYINT(1) NOT NULL DEFAULT 1",
        "dead_stock_alert": "TINYINT(1) NOT NULL DEFAULT 1",
        "ai_recommendation_alert": "TINYINT(1) NOT NULL DEFAULT 1",
        "ai_recommendations": "TINYINT(1) NOT NULL DEFAULT 1",
        "ai_ocr": "TINYINT(1) NOT NULL DEFAULT 1",
        "ai_product_matching": "TINYINT(1) NOT NULL DEFAULT 1",
    }
    cursor.execute("SHOW COLUMNS FROM user_settings")
    column_rows = cursor.fetchall()
    existing_columns = {
        row.get("Field") if isinstance(row, dict) else row[0]
        for row in column_rows
    }
    for column, definition in columns.items():
        if column not in existing_columns:
            cursor.execute(f"ALTER TABLE user_settings ADD COLUMN {column} {definition}")


def get_user_settings(uid, cursor=None):
    """Return settings for a user, creating the default row when necessary."""
    owns_connection = cursor is None
    conn = getConnection() if owns_connection else None
    cur = conn.cursor(dictionary=True) if owns_connection else cursor
    try:
        ensure_user_settings_table(cur)
        cur.execute("SELECT setting_id FROM user_settings WHERE uid=%s", (uid,))
        if cur.fetchone() is None:
            cur.execute("INSERT INTO user_settings (uid) VALUES (%s)", (uid,))
            if owns_connection:
                conn.commit()
        cur.execute("SELECT * FROM user_settings WHERE uid=%s", (uid,))
        result = cur.fetchone()
        return result or {}
    finally:
        if owns_connection:
            cur.close()
            conn.close()


@app.route("/settings")
@login_required
def settings():
    uid = session["uid"]
    conn = getConnection()
    cursor = conn.cursor(dictionary=True)
    try:
        ensure_user_settings_table(cursor)
        cursor.execute("SELECT setting_id FROM user_settings WHERE uid=%s", (uid,))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO user_settings (uid) VALUES (%s)", (uid,))
            conn.commit()

        cursor.execute("""
            SELECT id, name, email, phone, business_name, gst_number, fssai_number, invoice_prefix
            FROM users WHERE id=%s
        """, (uid,))
        account = cursor.fetchone() or {}
        cursor.execute("SELECT * FROM user_settings WHERE uid=%s", (uid,))
        settings_data = cursor.fetchone() or {}
        session["name"] = account.get("name", session.get("name", ""))
        return render_template("settings.html", settings=settings_data, account=account)
    finally:
        cursor.close()
        conn.close()


@app.route("/saveAccountSettings", methods=["POST"])
@login_required
def saveAccountSettings():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    if not name or not email:
        return "Name and email are required.", 400

    conn = getConnection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email=%s AND id<>%s", (email, session["uid"]))
        if cursor.fetchone():
            return "That email address is already in use.", 409
        cursor.execute("UPDATE users SET name=%s, email=%s, phone=%s WHERE id=%s",
                       (name, email, phone, session["uid"]))
        conn.commit()
        session["name"] = name
        session["user"] = email
        return redirect("/settings?section=account&saved=account")
    finally:
        cursor.close()
        conn.close()


@app.route("/saveNotificationSettings", methods=["POST"])
@login_required
def saveNotificationSettings():
    fields = ("low_stock_alert", "out_of_stock_alert", "dead_stock_alert", "ai_recommendation_alert")
    values = {field: 1 if request.form.get(field) else 0 for field in fields}
    conn = getConnection()
    cursor = conn.cursor()
    try:
        ensure_user_settings_table(cursor)
        cursor.execute("SELECT setting_id FROM user_settings WHERE uid=%s", (session["uid"],))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO user_settings (uid) VALUES (%s)", (session["uid"],))
        cursor.execute("""UPDATE user_settings SET low_stock_alert=%s, out_of_stock_alert=%s,
            dead_stock_alert=%s, ai_recommendation_alert=%s WHERE uid=%s""",
            (values["low_stock_alert"], values["out_of_stock_alert"], values["dead_stock_alert"],
             values["ai_recommendation_alert"], session["uid"]))
        conn.commit()
        return redirect("/settings?section=notifications&saved=notifications")
    finally:
        cursor.close()
        conn.close()


@app.route("/saveInventorySettings", methods=["POST"])
@login_required
def saveInventorySettings():
    try:
        low_stock_threshold = int(request.form.get("low_stock_threshold", 10))
        dead_stock_days = int(request.form.get("dead_stock_days", 15))
    except (TypeError, ValueError):
        return "Inventory settings must be valid numbers.", 400
    if not 1 <= low_stock_threshold <= 100000 or not 1 <= dead_stock_days <= 3650:
        return "Threshold must be 1–100000 and dead-stock days must be 1–3650.", 400
    currency = request.form.get("currency", "INR").upper()
    if currency not in ("INR", "USD"):
        currency = "INR"
    conn = getConnection()
    cursor = conn.cursor()
    try:
        ensure_user_settings_table(cursor)
        cursor.execute("""INSERT INTO user_settings (uid, low_stock_threshold, dead_stock_days, currency)
            VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE
            low_stock_threshold=VALUES(low_stock_threshold), dead_stock_days=VALUES(dead_stock_days),
            currency=VALUES(currency)""",
            (session["uid"], low_stock_threshold, dead_stock_days, currency))
        conn.commit()
        return redirect("/settings?section=inventory&saved=inventory")
    finally:
        cursor.close()
        conn.close()


@app.route("/saveBillingSettings", methods=["POST"])
@login_required
def saveBillingSettings():
    business_name = request.form.get("business_name", "").strip()
    gst_number = request.form.get("gst_number", "").strip()
    fssai_number = request.form.get("fssai_number", "").strip()
    show_fssai_on_bill = 1 if request.form.get("show_fssai_on_bill") else 0
    invoice_prefix = request.form.get("invoice_prefix", "INV-").strip() or "INV-"
    try:
        gst_rate = float(request.form.get("gst_rate", 18))
    except (TypeError, ValueError):
        return "GST rate is invalid.", 400
    if not 0 <= gst_rate <= 100:
        return "GST rate must be between 0 and 100.", 400
    if not business_name:
        return "Business name is required.", 400
    conn = getConnection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET business_name=%s, gst_number=%s, fssai_number=%s, invoice_prefix=%s WHERE id=%s",
                       (business_name, gst_number, fssai_number, invoice_prefix, session["uid"]))
        ensure_user_settings_table(cursor)
        cursor.execute("""INSERT INTO user_settings (uid, gst_rate, show_fssai_on_bill) VALUES (%s,%s,%s)
            ON DUPLICATE KEY UPDATE gst_rate=VALUES(gst_rate), show_fssai_on_bill=VALUES(show_fssai_on_bill)""",
                       (session["uid"], gst_rate, show_fssai_on_bill))
        conn.commit()
        return redirect("/settings?section=billing&saved=billing")
    finally:
        cursor.close()
        conn.close()


@app.route("/saveAISettings", methods=["POST"])
@login_required
def saveAISettings():
    fields = ("ai_recommendations", "ai_ocr", "ai_product_matching")
    values = {field: 1 if request.form.get(field) else 0 for field in fields}
    conn = getConnection()
    cursor = conn.cursor()
    try:
        ensure_user_settings_table(cursor)
        cursor.execute("SELECT setting_id FROM user_settings WHERE uid=%s", (session["uid"],))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO user_settings (uid) VALUES (%s)", (session["uid"],))
        cursor.execute("""UPDATE user_settings SET ai_recommendations=%s, ai_ocr=%s,
            ai_product_matching=%s WHERE uid=%s""",
            (values["ai_recommendations"], values["ai_ocr"], values["ai_product_matching"], session["uid"]))
        conn.commit()
        return redirect("/settings?section=ai&saved=ai")
    finally:
        cursor.close()
        conn.close()


@app.route("/changePassword", methods=["POST"])
@login_required
def changePassword():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")
    if len(new_password) < 8:
        return "New password must contain at least 8 characters.", 400
    if new_password != confirm_password:
        return "New password and confirmation do not match.", 400
    conn = getConnection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT password FROM users WHERE id=%s", (session["uid"],))
        row = cursor.fetchone()
        if not row or row[0] != current_password:
            return "Current password is incorrect.", 403
        # Keep compatibility with the existing login flow, which compares stored passwords directly.
        cursor.execute("UPDATE users SET password=%s WHERE id=%s", (new_password, session["uid"]))
        conn.commit()
        return redirect("/settings?section=security&saved=password")
    finally:
        cursor.close()
        conn.close()


# ==========================
# ANDROID: DASHBOARD STATS API
# ==========================
@app.route('/api/dashboard-stats', methods=['GET'])
def android_dashboard_stats():
    uid = get_android_user_id()
    if uid is None:
        return jsonify({
            "success": False,
            "message": "Authentication required. Please log in again."
        }), 401

    conn = None
    cursor = None
    try:
        conn = getConnection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*),
                   COALESCE(SUM(CASE WHEN stock < 10 THEN 1 ELSE 0 END), 0)
            FROM products
            WHERE uid = %s
        """, (uid,))
        product_row = cursor.fetchone() or (0, 0)
        total_products = int(product_row[0] or 0)
        low_stock = int(product_row[1] or 0)

        cursor.execute("""
            SELECT COALESCE(SUM(total_amount), 0)
            FROM bills
            WHERE uid = %s AND DATE(bill_date) = CURDATE()
        """, (uid,))
        today_sales_row = cursor.fetchone()
        today_sales = float((today_sales_row or [0])[0] or 0)

        cursor.execute("""
            SELECT COALESCE(SUM((p.selling_price - p.cost_price) * bi.quantity), 0)
            FROM bill_items bi
            JOIN products p ON bi.product_id = p.pid
            JOIN bills b ON bi.bill_id = b.bill_id
            WHERE b.uid = %s AND bi.uid = %s AND p.uid = %s
        """, (uid, uid, uid))
        profit_row = cursor.fetchone()
        total_profit = float((profit_row or [0])[0] or 0)

        return jsonify({
            "success": True,
            "total_products": total_products,
            "low_stock": low_stock,
            "today_sales": round(today_sales, 2),
            "total_profit": round(total_profit, 2)
        }), 200

    except Exception:
        app.logger.exception("Android dashboard stats API error")
        return jsonify({
            "success": False,
            "message": "Unable to load dashboard statistics"
        }), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ==========================
# ANDROID LOGIN API
# ==========================
@app.route('/api/login', methods=['POST'])
def android_login():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "success": False,
            "message": "Invalid request data"
        }), 400

    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({
            "success": False,
            "message": "Email and password are required"
        }), 400

    conn = None
    cursor = None

    try:
        conn = getConnection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM users
            WHERE email = %s AND password = %s
            """,
            (email, password)
        )

        user = cursor.fetchone()

        if user:
            token = create_android_token(user[0])
            return jsonify({
                "success": True,
                "message": "Login successful",
                "token": token,
                "user": {
                    "id": user[0],
                    "name": user[1],
                    "email": email
                }
            }), 200

        return jsonify({
            "success": False,
            "message": "Invalid email or password"
        }), 401

    except Exception as e:
        app.logger.exception("Android login API error")

        return jsonify({
            "success": False,
            "message": "Server error. Please try again."
        }), 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()





# ==========================
# LOGOUT
# ==========================

@app.route('/logout')
@login_required
def logout():

    session.pop("uid", None)
    session.pop("user", None)
    session.pop("name", None)

    return redirect("/login")


# ==========================
# RUN APPLICATION
# ==========================

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)