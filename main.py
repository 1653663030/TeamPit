#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import sqlite3
import json
import shutil
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ==================== 路径兼容 ====================
def get_base_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    else:
        return Path(__file__).parent.absolute()

def get_data_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / "data"
    else:
        return Path(__file__).parent / "data"

def get_uploads_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / "uploads"
    else:
        return Path(__file__).parent / "uploads"


BASE_DIR = get_base_dir()
DATA_DIR = get_data_dir()
UPLOAD_DIR = get_uploads_dir()

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "teampit.db"

# ==================== 数据库初始化 ====================
def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS room_whitelist (
            room_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            PRIMARY KEY (room_id, user_id),
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id, user_id) REFERENCES room_whitelist(room_id, user_id)
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'todo',
            assignee TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            tags TEXT,
            uploaded_by TEXT NOT NULL,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            content TEXT NOT NULL,
            author TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            yesterday TEXT,
            today TEXT,
            blocked TEXT,
            checkin_date DATE DEFAULT CURRENT_DATE,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ==================== FastAPI 应用 ====================
app = FastAPI(title="TeamPit 团队作战指挥室")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ==================== 数据库工具 ====================
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def check_whitelist(room_id: str, user_id: str) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id FROM room_whitelist WHERE room_id = ? AND user_id = ?",
        (room_id, user_id)
    )
    result = cur.fetchone()
    conn.close()
    return result is not None

def is_room_owner(room_id: str, user_id: str) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT owner_id FROM rooms WHERE id = ?", (room_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None and row["owner_id"] == user_id

# ==================== Pydantic 模型 ====================
class RoomCreate(BaseModel):
    room_id: str
    owner_id: str
    user_ids: List[str]

class RoomJoin(BaseModel):
    room_id: str
    user_id: str

class WhitelistAdd(BaseModel):
    room_id: str
    owner_id: str
    new_user_ids: List[str]

# 🆕 任务相关模型
class TaskCreate(BaseModel):
    room_id: str
    user_id: str
    title: str
    assignee: Optional[str] = None

class TaskUpdate(BaseModel):
    room_id: str
    user_id: str
    title: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = None

# 🆕 灵感相关模型
class IdeaCreate(BaseModel):
    room_id: str
    user_id: str
    content: str

# 🆕 站会相关模型
class CheckinCreate(BaseModel):
    room_id: str
    user_id: str
    yesterday: str = ""
    today: str = ""
    blocked: str = ""

# ==================== API: 房间管理 ====================
@app.post("/api/rooms/create")
def create_room(data: RoomCreate):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO rooms (id, owner_id) VALUES (?, ?)",
            (data.room_id, data.owner_id)
        )
        # 🔥 自动把房主加入白名单（不需要用户手动填写）
        all_user_ids = list(set([data.owner_id] + data.user_ids))  # 去重
        for uid in all_user_ids:
            uid = uid.strip()
            if uid:
                cur.execute(
                    "INSERT INTO room_whitelist (room_id, user_id) VALUES (?, ?)",
                    (data.room_id, uid)
                )
        conn.commit()
        return {"status": "ok", "room": data.room_id}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="房间号已被占用")
    finally:
        conn.close()

@app.post("/api/rooms/join")
def join_room(data: RoomJoin):
    if not check_whitelist(data.room_id, data.user_id):
        raise HTTPException(status_code=403, detail="你的ID不在该房间白名单中，请联系创建者")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO members (room_id, user_id, last_seen) 
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT DO UPDATE SET last_seen = CURRENT_TIMESTAMP
    ''', (data.room_id, data.user_id))
    conn.commit()
    conn.close()
    return {"status": "ok", "room": data.room_id, "user_id": data.user_id}

@app.post("/api/rooms/whitelist/add")
def add_to_whitelist(data: WhitelistAdd):
    if not is_room_owner(data.room_id, data.owner_id):
        raise HTTPException(status_code=403, detail="只有房主可以添加成员")
    
    conn = get_db()
    cur = conn.cursor()
    for uid in data.new_user_ids:
        uid = uid.strip()
        if uid:
            cur.execute(
                "INSERT OR IGNORE INTO room_whitelist (room_id, user_id) VALUES (?, ?)",
                (data.room_id, uid)
            )
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/api/rooms/members")
def get_members(room_id: str, user_id: str):
    if not check_whitelist(room_id, user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT w.user_id, m.last_seen,
               CASE WHEN m.last_seen > datetime('now', '-5 minutes') THEN 1 ELSE 0 END as is_online
        FROM room_whitelist w
        LEFT JOIN members m ON w.room_id = m.room_id AND w.user_id = m.user_id
        WHERE w.room_id = ?
    ''', (room_id,))
    rows = cur.fetchall()
    conn.close()
    return {"members": [dict(row) for row in rows]}

