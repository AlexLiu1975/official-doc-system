import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, render_template
from datetime import datetime
import time
    
app = Flask(__name__)
# --- 資料庫連線設定 ---

def get_db_connection():
    # 這裡填入 Supabase 的連線字串
    db_url = os.environ.get("DATABASE_URL")
    # 建議在環境變數網址後加上 ?sslmode=require
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return conn



def init_db():
    """初始化 PostgreSQL 資料庫表格"""
    conn = get_db_connection()
    cur = conn.cursor()
    # PostgreSQL 語法優化：TIMESTAMP 與 VARCHAR
    cur.execute("""
        CREATE TABLE IF NOT EXISTS official_docs (
            doc_id VARCHAR(20) PRIMARY KEY,
            assignee VARCHAR(100) NOT NULL,
            job_number VARCHAR(50) NOT NULL,
            login_time TIMESTAMP NOT NULL,
            collection_time TIMESTAMP,
            is_collected INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("✅ PostgreSQL 資料庫初始化成功！")

# --- 網頁路由 ---

@app.route('/')
def index():
    return render_template('doc_admin.html')

@app.route('/collect')
def collect_page():
    return render_template('user_collect.html')

# --- API 介面 ---

@app.route('/api/doc_list', methods=['GET'])
def get_docs():
    """取得公文清單：支援日期區間篩選"""
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if start_date and end_date:
        # PostgreSQL 使用 %s 作為佔位符
        query = "SELECT * FROM official_docs WHERE login_time >= %s AND login_time <= %s ORDER BY login_time DESC"
        cur.execute(query, (f"{start_date} 00:00:00", f"{end_date} 23:59:59"))
    elif start_date:
        query = "SELECT * FROM official_docs WHERE login_time >= %s ORDER BY login_time DESC"
        cur.execute(query, (f"{start_date} 00:00:00",))
    else:
        # 預設：僅顯示未領取
        query = "SELECT * FROM official_docs WHERE is_collected = 0 ORDER BY login_time DESC"
        cur.execute(query)
        
    docs = cur.fetchall()
    
    # 處理回傳資料中的 datetime 物件轉為字串，以便 JSON 傳輸
    result = []
    for doc in docs:
        d = dict(doc)
        d['login_time'] = d['login_time'].strftime('%Y-%m-%d %H:%M:%S') if d['login_time'] else ""
        d['collection_time'] = d['collection_time'].strftime('%Y-%m-%d %H:%M:%S') if d['collection_time'] else ""
        result.append(d)

    cur.close()
    conn.close()
    return jsonify(result)

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

        now = datetime.now()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO official_docs (doc_id, assignee, job_number, login_time) VALUES (%s, %s, %s, %s)",
            (doc_id, assignee, job_number, now)
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'status': 'success'})
    except psycopg2.IntegrityError:
        return jsonify({'status': 'error', 'message': '此收文號已存在'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/collect_doc/<job_num>', methods=['POST'])
def collect_action(job_num):
    """簽收公文 (透過職號)"""
    now = datetime.now()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. 檢查是否有待領公文
        cur.execute(
            "SELECT doc_id, assignee FROM official_docs WHERE job_number = %s AND is_collected = 0", 
            (job_num,)
        )
        docs = cur.fetchall()

        if docs:
            name = docs[0]['assignee']
            doc_list = [d['doc_id'] for d in docs]
            
            # 2. 更新狀態
            cur.execute(
                "UPDATE official_docs SET is_collected = 1, collection_time = %s WHERE job_number = %s AND is_collected = 0",
                (now, job_num)
            )
            conn.commit()
            cur.close()
            conn.close()
            
            return jsonify({
                'status': 'success', 
                'doc_ids': doc_list, 
                'name': name, 
                'time': now.strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            cur.close()
            conn.close()
            return jsonify({'status': 'fail', 'message': '目前無待領公文'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 記得保留這個 debug 路由，第一次連上 Supabase 時要跑一次建表
@app.route('/debug/init')
def force_init():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS official_docs (
                doc_id VARCHAR(20) PRIMARY KEY,
                assignee VARCHAR(100) NOT NULL,
                job_number VARCHAR(50) NOT NULL,
                login_time TIMESTAMP NOT NULL,
                collection_time TIMESTAMP,
                is_collected INTEGER DEFAULT 0
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        return "<h1>✅ Supabase 資料庫初始化成功！</h1>"
    except Exception as e:
        return f"<h1>❌ 失敗</h1><p>{str(e)}</p>"

# --- 啟動 ---

if __name__ == '__main__':
    # 這裡最關鍵：讀取 Render 提供的 PORT，預設為 10000
    port = int(os.environ.get("PORT", 10000))
    # 必須監聽 0.0.0.0 才能讓外部連線進來
    app.run(host='0.0.0.0', port=port)
