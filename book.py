from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import mysql.connector
from datetime import datetime
import mysql.connector.pooling
from mysql.connector import Error
import json

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Needed for flash messages

# Database configuration with connection pooling
db_config = {
    'host': 'localhost',  # Your RDS endpoint
    'user': 'root',  # Your DB username
    'password': 'Surya@123',  # Your DB password
    'database': 'bookstore'  # Your DB name
}

cnxpool = mysql.connector.pooling.MySQLConnectionPool(pool_name="mypool",
                                                      pool_size=5,
                                                      **db_config)

@app.route("/test-db-connection")
def test_db_connection():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE();")  # Test query to check connection
        db_name = cursor.fetchone()
        cursor.close()
        conn.close()
        return f"Connected to the database: {db_name[0]}"
    except mysql.connector.Error as err:
        return f"Error: {err}"

# Function to establish a database connection
def get_db_connection():
    try:
        return cnxpool.get_connection()
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['POST','GET'])
def register():
    if request.method == 'POST':
        name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        default_address = request.form.get('address')
        mobile = request.form.get('phone')

        if not default_address:
            flash('Default address is required!')
            return redirect(url_for('register'))
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'INSERT INTO users (full_name, phone, email, password, address) VALUES (%s, %s, %s, %s, %s)',
            (name, mobile, email, password, default_address))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Thank you for registering!')
        return redirect(url_for('login'))

    return render_template('register.html')


import hashlib

# Admin configuration
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = hashlib.sha256("admin123".encode()).hexdigest()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')  # Serve the login page

    # Handle POST request (as previously defined)
    data = request.get_json()

    # Safely retrieve role, email, username, and password from the data
    role = data.get('role')
    email = data.get('email')  # This will be None for admin
    username = data.get('username')  # This will be None for user
    password = data.get('password')

    # Ensure that password is provided
    if not password:
        return jsonify(success=False, message="Password is required!"), 400

    # Admin login logic
    if role == 'admin':
        if not username:
            return jsonify(success=False, message="Username is required for admin login!"), 400
        if username == ADMIN_USERNAME and hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASSWORD_HASH:
            session['admin_logged_in'] = True  # Set session for admin
            return jsonify(success=True, message="Welcome, Admin!", redirect_url=url_for('admin_dashboard'))  # Return success for admin login
        else:
            return jsonify(success=False, message='Invalid admin credentials!'), 401

    # User login logic
    elif role == 'user':
        if not email:
            return jsonify(success=False, message="Email is required for user login!"), 400

        # Assuming you have a function to get user by email
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        # Check if user exists and verify password
        if user and user['password'] == password:  # Direct comparison
            session['user_id'] = user['user_id']  # Store user ID in session
            return jsonify(success=True, message="Login successful!", redirect_url=url_for('user'))  # Return success as JSON
        else:
            return jsonify(success=False, message='Invalid email or password!'), 401

    return jsonify(success=False, message='Invalid role specified!'), 400


@app.route('/user')
def user():
    return render_template('user.html')