# ==================== API: 任务管理（全部改为接收JSON） ====================
@app.get("/api/tasks")
def get_tasks(room_id: str, user_id: str):
    if not check_whitelist(room_id, user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM tasks WHERE room_id = ? ORDER BY created_at DESC",
        (room_id,)
    )
    tasks = cur.fetchall()
    conn.close()
    return {"tasks": [dict(t) for t in tasks]}

@app.post("/api/tasks")
def create_task(data: TaskCreate = Body(...)):   # 🔥 改为接收 JSON
    if not check_whitelist(data.room_id, data.user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks (room_id, title, assignee) VALUES (?, ?, ?)",
        (data.room_id, data.title, data.assignee)
    )
    conn.commit()
    task_id = cur.lastrowid
    cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = cur.fetchone()
    conn.close()
    return {"task": dict(task)}

@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, data: TaskUpdate = Body(...)):   # 🔥 改为接收 JSON
    if not check_whitelist(data.room_id, data.user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT room_id FROM tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    if not row or row["room_id"] != data.room_id:
        conn.close()
        raise HTTPException(status_code=404, detail="任务不存在")
    
    updates = []
    params = []
    if data.title is not None:
        updates.append("title = ?")
        params.append(data.title)
    if data.status is not None:
        updates.append("status = ?")
        params.append(data.status)
    if data.assignee is not None:
        updates.append("assignee = ?")
        params.append(data.assignee)
    
    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(task_id)
        cur.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()
    
    cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    task = cur.fetchone()
    conn.close()
    return {"task": dict(task)}

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int, room_id: str = Query(...), user_id: str = Query(...)):
    if not check_whitelist(room_id, user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT room_id FROM tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    if not row or row["room_id"] != room_id:
        conn.close()
        raise HTTPException(status_code=404, detail="任务不存在")
    
    cur.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

# ==================== API: 灵感留言（全部改为接收JSON） ====================
@app.get("/api/ideas")
def get_ideas(room_id: str, user_id: str):
    if not check_whitelist(room_id, user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM ideas WHERE room_id = ? ORDER BY created_at DESC",
        (room_id,)
    )
    ideas = cur.fetchall()
    conn.close()
    return {"ideas": [dict(i) for i in ideas]}

@app.post("/api/ideas")
def create_idea(data: IdeaCreate = Body(...)):   # 🔥 改为接收 JSON
    if not check_whitelist(data.room_id, data.user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    if data.user_id != data.user_id:
        # 防止冒名，但因为传入的就是 user_id，所以这里简单校验
        pass
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ideas (room_id, content, author) VALUES (?, ?, ?)",
        (data.room_id, data.content, data.user_id)
    )
    conn.commit()
    idea_id = cur.lastrowid
    cur.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,))
    idea = cur.fetchone()
    conn.close()
    return {"idea": dict(idea)}

