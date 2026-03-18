import sqlite3
from flask import Flask, request, jsonify, render_template
from datetime import datetime
import os

app = Flask(__name__)
DB_NAME = "secret_official.sqlite"

# --- 資料庫基礎設定 ---

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """初始化資料庫，確保包含所有必要欄位"""
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS official_docs (
            doc_id TEXT PRIMARY KEY,
            assignee TEXT NOT NULL,
            job_number TEXT NOT NULL,
            login_time TEXT NOT NULL,
            collection_time TEXT,
            is_collected INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()
    print("✅ 密件公文資料庫連線成功且已初始化！")

# --- 網頁頁面路由 ---

@app.route('/')
def index():
    """管理端首頁"""
    return render_template('doc_admin.html')

@app.route('/collect')
def collect_page():
    """承辦人簽收頁面"""
    return render_template('user_collect.html')

# --- API 介面 ---

@app.route('/api/doc_list', methods=['GET'])
def get_docs():
    """取得公文清單：預設顯示『未領取』，若有日期則顯示『該區間全部』"""
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    conn = get_db_connection()
    
    if start_date and end_date:
        # 當使用者選擇日期區間時：顯示該區間內「所有」公文 (方便印報表)
        query = "SELECT * FROM official_docs WHERE login_time BETWEEN ? AND ? ORDER BY login_time DESC"
        docs = conn.execute(query, (f"{start_date} 00:00:00", f"{end_date} 23:59:59")).fetchall()
    elif start_date:
        # 若只有起始日：顯示該日後「所有」公文
        query = "SELECT * FROM official_docs WHERE login_time >= ? ORDER BY login_time DESC"
        docs = conn.execute(query, (f"{start_date} 00:00:00",)).fetchall()
    else:
        # 【預設】顯示所有「尚未領取」的公文
        query = "SELECT * FROM official_docs WHERE is_collected = 0 ORDER BY login_time DESC"
        docs = conn.execute(query).fetchall()
        
    conn.close()
    return jsonify([dict(doc) for doc in docs])

@app.route('/api/add_doc', methods=['POST'])
def add_doc():
    """登錄新公文"""
    try:
        data = request.json
        doc_id = data.get('doc_id')
        assignee = data.get('assignee')
        job_number = data.get('job_number')

        if not doc_id or len(doc_id) != 10:
            return jsonify({'status': 'error', 'message': '收文號須為 10 碼'}), 400
        if not assignee or not job_number:
            return jsonify({'status': 'error', 'message': '姓名與職號不能空白'}), 400

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO official_docs (doc_id, assignee, job_number, login_time) VALUES (?, ?, ?, ?)",
            (doc_id, assignee, job_number, now)
        )
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': '此收文號已存在於資料庫'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/collect_doc/<job_num>', methods=['POST'])
def collect_action(job_num):
    """透過職號領取該承辦人名下『所有』待領公文"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn = get_db_connection()
        # 1. 找出該職號名下所有尚未領取的公文
        docs = conn.execute(
            "SELECT doc_id, assignee FROM official_docs WHERE job_number = ? AND is_collected = 0", 
            (job_num,)
        ).fetchall()

        if docs:
            name = docs[0]['assignee']
            doc_list = [d['doc_id'] for d in docs] # 提取所有收文號
            
            # 2. 批量更新狀態為已領取
            conn.execute(
                "UPDATE official_docs SET is_collected = 1, collection_time = ? WHERE job_number = ? AND is_collected = 0",
                (now, job_num)
            )
            conn.commit()
            conn.close()
            
            # 3. 回傳資料供前端顯示
            return jsonify({
                'status': 'success', 
                'doc_ids': doc_list, 
                'name': name, 
                'time': now,
                'count': len(doc_list)
            })
        else:
            conn.close()
            return jsonify({'status': 'fail', 'message': '目前查無此職號之待領公文'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- 啟動程式 ---

if __name__ == '__main__':
    init_db()
    # 使用 5001 埠號避開 macOS 預設佔用的 5000 埠
    # debug=True 會在修改後自動重啟伺服器
    app.run(host='0.0.0.0', port=5001, debug=True)