@app.route('/cart', methods=['POST', 'GET'])
def cart():
    if 'user_id' not in session:
        return jsonify(success=False, error="User not logged in"), 401

    if request.method == 'POST':
        item_data = request.get_json()
        print(f"Received item data: {item_data}")  # Debug: Print received data

        # Validate input data
        if not all(key in item_data for key in ['name', 'price', 'quantity']):
            return jsonify(success=False, error="Missing required data"), 400

        try:
            item_name = item_data['name']
            item_price = float(item_data['price'])
            item_quantity = int(item_data['quantity'])
            print(f"Parsed item: name={item_name}, price={item_price}, quantity={item_quantity}")  # Debug: Print parsed item details
        except ValueError as e:
            print(f"Error parsing item data: {str(e)}")  # Debug: Print parsing error
            return jsonify(success=False, error=f"Invalid price or quantity: {str(e)}"), 400

        db = get_db_connection()
        if not db:
            return jsonify(success=False, error="Database connection failed"), 500

        try:
            with db.cursor() as cursor:
                # Check if a Pending order exists for the user
                cursor.execute("SELECT order_id FROM orders WHERE user_id = %s AND status = 'Pending' LIMIT 1", (session['user_id'],))
                existing_order = cursor.fetchone()

                if existing_order:
                    order_id = existing_order[0]
                    print(f"Existing order found: order_id={order_id}")  # Debug: Print existing order ID
                else:
                    # Create a new order if no Pending order exists
                    cursor.execute("INSERT INTO orders (user_id, total_amount, status) VALUES (%s, 0, 'Pending')", (session['user_id'],))
                    order_id = cursor.lastrowid
                    print(f"New order created: order_id={order_id}")  # Debug: Print new order ID

                # Check if the item already exists in the order
                cursor.execute("SELECT quantity FROM order_items WHERE order_id = %s AND book_title = %s", (order_id, item_name))
                existing_item = cursor.fetchone()

                if existing_item:
                    # Update existing item quantity
                    new_quantity = existing_item[0] + item_quantity
                    print(f"Updating existing item: order_id={order_id}, book_title={item_name}, new_quantity={new_quantity}")  # Debug: Print update details
                    cursor.execute("UPDATE order_items SET quantity = %s WHERE order_id = %s AND book_title = %s",
                                   (new_quantity, order_id, item_name))
                else:
                    # Insert new item into order_items
                    print(f"Inserting new item: order_id={order_id}, book_title={item_name}, quantity={item_quantity}, price={item_price}")  # Debug: Print insert details
                    cursor.execute("INSERT INTO order_items (order_id, book_title, quantity, price) VALUES (%s, %s, %s, %s)",
                                   (order_id, item_name, item_quantity, item_price))

                # Update the total amount in the orders table
                cursor.execute("UPDATE orders SET total_amount = (SELECT SUM(quantity * price) FROM order_items WHERE order_id = %s) WHERE order_id = %s",
                               (order_id, order_id))

                db.commit()
                print("Transaction committed successfully")  # Debug: Print commit success

            return jsonify(success=True, message="Item added to cart")
        except mysql.connector.Error as e:
            db.rollback()
            print(f"MySQL error: {e}")  # Debug: Print MySQL error
            return jsonify(success=False, error=f"Failed to update cart in database: {str(e)}"), 500
        except Exception as e:
            db.rollback()
            print(f"Unexpected error: {e}")  # Debug: Print unexpected error
            return jsonify(success=False, error=f"An unexpected error occurred: {str(e)}"), 500
        finally:
            db.close()
            print("Database connection closed")  # Debug: Print connection closure

    elif request.method == 'GET':
        # Handle retrieving cart items...
        # (Keep your existing GET logic here)        
        db = get_db_connection()
        if not db:
            return jsonify(success=False, error="Database connection failed"), 500

        try:
            with db.cursor(dictionary=True) as cursor:
                # Get the current Pending order
                cursor.execute("SELECT order_id FROM orders WHERE user_id = %s AND status = 'Pending' LIMIT 1", (session['user_id'],))
                order_id = cursor.fetchone()

                if order_id:
                    order_id = order_id['order_id']
                    cursor.execute("SELECT book_title as name, quantity, price FROM order_items WHERE order_id = %s", (order_id,))
                    cart_items = cursor.fetchall()

                    total_price = sum(float(item['price']) * item['quantity'] for item in cart_items)
                    return render_template('cart.html', cart_items=cart_items, total_price=total_price)
                else:
                    return render_template('cart.html', cart_items=[], total_price=0)
        except Exception as e:
            print(f"Database error: {e}")
            return jsonify(success=False, error="Failed to retrieve cart items"), 500
        finally:
            db.close()


