import os
import json
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB max upload

# Wasmer PostgreSQL Database Configuration
DB_HOST = os.environ.get("POSTGRES_HOST", "psql.fr-roub1.bengt.wasmernet.com")
DB_PORT = int(os.environ.get("POSTGRES_PORT", 20184))
DB_NAME = os.environ.get("POSTGRES_DB", "database_pandu")
DB_USER = os.environ.get("POSTGRES_USER", "user_2871f50a")
DB_PASS = os.environ.get("POSTGRES_PASSWORD", "pw_q17jTZg1wpzKPFqslS2CdLpaqmBauddO")

USE_POSTGRES = None
_pg_retry_at = 0  # timestamp after which we retry PG if it previously failed

def get_db():
    global USE_POSTGRES, _pg_retry_at
    import time
    # Reset USE_POSTGRES to None after 60 seconds so we retry PG credentials
    if USE_POSTGRES is False and time.time() > _pg_retry_at:
        USE_POSTGRES = None
    if USE_POSTGRES is not False:
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASS,
                sslmode="require",
                connect_timeout=2
            )
            conn.autocommit = True
            USE_POSTGRES = True
            return conn, "pg"
        except Exception as e:
            USE_POSTGRES = False
            _pg_retry_at = time.time() + 60  # retry after 60 seconds
    # Fallback to SQLite — use absolute path next to server.py for stability
    import sqlite3
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loom_data.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return conn, "sqlite"

