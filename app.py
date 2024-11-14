from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mysqldb import MySQL
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import re

app = Flask(__name__)
app.config.from_object('config.Config')
app.secret_key = app.config['SECRET_KEY']  # Move to config file

# Initialize MySQL connection with DictCursor
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
mysql = MySQL(app)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Utility functions
def get_db_cursor():
    return mysql.connection.cursor()

def validate_email(email):
    # Fix: Remove UGX suffix and use a more standard email regex pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    return len(password) >= 8

# Home Page
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

# Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    try:
        cur = get_db_cursor()
        
        # Get total products
        cur.execute("SELECT COUNT(*) as count FROM products")
        total_products = cur.fetchone()['count']
        
        # Get low stock products
        cur.execute("SELECT COUNT(*) as count FROM products WHERE quantity < 10")
        low_stock = cur.fetchone()['count']
        
        # Get today's sales
        cur.execute("""
            SELECT COUNT(*) as count, 
                   COALESCE(SUM(total_amount), 0) as total
            FROM sales
            WHERE DATE(sale_time) = CURDATE()
        """)
        sales_data = cur.fetchone()
        
        return render_template('dashboard.html',
                             total_products=total_products,
                             low_stock=low_stock,
                             daily_sales_count=sales_data['count'],
                             daily_sales_total=float(sales_data['total']))
    except Exception as e:
        flash('An error occurred while loading the dashboard.', 'danger')
        app.logger.error(f"Dashboard error: {str(e)}")
        return render_template('dashboard.html', error=True)
    finally:
        cur.close()