@app.route('/update_cart', methods=['POST'])
def update_cart():
    if 'user_id' not in session:
        return jsonify(success=False, error="User not logged in"), 401

    user_id = session['user_id']
    book_title = request.form.get('book_title')
    action = request.form.get('action')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get the latest order for the user, either Pending or open
        cursor.execute("""
            SELECT order_id FROM orders 
            WHERE user_id = %s AND (status = 'Pending' OR status = 'open') 
            ORDER BY order_id DESC LIMIT 1
        """, (user_id,))
        order = cursor.fetchone()

        if not order:
            # Create a new order if none exists
            cursor.execute("INSERT INTO orders (user_id, total_amount, status) VALUES (%s, 0, 'Pending')", (user_id,))
            order_id = cursor.lastrowid
        else:
            order_id = order['order_id']

        # Get current quantity and price
        cursor.execute("SELECT quantity, price FROM order_items WHERE order_id = %s AND book_title = %s", (order_id, book_title))
        item = cursor.fetchone()

        if action == 'increase':
            if item:
                new_quantity = item['quantity'] + 1
                cursor.execute("UPDATE order_items SET quantity = %s WHERE order_id = %s AND book_title = %s", (new_quantity, order_id, book_title))
            else:
                cursor.execute("INSERT INTO order_items (order_id, book_title, quantity, price) VALUES (%s, %s, %s, (SELECT price FROM books WHERE title = %s))", (order_id, book_title, 1, book_title))
        
        elif action == 'decrease':
            if item:
                new_quantity = item['quantity'] - 1
                if new_quantity > 0:
                    cursor.execute("UPDATE order_items SET quantity = %s WHERE order_id = %s AND book_title = %s", (new_quantity, order_id, book_title))
                else:
                    cursor.execute("DELETE FROM order_items WHERE order_id = %s AND book_title = %s", (order_id, book_title))
            else:
                return jsonify(success=False, error="Item not found"), 404
        
        elif action == 'remove':
            if item:
                cursor.execute("DELETE FROM order_items WHERE order_id = %s AND book_title = %s", (order_id, book_title))
            else:
                return jsonify(success=False, error="Item not found"), 404

        # Update the total amount in the orders table
        cursor.execute("""
            UPDATE orders 
            SET total_amount = (
                SELECT COALESCE(SUM(quantity * price), 0) 
                FROM order_items 
                WHERE order_id = %s
            ) 
            WHERE order_id = %s
        """, (order_id, order_id))

        conn.commit()
        return jsonify(success=True)

    except Exception as e:
        conn.rollback()
        print(f"Error updating cart: {str(e)}")
        return jsonify(success=False, error="Failed to update cart"), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/new-address', methods=['POST'])
def new_address():
    if 'user_id' not in session:
        return jsonify(success=False, error="User not logged in"), 401
    
    data = request.json
    
    # Extract address details from JSON data
    full_name = data.get('full-name')
    address_line1 = data.get('address-line1')
    address_line2 = data.get('address-line2', '')  # Optional field
    city = data.get('city')
    state = data.get('state')
    zip_code = data.get('zip')
    phone = data.get('phone')

    # Combine address details into a single string
    full_address = f"{full_name}, {address_line1}, {address_line2}, {city}, {state}, {zip_code}, {phone}"

    conn = get_db_connection()
    if not conn:
        return jsonify(success=False, error="Database connection failed"), 500

    try:
        cursor = conn.cursor()
        
        # Insert the new address into the shipping table
        cursor.execute(
            'INSERT INTO shipping (user_id, delivery_address) VALUES (%s, %s)',
            (session['user_id'], full_address)
        )
        
        conn.commit()
        
        return jsonify(success=True, message="Address added successfully", address=full_address)
    
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify(success=False, error=f"Database error: {err}"), 500
    
    finally:
        cursor.close()
        conn.close()

