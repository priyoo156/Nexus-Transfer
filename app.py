"""
Nexus Asynchronous Printing System - Production Backend
========================================================
Complete rewrite with comprehensive bug fixes, security improvements,
and production-grade code patterns.

Bug Fixes Implemented:
1. Enhanced QR code generation with robust error handling and logging
2. Replaced random token generation with UUID4 format
3. Added comprehensive token validation regex pattern
4. Fixed database transaction handling with proper rollback
5. Improved error logging and diagnostics throughout
6. Refactored duplicate database code into reusable helpers
7. Enhanced security with strict input validation
8. Proper HTTP status codes for all error cases
9. Fixed admin scanner state machine transitions
10. Added comprehensive exception handling and error recovery
"""

from flask import Flask, send_from_directory, render_template, request, jsonify, redirect, session, send_file
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
import webbrowser
from threading import Timer
from io import BytesIO
import os
import sqlite3
import uuid
import re
import logging
import qrcode
from PIL import Image

# ═════════════════════════════════════════════════════════════════════════════
# LOGGING CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════════════════════════════
# FLASK APP INITIALIZATION
# ═════════════════════════════════════════════════════════════════════════════

app = Flask(
    __name__,
    static_folder='static',
    template_folder='templates'
)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "nexus_secret_2026"
)
app.permanent_session_lifetime = timedelta(days=7)

# ═════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════════

UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DATABASE = os.path.join(app.root_path, "nexus.db")

# Token body uses 8 uppercase alphanumeric characters after the NEXUS- prefix
TOKEN_BODY_LENGTH = 8
TOKEN_PATTERN = re.compile(rf'^NEXUS-[A-Z0-9]{{{TOKEN_BODY_LENGTH}}}$')

ALLOWED_UPLOAD_EXTENSIONS = {'.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png'}

# Valid order status transitions
VALID_STATUS_TRANSITIONS = {
    "Pending": ["Printing"],
    "Printing": ["Completed"],
    "Completed": []
}

ALLOWED_STATUSES = {"Pending", "Printing", "Completed"}

# ═════════════════════════════════════════════════════════════════════════════
# UTILITY & VALIDATION FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════


def validate_token(token):
    """
    Validate order token format using regex.

    Args:
        token: Token string to validate

    Returns:
        Cleaned token (uppercase, stripped) or None if invalid
    """
    if token is None:
        return None

    cleaned = str(token).strip().upper()

    if not TOKEN_PATTERN.fullmatch(cleaned):
        return None

    return cleaned


def is_valid_status_transition(current_status, new_status):
    """
    Validate order status transitions.
    
    Allowed transitions:
    - Pending → Printing
    - Printing → Completed
    - Completed cannot transition
    
    Args:
        current_status: Current order status
        new_status: Desired new status
        
    Returns:
        Boolean indicating if transition is valid
    """
    if not current_status or current_status not in ALLOWED_STATUSES:
        current_status = "Pending"
    
    if new_status not in ALLOWED_STATUSES:
        return False
    
    allowed_next = VALID_STATUS_TRANSITIONS.get(current_status, [])
    return new_status in allowed_next


# ═════════════════════════════════════════════════════════════════════════════
# DATABASE FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════


def get_db():
    """
    Get thread-safe database connection.
    
    Returns:
        sqlite3.Connection with row factory enabled
    """
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def close_db(conn):
    """
    Safely close database connection.
    
    Args:
        conn: Database connection to close
    """
    if conn:
        try:
            conn.close()
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")


def row_to_order(row):
    """
    Convert database row to order dictionary.
    
    Args:
        row: sqlite3.Row object from database
        
    Returns:
        Dictionary with order data
    """
    original = row["original_filename"] or row["filename"] or "document"
    stored = row["stored_filename"] or ""
    status = row["status"] or "Pending"
    
    return {
        "token": row["order_id"],
        "order_id": row["order_id"],
        "filename": original,
        "original_filename": original,
        "stored_filename": stored,
        "file_url": f"/uploads/{stored}" if stored else "",
        "download_url": f"/uploads/{stored}?download=1" if stored else "",
        "copies": row["copies"],
        "pages": row["total_pages"],
        "total_pages": row["total_pages"],
        "color": row["mode"],
        "mode": row["mode"],
        "total": row["total"],
        "status": status,
        "uploaded_at": row["uploaded_at"] or ""
    }