def init_db():
    try:
        conn, mode = get_db()
        cursor = conn.cursor()
        if mode == "pg":
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS store_kv (
                    key VARCHAR(100) PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at VARCHAR(100)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files_kv (
                    file_id VARCHAR(200) PRIMARY KEY,
                    content TEXT NOT NULL,
                    updated_at VARCHAR(100)
                );
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS store_kv (
                    key VARCHAR(100) PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at VARCHAR(100)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files_kv (
                    file_id VARCHAR(200) PRIMARY KEY,
                    content TEXT NOT NULL,
                    updated_at VARCHAR(100)
                );
            """)
            conn.commit()
    except Exception as e:
        print("[WARN] DB init notice:", str(e))

# Initialize DB on start
try:
    init_db()
except Exception as e:
    print("[WARN] DB init notice:", str(e))

def db_get_all():
    try:
        conn, mode = get_db()
        cursor = conn.cursor()
        store = {}
        if mode == "pg":
            cursor.execute("SELECT key, value FROM store_kv;")
            rows = cursor.fetchall()
            for k, v in rows:
                store[k] = v if isinstance(v, (dict, list)) else json.loads(v)
        else:
            cursor.execute("SELECT key, value FROM store_kv;")
            rows = cursor.fetchall()
            for k, v in rows:
                try:
                    store[k] = json.loads(v)
                except:
                    store[k] = v
        return store
    except Exception as e:
        print("[WARN] db_get_all fallback notice:", str(e))
        import sqlite3
        conn = sqlite3.connect("loom_data.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS store_kv (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);")
        cursor.execute("SELECT key, value FROM store_kv;")
        rows = cursor.fetchall()
        store = {}
        for k, v in rows:
            try: store[k] = json.loads(v)
            except: store[k] = v
        return store

def db_get_key(key):
    try:
        conn, mode = get_db()
        cursor = conn.cursor()
        if mode == "pg":
            cursor.execute("SELECT value FROM store_kv WHERE key = %s;", (key,))
            row = cursor.fetchone()
            if row:
                return row[0] if isinstance(row[0], (dict, list)) else json.loads(row[0])
        else:
            cursor.execute("SELECT value FROM store_kv WHERE key = ?;", (key,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except:
                    return row[0]
        return None
    except Exception as e:
        print("[WARN] db_get_key fallback notice:", str(e))
        import sqlite3
        conn = sqlite3.connect("loom_data.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS store_kv (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);")
        cursor.execute("SELECT value FROM store_kv WHERE key = ?;", (key,))
        row = cursor.fetchone()
        if row:
            try: return json.loads(row[0])
            except: return row[0]
        return None

def db_set_key(key, val):
    try:
        conn, mode = get_db()
        cursor = conn.cursor()
        val_json = json.dumps(val)
        now_str = datetime.utcnow().isoformat()
        if mode == "pg":
            cursor.execute("""
                INSERT INTO store_kv (key, value, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at;
            """, (key, val_json, now_str))
        else:
            cursor.execute("""
                INSERT INTO store_kv (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
            """, (key, val_json, now_str))
            conn.commit()
    except Exception as e:
        print("[WARN] db_set_key fallback notice:", str(e))
        import sqlite3
        conn = sqlite3.connect("loom_data.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS store_kv (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);")
        val_json = json.dumps(val)
        now_str = datetime.utcnow().isoformat()
        cursor.execute("""
            INSERT INTO store_kv (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
        """, (key, val_json, now_str))
        conn.commit()

def db_get_file(file_id):
    conn, mode = get_db()
    cursor = conn.cursor()
    if mode == "pg":
        cursor.execute("SELECT content FROM files_kv WHERE file_id = %s;", (file_id,))
    else:
        cursor.execute("SELECT content FROM files_kv WHERE file_id = ?;", (file_id,))
    row = cursor.fetchone()
    return row[0] if row else None

def db_set_file(file_id, content):
    conn, mode = get_db()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    if mode == "pg":
        cursor.execute("""
            INSERT INTO files_kv (file_id, content, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (file_id) DO UPDATE SET content = EXCLUDED.content, updated_at = EXCLUDED.updated_at;
        """, (file_id, content, now_str))
    else:
        cursor.execute("""
            INSERT INTO files_kv (file_id, content, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at;
        """, (file_id, content, now_str))
        conn.commit()

@app.route('/api/file/<file_id>', methods=['GET'])
def get_file_content(file_id):
    content = db_get_file(file_id)
    if not content:
        return jsonify({"error": "File not found"}), 404
    return jsonify({"file_id": file_id, "content": content})

@app.route('/api/file/<file_id>', methods=['PUT', 'POST'])
def put_file_content(file_id):
    payload = request.get_json(force=True, silent=True) or {}
    content = payload.get("content") or request.data.decode('utf-8')
    if not content:
        return jsonify({"error": "Content required"}), 400
    db_set_file(file_id, content)
    return jsonify({"status": "ok", "file_id": file_id})

@app.route('/api/store.json', methods=['GET'])
@app.route('/api/store', methods=['GET'])
def get_full_store():
    store = db_get_all()
    store_bytes = json.dumps(store, sort_keys=True).encode('utf-8')
    etag = hashlib.md5(store_bytes).hexdigest()

    client_etag = request.headers.get('If-None-Match')
    if client_etag and client_etag.strip('"') == etag:
        res = Response(status=304)
        res.headers['ETag'] = f'"{etag}"'
        return res

    res = jsonify(store)
    res.headers['ETag'] = f'"{etag}"'
    res.headers['Cache-Control'] = 'no-cache'
    return res

@app.route('/api/store/<key>.json', methods=['GET'])
def get_key_data(key):
    val = db_get_key(key)
    if val is None:
        val = []
    val_bytes = json.dumps(val, sort_keys=True).encode('utf-8')
    etag = hashlib.md5(val_bytes).hexdigest()

    client_etag = request.headers.get('If-None-Match')
    if client_etag and client_etag.strip('"') == etag:
        res = Response(status=304)
        res.headers['ETag'] = f'"{etag}"'
        return res

    res = jsonify(val)
    res.headers['ETag'] = f'"{etag}"'
    return res

@app.route('/api/store/<key>.json', methods=['PUT'])
def put_key_data(key):
    payload = request.get_json(force=True, silent=True)
    if payload is None:
        payload = request.data.decode('utf-8')
    db_set_key(key, payload)
    return jsonify({"status": "ok", "key": key})

@app.route('/api/store/updatedAt.json', methods=['GET'])
def get_updated_at():
    val = db_get_key("updatedAt")
    if not val:
        val = datetime.utcnow().isoformat()
    return jsonify(val)

@app.route('/api/store/updatedAt.json', methods=['PUT'])
def put_updated_at():
    payload = request.get_json(force=True, silent=True)
    if not payload:
        payload = datetime.utcnow().isoformat()
    db_set_key("updatedAt", payload)
    return jsonify(payload)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"Loom Backend API Server starting on http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