@app.route('/checkout', methods=['GET'])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500

    try:
        cursor = conn.cursor(dictionary=True)

        # Fetch the current Pending order for the user
        cursor.execute("SELECT order_id, total_amount FROM orders WHERE user_id = %s AND status = 'Pending' LIMIT 1", (session['user_id'],))
        order = cursor.fetchone()

        if not order:
            return "No items in cart", 400

        # Fetch the cart items
        cursor.execute("SELECT book_title, quantity, price FROM order_items WHERE order_id = %s", (order['order_id'],))
        cart_items = cursor.fetchall()

        # Fetch the user's address from the users table
        cursor.execute("SELECT address FROM users WHERE user_id = %s", (session['user_id'],))
        user_address = cursor.fetchone()['address']

        # Fetch unique saved addresses for the user
        cursor.execute("SELECT DISTINCT delivery_address FROM shipping WHERE user_id = %s", (session['user_id'],))
        saved_addresses = [row['delivery_address'] for row in cursor.fetchall()]

        return render_template('checkout.html', 
                               cart_items=cart_items, 
                               total_amount=order['total_amount'], 
                               user_address=user_address,
                               saved_addresses=saved_addresses)

    except Exception as e:
        print(f"Error processing checkout: {str(e)}")
        return "Error processing checkout", 500
    finally:
        cursor.close()
        conn.close()


import logging