def sanitize_filename(filename):
    if not filename:
        return None
    safe_name = secure_filename(str(filename).strip())
    return safe_name if safe_name else None


def is_allowed_upload_extension(filename):
    _, extension = os.path.splitext(str(filename or ''))
    return extension.lower() in ALLOWED_UPLOAD_EXTENSIONS


def fetch_order_row(conn, token):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (token,))
    return cursor.fetchone()


def generate_unique_order_token(conn, max_attempts=10):
    cursor = conn.cursor()
    for _ in range(max_attempts):
        order_id = f"NEXUS-{uuid.uuid4().hex[:TOKEN_BODY_LENGTH].upper()}"
        if not TOKEN_PATTERN.match(order_id):
            continue
        cursor.execute("SELECT 1 FROM orders WHERE order_id = ?", (order_id,))
        if cursor.fetchone() is None:
            return order_id

    raise RuntimeError("Unable to generate unique order token")


def parse_int(value, default=0, minimum=None):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    return number


def parse_float(value, default=0.0, minimum=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    return number


def current_utc_timestamp():
    return datetime.utcnow().isoformat(timespec='seconds')


def init_db():
    """Initialize database with production schema."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Create orders table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE NOT NULL,
            filename TEXT,
            original_filename TEXT,
            stored_filename TEXT,
            mode TEXT,
            copies INTEGER,
            total_pages INTEGER,
            total REAL,
            status TEXT DEFAULT 'Pending',
            uploaded_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Get existing columns
        cursor.execute("PRAGMA table_info(orders)")
        columns = {row[1] for row in cursor.fetchall()}
        
        # Add missing columns (migrations)
        migrations = {
            "original_filename": "ALTER TABLE orders ADD COLUMN original_filename TEXT",
            "stored_filename": "ALTER TABLE orders ADD COLUMN stored_filename TEXT",
            "total_pages": "ALTER TABLE orders ADD COLUMN total_pages INTEGER",
            "uploaded_at": "ALTER TABLE orders ADD COLUMN uploaded_at TEXT",
            "created_at": "ALTER TABLE orders ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        }
        
        for column, sql in migrations.items():
            if column not in columns:
                try:
                    cursor.execute(sql)
                    logger.info(f"Added column: {column}")
                except sqlite3.Error:
                    pass
        
        # Data cleanup: Fill NULL values with sensible defaults
        cursor.execute(
            "UPDATE orders SET original_filename = filename WHERE original_filename IS NULL OR original_filename = ''"
        )
        cursor.execute(
            "UPDATE orders SET status = 'Pending' WHERE status IS NULL OR status = ''"
        )
        cursor.execute(
            "UPDATE orders SET uploaded_at = ? WHERE uploaded_at IS NULL OR uploaded_at = ''",
            (datetime.now().isoformat(timespec='seconds'),)
        )
        
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        conn.rollback()
        logger.error(f"Database initialization error: {e}")
    finally:
        close_db(conn)


# Initialize database on startup
init_db()

# ═════════════════════════════════════════════════════════════════════════════
# DECORATORS
# ═════════════════════════════════════════════════════════════════════════════


def admin_required(fn):
    """
    Decorator to protect admin-only routes.
    
    Returns:
        401 JSON response if not authenticated
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('admin'):
            protected_paths = (
                "/orders",
                "/order/",
                "/print/",
                "/start-print/",
                "/complete/",
                "/delete/",
                "/clear",
                "/uploads/"
            )
            
            # Check if current path is protected
            if any(request.path.startswith(path) for path in protected_paths):
                return jsonify({
                    "success": False,
                    "error": "Admin authentication required"
                }), 401
            
            return redirect('/admin-login')
        
        return fn(*args, **kwargs)
    
    return wrapper


# ═════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION ROUTES
# ═════════════════════════════════════════════════════════════════════════════


@app.route('/admin-login')
def admin_login():
    """Render admin login page."""
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    """
    Handle admin login with credentials.
    
    Credentials: admin / nexus123
    """
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    
    if not username or not password:
        return render_template(
            'login.html',
            error="Username and password required"
        ), 400
    
    if username == "admin" and password == "nexus123":
        session.permanent = request.form.get('remember') == '1'
        session['admin'] = True
        logger.info(f"Admin login successful at {datetime.now()}")
        return redirect('/admin')
    
    logger.warning(f"Failed login attempt for user: {username}")
    return render_template(
        'login.html',
        error="Invalid username or password"
    ), 401


@app.route('/logout')
def logout():
    """Clear admin session and redirect to login."""
    logger.info(f"Admin logout at {datetime.now()}")
    session.clear()
    return redirect('/admin-login')


# ═════════════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ═════════════════════════════════════════════════════════════════════════════


@app.route('/')
def index():
    """Render customer home page."""
    return render_template('nexus.html')


@app.route('/admin')
@admin_required
def admin():
    """Render admin control panel."""
    return render_template('admin.html')


@app.route('/health')
def health_check():
    """Health check endpoint for monitoring."""
    try:
        # Verify database connection
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders")
        close_db(conn)
        
        return jsonify({
            "status": "healthy",
            "service": "Nexus Printer Backend",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 503


# ═════════════════════════════════════════════════════════════════════════════
# FILE UPLOAD & MANAGEMENT ROUTES
# ═════════════════════════════════════════════════════════════════════════════


@app.route('/upload', methods=['POST'])
def upload_file():
    """
    Handle customer file upload.
    
    Validates and stores file, returns metadata for order creation.
    
    Returns:
        JSON with file metadata and secure storage name
    """
    if 'file' not in request.files:
        logger.warning("Upload request without file field")
        return jsonify({
            "success": False,
            "message": "No file selected"
        }), 400
    
    file = request.files['file']
    
    if not file or not file.filename:
        logger.warning("Upload request with empty filename")
        return jsonify({
            "success": False,
            "message": "Empty filename"
        }), 400
    
    # Secure and validate filename
    original_filename = secure_filename(file.filename) or "document"
    
    if not original_filename or len(original_filename) == 0:
        logger.warning(f"Invalid filename after sanitization: {file.filename}")
        return jsonify({
            "success": False,
            "message": "Invalid filename"
        }), 400
    
    # Generate unique storage name
    _, ext = os.path.splitext(original_filename)
    stored_filename = f"{uuid.uuid4().hex}{ext.lower()}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
    
    try:
        file.save(filepath)
        logger.info(f"File uploaded: {original_filename} → {stored_filename}")
        
        return jsonify({
            "success": True,
            "message": "File uploaded successfully",
            "filename": original_filename,
            "original_filename": original_filename,
            "stored_filename": stored_filename
        })
    except Exception as e:
        logger.error(f"File save failed: {e}")
        return jsonify({
            "success": False,
            "message": f"File save failed"
        }), 500


@app.route('/uploads/<filename>')
@admin_required
def serve_uploaded_file(filename):
    """
    Serve uploaded files with security checks.
    
    Prevents path traversal attacks.
    Requires admin authentication.
    """
    safe_name = secure_filename(filename)
    
    if not safe_name or safe_name != filename:
        logger.warning(f"Invalid filename in upload request: {filename}")
        return jsonify({"error": "Invalid filename"}), 400
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
    
    # Prevent path traversal
    if not os.path.abspath(filepath).startswith(os.path.abspath(app.config['UPLOAD_FOLDER'])):
        logger.warning(f"Path traversal attempt: {filename}")
        return jsonify({"error": "Access denied"}), 403
    
    if not os.path.exists(filepath):
        logger.warning(f"File not found: {filename}")
        return jsonify({"error": "File not found"}), 404
    
    download = request.args.get('download') == '1'
    
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        safe_name,
        as_attachment=download
    )


# ═════════════════════════════════════════════════════════════════════════════
# ORDER MANAGEMENT ROUTES
# ═════════════════════════════════════════════════════════════════════════════


@app.route('/create-order', methods=['POST'])
def create_order():
    """
    Create a new print order.

    Validates upload metadata, generates a unique token, and stores the order.
    """
    if not request.is_json:
        logger.warning("Create order request without JSON content type")
        return jsonify({
            "success": False,
            "error": "Content-Type must be application/json"
        }), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        logger.warning("Create order request without JSON payload or invalid JSON")
        return jsonify({
            "success": False,
            "error": "Missing or invalid JSON payload"
        }), 400

    original_filename = sanitize_filename(data.get('original_filename') or data.get('filename') or 'document')
    stored_filename = sanitize_filename(data.get('stored_filename'))
    mode = str(data.get('mode') or 'bw').strip()
    copies = parse_int(data.get('copies'), default=1, minimum=1)
    total_pages = parse_int(data.get('total_pages'), default=1, minimum=1)
    total = parse_float(data.get('total'), default=0.0, minimum=0.0)

    if not original_filename:
        logger.warning("Create order request with invalid original filename")
        return jsonify({
            "success": False,
            "error": "Invalid original filename"
        }), 400

    if not stored_filename or not is_allowed_upload_extension(stored_filename):
        logger.warning(f"Create order request with invalid stored filename: {stored_filename}")
        return jsonify({
            "success": False,
            "error": "Invalid stored filename"
        }), 400

    upload_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
    if not os.path.isfile(upload_path):
        logger.warning(f"Create order request with missing upload file: {stored_filename}")
        return jsonify({
            "success": False,
            "error": "Uploaded file not found"
        }), 400

    conn = get_db()
    try:
        cursor = conn.cursor()
        order_id = generate_unique_order_token(conn)

        cursor.execute('''
        INSERT INTO orders
        (order_id, filename, original_filename, stored_filename, mode, copies, total_pages, total, status, uploaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            order_id,
            original_filename,
            original_filename,
            stored_filename,
            mode,
            copies,
            total_pages,
            total,
            "Pending",
            current_utc_timestamp()
        ))

        conn.commit()
        logger.info(f"Order created: {order_id} | {original_filename} | ₹{total}")

        return jsonify({
            "success": True,
            "order_id": order_id,
            "uploaded_at": current_utc_timestamp()
        })

    except sqlite3.IntegrityError:
        conn.rollback()
        logger.error(f"Duplicate order token generated: {order_id}")
        return jsonify({
            "success": False,
            "error": "Order creation failed (duplicate token)"
        }), 409

    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Database error creating order: {e}")
        return jsonify({
            "success": False,
            "error": "Database error"
        }), 500

    finally:
        close_db(conn)


@app.route('/order/<token>')
@admin_required
def get_order(token):
    """
    Get order details by token.
    
    Args:
        token: Order token (NEXUS-XXXXXXXX)
        
    Returns:
        JSON with full order details or 404 if not found
    """
    clean_token = validate_token(token)
    
    if not clean_token:
        logger.warning(f"Invalid token format in get_order: {token}")
        return jsonify({
            "success": False,
            "error": "Invalid token format"
        }), 400
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (clean_token,))
        order = cursor.fetchone()
        
        if not order:
            logger.warning(f"Order not found: {clean_token}")
            return jsonify({
                "success": False,
                "error": "Order not found"
            }), 404
        
        return jsonify(row_to_order(order))
    
    except sqlite3.Error as e:
        logger.error(f"Database error fetching order {clean_token}: {e}")
        return jsonify({
            "success": False,
            "error": "Database error"
        }), 500
    
    finally:
        close_db(conn)


@app.route('/status/<token>')
def get_order_status(token):
    """Return the latest public status for a print order."""
    clean_token = validate_token(token)

    if not clean_token:
        return jsonify({
            "success": False,
            "error": "Invalid token format"
        }), 400

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM orders WHERE order_id = ?", (clean_token,))
        row = cursor.fetchone()

        if not row:
            return jsonify({
                "success": False,
                "error": "Order not found"
            }), 404

        status = row["status"] or "Pending"
        return jsonify({
            "success": True,
            "token": clean_token,
            "status": status
        })
    except sqlite3.Error as e:
        logger.error(f"Database error fetching status {clean_token}: {e}")
        return jsonify({
            "success": False,
            "error": "Database error"
        }), 500
    finally:
        close_db(conn)


@app.route('/orders')
@admin_required
def get_orders():
    """
    Get all orders with statistics.
    
    Returns:
        JSON with orders list and summary stats
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Get all orders (newest first)
        cursor.execute("SELECT * FROM orders ORDER BY uploaded_at DESC, id DESC")
        orders = [row_to_order(row) for row in cursor.fetchall()]
        
        # Get statistics
        stats_query = cursor.execute('''
            SELECT
                COUNT(*) AS total_orders,
                SUM(CASE WHEN LOWER(status) = 'completed' THEN 1 ELSE 0 END) AS printed_orders,
                SUM(CASE WHEN LOWER(status) = 'pending' THEN 1 ELSE 0 END) AS pending_orders,
                COALESCE(SUM(total), 0) AS total_revenue
            FROM orders
        ''')
        
        stats_row = stats_query.fetchone()
        
        stats = {
            "total_orders": stats_row["total_orders"] or 0,
            "pending_orders": stats_row["pending_orders"] or 0,
            "printed_orders": stats_row["printed_orders"] or 0,
            "total_revenue": stats_row["total_revenue"] or 0
        }
        
        logger.info(f"Orders fetched: {stats['total_orders']} total")
        
        return jsonify({
            "orders": orders,
            "stats": stats
        })
    
    except sqlite3.Error as e:
        logger.error(f"Database error fetching orders: {e}")
        return jsonify({
            "success": False,
            "error": "Database error"
        }), 500
    
    finally:
        close_db(conn)


@app.route('/stats')
def stats():
    """
    Get dashboard statistics (public endpoint).
    
    Returns:
        JSON with order counts and revenue
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        stats_row = cursor.execute('''
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='Pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status='Printing' THEN 1 ELSE 0 END) AS printing,
                SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) AS completed,
                COALESCE(SUM(total), 0) AS revenue
            FROM orders
        ''').fetchone()
        
        return jsonify({
            "total": stats_row["total"] or 0,
            "pending": stats_row["pending"] or 0,
            "printing": stats_row["printing"] or 0,
            "completed": stats_row["completed"] or 0,
            "revenue": stats_row["revenue"] or 0
        })
    
    except sqlite3.Error as e:
        logger.error(f"Database error fetching stats: {e}")
        return jsonify({
            "success": False,
            "error": "Stats error"
        }), 500
    
    finally:
        close_db(conn)



# ═════════════════════════════════════════════════════════════════════════════
# QR CODE GENERATION ROUTE - CRITICAL FOR PRINTING SYSTEM
# ═════════════════════════════════════════════════════════════════════════════


@app.route('/qr-code', methods=['POST'])
def qr_code():
    """
    Generate PNG QR code for a validated order token.

    This endpoint only accepts POST requests with JSON body containing a valid
    NEXUS token. It verifies that the order exists before returning a PNG image.
    """
    if not request.is_json:
        logger.warning("QR code request without JSON content type")
        return jsonify({
            "success": False,
            "error": "Content-Type must be application/json"
        }), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        logger.warning("QR code request without JSON payload or invalid JSON")
        return jsonify({
            "success": False,
            "error": "Missing or invalid JSON payload"
        }), 400

    raw_token = data.get('token')
    if isinstance(raw_token, dict):
        raw_token = raw_token.get('token')
    elif isinstance(raw_token, (list, tuple)):
        raw_token = raw_token[0] if raw_token else None

    clean_token = validate_token(raw_token)
    if not clean_token:
        logger.warning(f"QR request with invalid token: {raw_token}")
        return jsonify({
            "success": False,
            "error": "Invalid token format. Expected NEXUS-XXXXXXXX"
        }), 400

    conn = get_db()
    try:
        order = fetch_order_row(conn, clean_token)
        if not order:
            logger.warning(f"QR requested for missing order: {clean_token}")
            return jsonify({
                "success": False,
                "error": "Order not found"
            }), 404

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4
        )
        qr.add_data(clean_token)
        qr.make(fit=True)

        img = qr.make_image(fill_color='black', back_color='white')
        if img.mode != 'RGB':
            img = img.convert('RGB')

        buffer = BytesIO()
        img.save(buffer, format='PNG', optimize=False)
        buffer.seek(0)

        logger.info(f"QR code generated successfully: {clean_token}")
        return send_file(
            buffer,
            mimetype='image/png',
            as_attachment=False,
            download_name='qr-token.png'
        )

    except sqlite3.Error as e:
        logger.error(f"Database error checking order for QR code {clean_token}: {e}")
        return jsonify({
            "success": False,
            "error": "Database error"
        }), 500

    except Exception as e:
        logger.error(f"QR code generation failed for {clean_token}: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "QR code generation failed"
        }), 500

    finally:
        close_db(conn)


# ═════════════════════════════════════════════════════════════════════════════
# PRINT STATUS MANAGEMENT ROUTES
# ═════════════════════════════════════════════════════════════════════════════


@app.route('/start-print/<token>', methods=['POST'])
@admin_required
def start_print(token):
    """
    Start printing order (Pending → Printing transition).
    
    Validates status transition before updating.
    Only allows: Pending → Printing
    
    Args:
        token: Order token (NEXUS-XXXXXXXX)
        
    Returns:
        JSON with updated status or error
    """
    clean_token = validate_token(token)
    
    if not clean_token:
        logger.warning(f"Invalid token format in start_print: {token}")
        return jsonify({
            "success": False,
            "error": "Invalid token format"
        }), 400
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Get current status
        cursor.execute("SELECT status FROM orders WHERE order_id = ?", (clean_token,))
        row = cursor.fetchone()
        
        if not row:
            logger.warning(f"Order not found for start_print: {clean_token}")
            return jsonify({
                "success": False,
                "error": "Order not found"
            }), 404
        
        current_status = row["status"]
        
        # Validate transition
        if not is_valid_status_transition(current_status, "Printing"):
            logger.warning(f"Invalid transition {current_status}→Printing for {clean_token}")
            return jsonify({
                "success": False,
                "error": f"Cannot transition from {current_status} to Printing"
            }), 409
        
        # Update status
        cursor.execute("UPDATE orders SET status = 'Printing' WHERE order_id = ?", (clean_token,))
        conn.commit()
        
        if cursor.rowcount == 0:
            logger.error(f"Order not found after fetch: {clean_token}")
            return jsonify({
                "success": False,
                "error": "Order not found"
            }), 404
        
        logger.info(f"Order started printing: {clean_token} (Pending→Printing)")
        
        return jsonify({
            "success": True,
            "status": "Printing"
        })
    
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Database error starting print for {clean_token}: {e}")
        return jsonify({
            "success": False,
            "error": "Database error"
        }), 500
    
    finally:
        close_db(conn)


@app.route('/complete/<token>', methods=['POST', 'GET'])
@admin_required
def complete_order(token):
    """
    Mark order as completed (Printing → Completed transition).
    
    Validates status transition before updating.
    Only allows: Printing → Completed
    
    Args:
        token: Order token (NEXUS-XXXXXXXX)
        
    Returns:
        JSON with updated status or error
    """
    clean_token = validate_token(token)
    
    if not clean_token:
        logger.warning(f"Invalid token format in complete_order: {token}")
        return jsonify({
            "success": False,
            "error": "Invalid token format"
        }), 400
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Get current status
        cursor.execute("SELECT status FROM orders WHERE order_id = ?", (clean_token,))
        row = cursor.fetchone()
        
        if not row:
            logger.warning(f"Order not found for complete_order: {clean_token}")
            return jsonify({
                "success": False,
                "error": "Order not found"
            }), 404
        
        current_status = row["status"]
        
        # Validate transition
        if not is_valid_status_transition(current_status, "Completed"):
            logger.warning(f"Invalid transition {current_status}→Completed for {clean_token}")
            return jsonify({
                "success": False,
                "error": f"Cannot transition from {current_status} to Completed"
            }), 409
        
        # Update status
        cursor.execute("UPDATE orders SET status = 'Completed' WHERE order_id = ?", (clean_token,))
        conn.commit()
        
        if cursor.rowcount == 0:
            logger.error(f"Order not found after fetch: {clean_token}")
            return jsonify({
                "success": False,
                "error": "Order not found"
            }), 404
        
        logger.info(f"Order completed: {clean_token} (Printing→Completed)")
        
        return jsonify({
            "success": True,
            "status": "Completed"
        })
    
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Database error completing order {clean_token}: {e}")
        return jsonify({
            "success": False,
            "error": "Database error"
        }), 500
    
    finally:
        close_db(conn)


@app.route('/print/<token>')
@admin_required
def print_order(token):
    """
    Legacy endpoint: Mark order as completed immediately.
    
    For backward compatibility, marks Pending or Printing as Completed.
    New code should use /start-print/<token> → /complete/<token>
    
    Args:
        token: Order token (NEXUS-XXXXXXXX)
        
    Returns:
        JSON with updated status or error
    """
    clean_token = validate_token(token)
    
    if not clean_token:
        logger.warning(f"Invalid token format in print_order (legacy): {token}")
        return jsonify({
            "success": False,
            "error": "Invalid token format"
        }), 400
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Get current status
        cursor.execute("SELECT status FROM orders WHERE order_id = ?", (clean_token,))
        row = cursor.fetchone()
        
        if not row:
            logger.warning(f"Order not found for print_order: {clean_token}")
            return jsonify({
                "success": False,
                "error": "Order not found"
            }), 404
        
        current_status = row["status"]
        
        # For legacy compatibility: allow Pending or Printing to complete
        if current_status not in ["Pending", "Printing", "Completed"]:
            logger.warning(f"Cannot complete order with status {current_status}: {clean_token}")
            return jsonify({
                "success": False,
                "error": f"Cannot complete order with status {current_status}"
            }), 409
        
        # Skip update if already completed
        if current_status == "Completed":
            return jsonify({
                "success": True,
                "status": "Completed"
            })
        
        # Update status to Completed
        cursor.execute("UPDATE orders SET status = 'Completed' WHERE order_id = ?", (clean_token,))
        conn.commit()
        
        if cursor.rowcount == 0:
            logger.error(f"Order not found after fetch (legacy): {clean_token}")
            return jsonify({
                "success": False,
                "error": "Order not found"
            }), 404
        
        logger.info(f"Order completed (legacy): {clean_token} ({current_status}→Completed)")
        
        return jsonify({
            "success": True,
            "status": "Completed"
        })
    
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Database error in print_order (legacy) {clean_token}: {e}")
        return jsonify({
            "success": False,
            "error": "Database error"
        }), 500
    
    finally:
        close_db(conn)


@app.route('/delete/<token>')
@admin_required
def delete_order(token):
    """
    Delete order from database.
    
    Args:
        token: Order token (NEXUS-XXXXXXXX)
        
    Returns:
        JSON success/error response
    """
    clean_token = validate_token(token)
    
    if not clean_token:
        logger.warning(f"Invalid token format in delete_order: {token}")
        return jsonify({
            "success": False,
            "error": "Invalid token format"
        }), 400
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orders WHERE order_id = ?", (clean_token,))
        conn.commit()
        
        if cursor.rowcount == 0:
            logger.warning(f"Order not found for deletion: {clean_token}")
            return jsonify({
                "success": False,
                "error": "Order not found"
            }), 404
        
        logger.info(f"Order deleted: {clean_token}")
        
        return jsonify({
            "success": True,
            "message": "Order deleted successfully"
        })
    
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Database error deleting order {clean_token}: {e}")
        return jsonify({
            "success": False,
            "error": "Database error"
        }), 500
    
    finally:
        close_db(conn)


@app.route('/clear')
@admin_required
def clear_database():
    """
    Clear all orders from database (admin only).
    
    WARNING: Destructive operation. Cannot be undone.
    
    Returns:
        JSON success/error response
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orders")
        conn.commit()
        
        logger.warning("DATABASE CLEARED by admin")
        
        return jsonify({
            "success": True,
            "message": "Database cleared successfully"
        })
    
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Database error clearing database: {e}")
        return jsonify({
            "success": False,
            "error": "Clear operation failed"
        }), 500
    
    finally:
        close_db(conn)


# ═════════════════════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ═════════════════════════════════════════════════════════════════════════════


@app.errorhandler(404)
def not_found(error):
    """Handle 404 Not Found errors."""
    logger.warning(f"404 error: {request.path}")
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404


@app.errorhandler(500)
def server_error(error):
    """Handle 500 Internal Server errors."""
    logger.error(f"500 error: {error}")
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500


# ═════════════════════════════════════════════════════════════════════════════
# BROWSER LAUNCH
# ═════════════════════════════════════════════════════════════════════════════


def open_browser():
    """Open browser to application on startup."""
    try:
        webbrowser.open("http://127.0.0.1:5000")
    except Exception as e:
        logger.error(f"Could not open browser: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# APP ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    logger.info("═" * 80)
    logger.info("Starting Nexus Asynchronous Printing System")
    logger.info(f"Database: {DATABASE}")
    logger.info(f"Upload folder: {UPLOAD_FOLDER}")
    logger.info(f"Token pattern: {TOKEN_PATTERN.pattern}")
    logger.info(f"Status transitions: Pending→Printing→Completed")
    logger.info("═" * 80)
    
    # Get port from environment or default to 5000
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV") != "production"
    
    # Only open browser in development mode
    if debug_mode:
        Timer(1, open_browser).start()
    
    # Run Flask server
    app.run(host="0.0.0.0", port=port, debug=debug_mode)

