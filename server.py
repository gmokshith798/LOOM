import os
import json
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Wasmer PostgreSQL Database Configuration
DB_HOST = os.environ.get("POSTGRES_HOST", "psql.fr-roub1.bengt.wasmernet.com")
DB_PORT = int(os.environ.get("POSTGRES_PORT", 20184))
DB_NAME = os.environ.get("POSTGRES_DB", "database_pandu")
DB_USER = os.environ.get("POSTGRES_USER", "user_2871f50a")
DB_PASS = os.environ.get("POSTGRES_PASSWORD", "pw_q17jTZgiwpzKPFqs1S2CdLpaqmBaudd0")

USE_POSTGRES = False

def get_db():
    global USE_POSTGRES
    # 1. Try PostgreSQL
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            sslmode="require",
            connect_timeout=4
        )
        conn.autocommit = True
        USE_POSTGRES = True
        return conn, "pg"
    except Exception as e:
        # Fallback to local SQLite database if PostgreSQL password/network needs configuration
        import sqlite3
        conn = sqlite3.connect("loom_data.db", check_same_thread=False)
        USE_POSTGRES = False
        return conn, "sqlite"

def init_db():
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
        print(f"[OK] Connected to Wasmer PostgreSQL ({DB_HOST}:{DB_PORT}/{DB_NAME})")
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS store_kv (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at VARCHAR(100)
            );
        """)
        print("[INFO] Running with SQLite local database fallback (loom_data.db)")

# Initialize DB on start
try:
    init_db()
except Exception as e:
    print("[WARN] DB init notice:", str(e))

def db_get_all():
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

def db_get_key(key):
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

def db_set_key(key, val):
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