logging.basicConfig(filename='bookstore.log', level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

@app.route('/place-order', methods=['POST'])
def place_order():
    if 'user_id' not in session:
        return jsonify(success=False, error="User  not logged in"), 401

    conn = get_db_connection()
    if not conn:
        return jsonify(success=False, error="Database connection failed"), 500

    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)

        user_id = session['user_id']
        delivery_address = request.form.get('delivery_address')
        total_price = request.form.get('total_price', 0)

        if not delivery_address:
            return jsonify(success=False, error="No delivery address provided"), 400

        # Start transaction
        cursor.execute("START TRANSACTION")

        # Get current Pending order
        cursor.execute(
            "SELECT order_id FROM orders WHERE user_id = %s AND status = 'Pending' LIMIT 1",
            (user_id,)
        )
        pending_order = cursor.fetchone()

        if pending_order:
            order_id = pending_order['order_id']

            # Update existing order
            cursor.execute(
                "UPDATE orders SET total_amount = %s, status = 'Pending' WHERE order_id = %s",  # Set status to Pending
                (total_price, order_id)
            )

            # Update order_items status to 'ordered'
            cursor.execute(
                "UPDATE order_items SET status = 'ordered' WHERE order_id = %s AND status = 'in_cart'",
                (order_id,)
            )

            # Create shipping record
            cursor.execute(
                '''INSERT INTO shipping 
                   (user_id, order_id, delivery_address, payment_method, order_date, total_price) 
                   VALUES (%s, %s, %s, 'Cash on Delivery', NOW(), %s)''',
                (user_id, order_id, delivery_address, total_price)
            )

            conn.commit()
            return jsonify(success=True, message="Order placed successfully", redirect_url=url_for('user_dashboard'))
        else:
            # Create a new order if no Pending order exists
            cursor.execute(
                "INSERT INTO orders (user_id, total_amount, status) VALUES (%s, %s, 'Pending')",  # Set status to Pending
                (user_id, total_price)
            )
            order_id = cursor.lastrowid

            # Create shipping record for new order
            cursor.execute(
                '''INSERT INTO shipping 
                   (user_id, order_id, delivery_address, payment_method, order_date, total_price) 
                   VALUES (%s, %s, %s, 'Cash on Delivery', NOW(), %s)''',
                (user_id, order_id, delivery_address, total_price)
            )

            conn.commit()
            return jsonify(success=True, message="Order placed successfully", redirect_url=url_for('user_dashboard'))

    except mysql.connector.Error as e:
        if conn:
            conn.rollback()
        return jsonify(success=False, error=f"Database error: {str(e)}"), 500

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify(success=False, error=f"Unexpected error: {str(e)}"), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/myorders')
def user_dashboard():
    if 'user_id' not in session:
        flash('You need to log in to access your orders!')
        return redirect(url_for('login'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Updated query to include book titles
        cursor.execute('''
            SELECT 
                o.order_id,
                o.total_amount,
                o.status,
                s.order_date,
                s.delivery_address,
                GROUP_CONCAT(
                    DISTINCT CONCAT(oi.book_title, ' (Qty: ', oi.quantity, ')')
                    SEPARATOR ', '
                ) as book_titles
            FROM orders o
            LEFT JOIN shipping s ON s.order_id = o.order_id
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.user_id = %s
            GROUP BY o.order_id, o.total_amount, o.status, s.order_date, s.delivery_address
            ORDER BY o.order_id DESC
        ''', (session['user_id'],))

        orders = cursor.fetchall()

        formatted_orders = []
        for order in orders:
            formatted_order = {
                'order_id': order['order_id'],
                'total_amount': f"${float(order['total_amount']):.2f}",
                'status': order['status'],
                'order_date': order['order_date'].strftime('%Y-%m-%d %H:%M') if order['order_date'] else 'N/A',
                'delivery_address': order['delivery_address'] or 'N/A',
                'book_titles': order['book_titles'] or 'No books'
            }
            formatted_orders.append(formatted_order)

        return render_template('myorders.html', orders=formatted_orders)

    except Exception as e:
        print(f"Error in user_dashboard: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('An error occurred while fetching your orders.')
        return redirect(url_for('home'))

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# Updated route in book.py

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_logged_in' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        flash('Database connection failed')
        return redirect(url_for('admin_dashboard'))

    try:
        cursor = conn.cursor(dictionary=True)

        # Fetch summary statistics (keep this part unchanged)
        cursor.execute("""
            SELECT
                (SELECT COUNT(DISTINCT email) FROM users) as total_users,
                (SELECT COUNT(*) FROM orders WHERE status = 'Pending') as pending_orders_count,
                (SELECT COUNT(*) FROM orders WHERE status IN ('Shipped', 'Delivered')) as successful_orders_count,
                (SELECT COUNT(*) FROM orders WHERE status = 'Cancelled') as cancelled_orders_count,
                (SELECT COUNT(*) FROM orders) as total_orders_count,
                COALESCE(SUM(CASE WHEN status IN ('Shipped', 'Delivered') THEN total_amount ELSE 0 END), 0) as total_revenue,
                (SELECT COALESCE(AVG(total_amount), 0) FROM orders) as average_order_value,
                (SELECT COUNT(DISTINCT delivery_address) FROM shipping) as total_shipping_addresses
            FROM orders
        """)
        stats = cursor.fetchone()

        # Updated query for pending orders to avoid duplicates
        cursor.execute("""
            SELECT DISTINCT
                o.order_id,
                u.full_name as customer_name,
                o.total_amount,
                o.status,
                s.delivery_address,
                s.order_date,
                GROUP_CONCAT(DISTINCT 
                    CONCAT(oi.book_title, ' (Qty: ', oi.quantity, ')')
                    SEPARATOR ', '
                ) as book_titles
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            LEFT JOIN shipping s ON o.order_id = s.order_id
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.status = 'Pending'
            GROUP BY o.order_id, u.full_name, o.total_amount, o.status, s.delivery_address, s.order_date
            ORDER BY o.order_id DESC
        """)
        pending_orders = cursor.fetchall()

        # Updated query for successful orders
        cursor.execute("""
            SELECT DISTINCT
                o.order_id,
                u.full_name as customer_name,
                o.total_amount,
                o.status,
                s.delivery_address,
                s.order_date,
                GROUP_CONCAT(DISTINCT 
                    CONCAT(oi.book_title, ' (Qty: ', oi.quantity, ')')
                    SEPARATOR ', '
                ) as book_titles
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            LEFT JOIN shipping s ON o.order_id = s.order_id
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.status IN ('Shipped', 'Delivered')
            GROUP BY o.order_id, u.full_name, o.total_amount, o.status, s.delivery_address, s.order_date
            ORDER BY s.order_date DESC
            LIMIT 10
        """)
        successful_orders = cursor.fetchall()

        # Updated query for cancelled orders
        cursor.execute("""
            SELECT DISTINCT
                o.order_id,
                u.full_name as customer_name,
                o.total_amount,
                o.status,
                s.delivery_address,
                s.order_date,
                GROUP_CONCAT(DISTINCT 
                    CONCAT(oi.book_title, ' (Qty: ', oi.quantity, ')')
                    SEPARATOR ', '
                ) as book_titles
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            LEFT JOIN shipping s ON o.order_id = s.order_id
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.status = 'Cancelled'
            GROUP BY o.order_id, u.full_name, o.total_amount, o.status, s.delivery_address, s.order_date
            ORDER BY s.order_date DESC
        """)
        cancelled_orders = cursor.fetchall()

        return render_template('admin.html',
                    total_users=stats['total_users'],
                    pending_orders_count=stats['pending_orders_count'],
                    successful_orders_count=stats['successful_orders_count'],
                    cancelled_orders_count=stats['cancelled_orders_count'],
                    total_orders_count=stats['total_orders_count'],
                    average_order_value=stats['average_order_value'],
                    total_shipping_addresses=stats['total_shipping_addresses'],
                    total_revenue=stats['total_revenue'],
                    pending_orders=pending_orders,
                    successful_orders=successful_orders,
                    cancelled_orders=cancelled_orders)

    except Exception as e:
        print(f"Error in admin dashboard: {str(e)}")
        flash('An error occurred while fetching dashboard data')
        return redirect(url_for('login'))

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Update the manage_users route:
@app.route('/admin/users')
def manage_users():
    if 'admin_logged_in' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        flash('Database connection failed')
        return redirect(url_for('admin_dashboard'))

    try:
        cursor = conn.cursor(dictionary=True)

        # Fetch all registered users with their order statistics
        cursor.execute("""
            SELECT 
                u.user_id,
                u.full_name,
                u.email,
                u.phone,
                u.address,
                COUNT(DISTINCT o.order_id) as total_orders,
                COALESCE(SUM(o.total_amount), 0) as total_spent
            FROM users u
            LEFT JOIN orders o ON u.user_id = o.user_id
            GROUP BY u.user_id, u.full_name, u.email, u.phone, u.address
            ORDER BY u.user_id DESC
        """)
        users = cursor.fetchall()
        # Debugging: Print the fetched users
        print("Fetched Users:", users)

        return render_template('manage_users.html', users=users)

    except Exception as e:
        print(f"Error fetching users: {e}")
        flash('An error occurred while fetching user data.')
        return redirect(url_for('admin_dashboard'))

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/update_order_status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    new_status = request.form.get('new_status')

    # Validate the new status
    valid_statuses = ['Pending', 'Shipped', 'Delivered', 'Cancelled']
    if new_status not in valid_statuses:
        return jsonify(success=False, message="Invalid status"), 400

    # Connect to the database
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Update the order status in the database
        cursor.execute("""
            UPDATE orders
            SET status = %s
            WHERE order_id = %s
        """, (new_status, order_id))

        # Check if any rows were affected
        if cursor.rowcount == 0:
            return jsonify(success=False, message="No order found with the specified ID"), 404

        conn.commit()

        return jsonify(success=True, message="Order status updated successfully")
    
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    
    finally:
        cursor.close()
        conn.close()

@app.route('/admin')
def admin_page():
    return redirect(url_for('admin_dashboard'))  # Redirect /admin to /admin/dashboard

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('login'))  # Redirect to login after logout

@app.route('/logout')
def user_logout():
    # Clear the user session
    session.pop('user_id', None)  # Remove user ID from session
    session.pop('user_email', None)  # Remove user email from session if stored
    flash('You have been logged out successfully.')  # Optional: Flash message to inform the user
    return redirect(url_for('login'))  # Redirect to the login page

if __name__ == '__main__':
    app.run(debug=True)