# User Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not all([email, password, confirm_password]):
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        if not validate_email(email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('register.html')

        if not validate_password(password):
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')

        try:
            cur = get_db_cursor()
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                flash('Email already registered.', 'danger')
                return render_template('register.html')

            hashed_password = generate_password_hash(password)
            cur.execute("INSERT INTO users (email, password) VALUES (%s, %s)", 
                       (email, hashed_password))
            mysql.connection.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            mysql.connection.rollback()
            flash('An error occurred during registration.', 'danger')
            app.logger.error(f"Registration error: {str(e)}")
        finally:
            cur.close()

    return render_template('register.html')

# User Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not all([email, password]):
            flash('Please enter both email and password.', 'danger')
            return render_template('login.html')

        try:
            cur = get_db_cursor()
            cur.execute("""
                SELECT id, email, password 
                FROM users 
                WHERE email = %s
            """, (email,))
            
            user = cur.fetchone()

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['email'] = user['email']
                session.permanent = True  # Make session permanent
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid email or password.', 'danger')

        except Exception as e:
            app.logger.error(f"Login error: {str(e)}")
            flash('An error occurred during login.', 'danger')
        finally:
            cur.close()

    return render_template('login.html')

# User Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# Add Product
@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        try:
            product_name = request.form.get('product_name')
            price = request.form.get('price')
            quantity = request.form.get('quantity')
            user_id = session.get('user_id')  # Get the current user's ID from session

            if not all([product_name, price, quantity, user_id]):
                flash('All fields are required.', 'danger')
                return redirect(url_for('add_product'))

            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO products 
                (product_name, price, quantity, user_id) 
                VALUES (%s, %s, %s, %s)
            """, (product_name, price, quantity, user_id))
            
            mysql.connection.commit()
            flash('Product added successfully!', 'success')
            return redirect(url_for('stock'))

        except Exception as e:
            mysql.connection.rollback()
            app.logger.error(f"Add product error: {str(e)}")
            flash('An error occurred while adding the product.', 'danger')
        finally:
            cur.close()

    return render_template('add_product.html')

# Edit Product
@app.route('/edit_product/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    try:
        cur = get_db_cursor()
        
        if request.method == 'POST':
            # Get form data
            product_name = request.form.get('product_name')
            price = request.form.get('price')
            quantity = request.form.get('quantity')
            category = request.form.get('category')
            description = request.form.get('description')

            if not all([product_name, price, quantity]):
                flash('Product name, price, and quantity are required.', 'danger')
                return redirect(url_for('edit_product', id=id))

            try:
                # Update product
                cur.execute("""
                    UPDATE products 
                    SET product_name = %s, 
                        price = %s, 
                        quantity = %s, 
                        category = %s, 
                        description = %s 
                    WHERE id = %s
                """, (product_name, price, quantity, category, description, id))
                
                mysql.connection.commit()
                flash('Product updated successfully!', 'success')
                return redirect(url_for('stock'))
            except Exception as e:
                mysql.connection.rollback()
                flash('Failed to update product.', 'danger')
                app.logger.error(f"Database error: {str(e)}")
                return redirect(url_for('edit_product', id=id))

        # GET request - fetch product
        cur.execute("""
            SELECT p.*, c.name as category_name 
            FROM products p 
            LEFT JOIN categories c ON p.category = c.id 
            WHERE p.id = %s
        """, (id,))
        
        product = cur.fetchone()

        if not product:
            flash('Product not found.', 'danger')
            return redirect(url_for('stock'))

        # Fetch categories
        cur.execute("SELECT * FROM categories ORDER BY name")
        categories = cur.fetchall()

        return render_template('edit_product.html', 
                             product=product, 
                             categories=categories)

    except Exception as e:
        app.logger.error(f"Edit product error: {str(e)}")
        flash('An error occurred while editing the product.', 'danger')
        return redirect(url_for('stock'))
    finally:
        if 'cur' in locals():
            cur.close()

# Delete Product
@app.route('/delete_product/<int:id>')
@login_required
def delete_product(id):
    try:
        cur = get_db_cursor()
        
        # Check if product exists
        cur.execute("SELECT * FROM products WHERE id = %s", (id,))
        product = cur.fetchone()
        
        if not product:
            flash('Product not found.', 'danger')
            return redirect(url_for('stock'))

        # Delete product
        cur.execute("DELETE FROM products WHERE id = %s", (id,))
        mysql.connection.commit()
        
        flash('Product deleted successfully!', 'success')
        return redirect(url_for('stock'))

    except Exception as e:
        app.logger.error(f"Delete product error: {str(e)}")
        flash('An error occurred while deleting the product.', 'danger')
        return redirect(url_for('stock'))
    finally:
        cur.close()

# View Stock
@app.route('/stock')
@login_required
def stock():
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'id')
    order = request.args.get('order', 'asc')
    page = request.args.get('page', 1, type=int)
    per_page = 10

    try:
        cur = get_db_cursor()
        
        # Build the query
        query = """
            SELECT p.*, c.name as category_name 
            FROM products p 
            LEFT JOIN categories c ON p.category = c.id 
            WHERE 1=1
        """
        params = []

        if search:
            query += " AND p.product_name LIKE %s"
            params.append(f'%{search}%')

        # Add sorting
        query += f" ORDER BY p.{sort} {order}"
        
        # Add pagination
        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, (page - 1) * per_page])

        cur.execute(query, tuple(params))
        products = cur.fetchall()

        # Get total count for pagination
        cur.execute("""
            SELECT COUNT(*) as count 
            FROM products p 
            WHERE 1=1
        """ + (" AND p.product_name LIKE %s" if search else ""),
        (f'%{search}%',) if search else ())
        
        total = cur.fetchone()['count']
        pages = (total + per_page - 1) // per_page
        
        return render_template('stock.html',
                             products=products,
                             page=page,
                             pages=pages,
                             search=search,
                             sort=sort,
                             order=order)

    except Exception as e:
        flash('An error occurred while fetching stock.', 'danger')
        app.logger.error(f"Stock view error: {str(e)}")
        return redirect(url_for('dashboard'))
    finally:
        cur.close()

# Process Sales
@app.route('/sales', methods=['GET', 'POST'])
@login_required
def sales():
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        quantity = request.form.get('quantity')

        try:
            # Validate inputs
            if not product_id or not quantity:
                flash('Please select a product and enter quantity.', 'danger')
                return redirect(url_for('sales'))

            quantity = int(quantity)
            if quantity <= 0:
                flash('Please enter a valid quantity.', 'danger')
                return redirect(url_for('sales'))

            cur = get_db_cursor()
            
            # Start transaction
            mysql.connection.begin()

            # Get product details and lock the row
            cur.execute("""
                SELECT id, product_name, price, quantity as stock
                FROM products 
                WHERE id = %s 
                FOR UPDATE
            """, (product_id,))
            
            product = cur.fetchone()
            
            if not product:
                mysql.connection.rollback()
                flash('Product not found.', 'danger')
                return redirect(url_for('sales'))

            if product['stock'] < quantity:
                mysql.connection.rollback()
                flash(f'Insufficient stock. Only {product["stock"]} available.', 'danger')
                return redirect(url_for('sales'))

            # Calculate total amount
            total_amount = product['price'] * quantity

            # Update product stock
            cur.execute("""
                UPDATE products 
                SET quantity = quantity - %s 
                WHERE id = %s
            """, (quantity, product_id))

            # Record the sale
            cur.execute("""
                INSERT INTO sales 
                (product_id, user_id, quantity_sold, unit_price, total_amount, sale_time) 
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (product_id, session['user_id'], quantity, product['price'], total_amount))

            # Record stock movement
            cur.execute("""
                INSERT INTO stock_movements 
                (product_id, user_id, movement_type, quantity, reason, movement_time) 
                VALUES (%s, %s, 'out', %s, 'Sale', NOW())
            """, (product_id, session['user_id'], quantity))

            # Commit transaction
            mysql.connection.commit()
            
            flash(f'Sale of {quantity} {product["product_name"]} processed successfully!', 'success')

        except ValueError:
            mysql.connection.rollback()
            flash('Please enter a valid quantity.', 'danger')
        except Exception as e:
            mysql.connection.rollback()
            app.logger.error(f"Sales error: {str(e)}")
            flash('An error occurred while processing the sale.', 'danger')
        finally:
            cur.close()

        return redirect(url_for('sales'))

    # GET request - show sales form
    try:
        cur = get_db_cursor()
        cur.execute("""
            SELECT id, product_name, price, quantity 
            FROM products 
            WHERE quantity > 0 AND is_active = TRUE
            ORDER BY product_name
        """)
        products = cur.fetchall()
        
        return render_template('sales.html', products=products)
    except Exception as e:
        app.logger.error(f"Sales page error: {str(e)}")
        flash('Error loading products.', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        cur.close()

# Sales Report
@app.route('/report')
@login_required
def report():
    date_from = request.args.get('date_from', datetime.now().date().isoformat())
    date_to = request.args.get('date_to', datetime.now().date().isoformat())

    try:
        cur = get_db_cursor()
        cur.execute("""
            SELECT s.id, p.product_name, s.quantity_sold, p.price, 
                   (p.price * s.quantity_sold) as total, s.sale_time
            FROM sales s
            JOIN products p ON s.product_id = p.id
            WHERE DATE(s.sale_time) BETWEEN %s AND %s
            ORDER BY s.sale_time DESC
        """, (date_from, date_to))
        sales = cur.fetchall()

        # Calculate totals
        cur.execute("""
            SELECT COUNT(*) as count, 
                   SUM(p.price * s.quantity_sold) as total_amount,
                   SUM(s.quantity_sold) as total_quantity
            FROM sales s
            JOIN products p ON s.product_id = p.id
            WHERE DATE(s.sale_time) BETWEEN %s AND %s
        """, (date_from, date_to))
        summary = cur.fetchone()

        return render_template('report.html',
                             sales=sales,
                             summary=summary,
                             date_from=date_from,
                             date_to=date_to)

    except Exception as e:
        flash('An error occurred while generating the report.', 'danger')
        app.logger.error(f"Report error: {str(e)}")
        return redirect(url_for('dashboard'))
    finally:
        cur.close()

# Sales History
@app.route('/sales_history')
@login_required
def sales_history():
    page = request.args.get('page', 1, type=int)
    per_page = 10

    try:
        cur = get_db_cursor()
        cur.execute("""
            SELECT s.id, p.product_name, s.quantity_sold, 
                   p.price, s.sale_time, u.email as sold_by
            FROM sales s
            JOIN products p ON s.product_id = p.id
            JOIN users u ON s.user_id = u.id
            ORDER BY s.sale_time DESC
            LIMIT %s OFFSET %s
        """, (per_page, (page - 1) * per_page))
        sales = cur.fetchall()

        # Get total count for pagination
        cur.execute("SELECT COUNT(*) FROM sales")
        total = cur.fetchone()[0]
        pages = (total + per_page - 1) // per_page

        return render_template('sales_history.html',
                             sales=sales,
                             page=page,
                             pages=pages)

    except Exception as e:
        flash('An error occurred while fetching sales history.', 'danger')
        app.logger.error(f"Sales history error: {str(e)}")
        return redirect(url_for('dashboard'))
    finally:
        cur.close()

# API Routes
@app.route('/api/sales_data/<period>')
@login_required
def sales_data(period):
    try:
        cur = get_db_cursor()
        if period == 'week':
            cur.execute("""
                SELECT DATE(sale_time) as date,
                       SUM(total_amount) as total
                FROM sales
                WHERE sale_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                GROUP BY DATE(sale_time)
                ORDER BY date
            """)
        elif period == 'month':
            cur.execute("""
                SELECT DATE(sale_time) as date,
                       SUM(total_amount) as total
                FROM sales
                WHERE sale_time >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                GROUP BY DATE(sale_time)
                ORDER BY date
            """)
        
        data = cur.fetchall()
        return jsonify({
            'labels': [row['date'].strftime('%Y-%m-%d') for row in data],
            'values': [float(row['total']) for row in data]
        })
    except Exception as e:
        app.logger.error(f"API error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()

@app.route('/api/top_products')
@login_required
def top_products():
    try:
        cur = get_db_cursor()
        cur.execute("""
            SELECT p.product_name,
                   SUM(s.quantity_sold) as total_sold
            FROM products p
            JOIN sales s ON p.id = s.product_id
            GROUP BY p.id, p.product_name
            ORDER BY total_sold DESC
            LIMIT 5
        """)
        data = cur.fetchall()
        return jsonify({
            'labels': [row['product_name'] for row in data],
            'values': [row['total_sold'] for row in data]
        })
    except Exception as e:
        app.logger.error(f"API error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()

@app.route('/api/recent_sales')
@login_required
def recent_sales():
    try:
        cur = get_db_cursor()
        cur.execute("""
            SELECT p.product_name as product,
                   s.quantity_sold as quantity,
                   s.total_amount as amount,
                   s.sale_time as time
            FROM sales s
            JOIN products p ON s.product_id = p.id
            ORDER BY s.sale_time DESC
            LIMIT 5
        """)
        sales = cur.fetchall()
        return jsonify([{
            'product': sale['product'],
            'quantity': sale['quantity'],
            'amount': float(sale['amount']),
            'time': sale['time'].isoformat()
        } for sale in sales])
    except Exception as e:
        app.logger.error(f"API error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()

@app.route('/api/low_stock')
@login_required
def low_stock():
    try:
        cur = get_db_cursor()
        cur.execute("""
            SELECT id, product_name, quantity
            FROM products
            WHERE quantity < 10
            ORDER BY quantity ASC
            LIMIT 5
        """)
        items = cur.fetchall()
        return jsonify([{
            'id': item['id'],
            'product': item['product_name'],
            'stock': item['quantity']
        } for item in items])
    except Exception as e:
        app.logger.error(f"API error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()

if __name__ == "__main__":
    app.run(debug=True)