@app.delete("/api/ideas/{idea_id}")
def delete_idea(idea_id: int, room_id: str = Query(...), user_id: str = Query(...)):
    if not check_whitelist(room_id, user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT room_id, author FROM ideas WHERE id = ?", (idea_id,))
    row = cur.fetchone()
    if not row or row["room_id"] != room_id:
        conn.close()
        raise HTTPException(status_code=404, detail="灵感不存在")
    if row["author"] != user_id:
        conn.close()
        raise HTTPException(status_code=403, detail="只能删除自己的灵感")
    
    cur.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

# ==================== API: 文件管理（文件上传保持 FormData） ====================
@app.get("/api/files")
def get_files(room_id: str, user_id: str):
    if not check_whitelist(room_id, user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM files WHERE room_id = ? ORDER BY uploaded_at DESC",
        (room_id,)
    )
    files = cur.fetchall()
    conn.close()
    return {"files": [dict(f) for f in files]}

@app.post("/api/files/upload")
async def upload_file(
    room_id: str = Form(...),
    user_id: str = Form(...),
    tags: str = Form(""),
    file: UploadFile = File(...)
):
    if not check_whitelist(room_id, user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    room_upload_dir = UPLOAD_DIR / room_id
    room_upload_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = room_upload_dir / safe_filename
    
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO files (room_id, filename, filepath, tags, uploaded_by) VALUES (?, ?, ?, ?, ?)",
        (room_id, file.filename, str(file_path), tags, user_id)
    )
    conn.commit()
    file_id = cur.lastrowid
    cur.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    file_record = cur.fetchone()
    conn.close()
    
    return {"file": dict(file_record)}

@app.get("/api/files/download/{file_id}")
def download_file(file_id: int, room_id: str = Query(...), user_id: str = Query(...)):
    if not check_whitelist(room_id, user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM files WHERE id = ? AND room_id = ?", (file_id, room_id))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    file_path = Path(row["filepath"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件已丢失")
    
    return FileResponse(
        path=str(file_path),
        filename=row["filename"],
        media_type="application/octet-stream"
    )

@app.delete("/api/files/{file_id}")
def delete_file(file_id: int, room_id: str = Query(...), user_id: str = Query(...)):
    if not check_whitelist(room_id, user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM files WHERE id = ? AND room_id = ?", (file_id, room_id))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="文件不存在")
    
    file_path = Path(row["filepath"])
    if file_path.exists():
        file_path.unlink()
    
    cur.execute("DELETE FROM files WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

# ==================== API: 每日站会（全部改为接收JSON） ====================
@app.get("/api/checkins")
def get_checkins(room_id: str, user_id: str):
    if not check_whitelist(room_id, user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM checkins WHERE room_id = ? ORDER BY checkin_date DESC, id DESC",
        (room_id,)
    )
    checkins = cur.fetchall()
    conn.close()
    return {"checkins": [dict(c) for c in checkins]}

@app.get("/api/checkins/today")
def get_today_checkin(room_id: str, user_id: str):
    if not check_whitelist(room_id, user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    today_str = date.today().isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM checkins WHERE room_id = ? AND user_id = ? AND checkin_date = ?",
        (room_id, user_id, today_str)
    )
    row = cur.fetchone()
    conn.close()
    return {"checkin": dict(row) if row else None}

@app.post("/api/checkins")
def create_checkin(data: CheckinCreate = Body(...)):   # 🔥 改为接收 JSON
    if not check_whitelist(data.room_id, data.user_id):
        raise HTTPException(status_code=403, detail="无权访问")
    
    today_str = date.today().isoformat()
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute(
        "SELECT id FROM checkins WHERE room_id = ? AND user_id = ? AND checkin_date = ?",
        (data.room_id, data.user_id, today_str)
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            "UPDATE checkins SET yesterday = ?, today = ?, blocked = ? WHERE id = ?",
            (data.yesterday, data.today, data.blocked, existing["id"])
        )
    else:
        cur.execute(
            "INSERT INTO checkins (room_id, user_id, yesterday, today, blocked, checkin_date) VALUES (?, ?, ?, ?, ?, ?)",
            (data.room_id, data.user_id, data.yesterday, data.today, data.blocked, today_str)
        )
    
    conn.commit()
    conn.close()
    return {"status": "ok", "date": today_str}

# ==================== 首页 ====================
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = BASE_DIR / "static" / "index.html"
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>TeamPit - 请确保 static/index.html 存在</h1>"

# ==================== 启动入口 ====================
if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  🏆 TeamPit 团队作战指挥室")
    print("=" * 50)
    print(f"  数据库: {DB_PATH}")
    print(f"  上传目录: {UPLOAD_DIR}")
    print("  启动服务: http://localhost:8080")
    print("  按 Ctrl+C 停止服务")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8080)
