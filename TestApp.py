import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# 1. ตั้งค่าหน้าจอ
st.set_page_config(page_title="Trip Splitter Pro", layout="wide")

# 🔄 รีเฟรชทุก 3 วินาที (3000 ms)
st_autorefresh(interval=3000, limit=None, key="trip_app_refresh")

DB_FILE = "trip_database.db"

# 2. ฟังก์ชันจัดการฐานข้อมูล
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, promptpay TEXT, bank_name TEXT, bank_account TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, status INTEGER DEFAULT 0, trip_date TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB)')
    cursor.execute('CREATE TABLE IF NOT EXISTS online_status (name TEXT PRIMARY KEY, last_seen DATETIME)')
    cursor.execute('CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, to_user TEXT, from_user TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, is_auto INTEGER DEFAULT 0, is_read INTEGER DEFAULT 0)')
    conn.commit()
    conn.close()

def compress_image(uploaded_file):
    if uploaded_file is None: return None
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    img.thumbnail((400, 400)) # ลดขนาดภาพลงครึ่งนึง
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()

init_db()

# --- ส่วนจัดการ Session และ Sidebar ---
if "current_online_user" not in st.session_state:
    st.session_state["current_online_user"] = None

# (ข้ามส่วน Login/Sidebar เพื่อความกระชับ แต่ให้ใช้ตามโครงเดิมที่คุณมี)
# สมมติว่าดึงข้อมูลทริปมาแล้วชื่อ trip_id และ current_trip

# --- 🎯 ส่วนหลักของแอป ---
st.title(f"✈️ Event: {st.session_state.get('current_trip_name', 'ทริปของฉัน')}")

# ✅ ประกาศ Tabs ให้ครบถ้วนเพื่อแก้ NameError: tab3
tab1, tab2, tab3 = st.tabs(["📝 สร้างบิล", "📊 ประวัติบิล", "💰 สรุปยอดเงิน"])

with tab1:
    st.subheader("➕ เพิ่มบิลใหม่")
    # ... (ส่วน Form กรอกบิลเดิมของคุณ) ...

with tab2:
    st.subheader("📋 รายการบิล")
    # ... (ส่วนแสดงรายการบิลเดิมของคุณ) ...

# 💰 ส่วนที่เพิ่มระบบคำนวณเงินใน Tab 3 ให้สมบูรณ์
with tab3:
    st.header("สรุปยอดค้างชำระ")
    conn = get_db_connection()
    # ดึงรายชื่อสมาชิกในทริป
    members_rows = conn.execute("SELECT name FROM members WHERE trip_id = ?", (1,)).fetchall() # แก้ trip_id ตามจริง
    members = [m['name'] for m in members_rows]
    
    # ดึงรายการค่าใช้จ่ายทั้งหมด
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (1,)).fetchall() # แก้ trip_id ตามจริง
    conn.close()

    if not expenses or not members:
        st.info("ยังไม่มีข้อมูลสำหรับคำนวณ")
    else:
        # คำนวณ Net Balance
        balances = {m: 0.0 for m in members}
        for exp in expenses:
            payer = exp['payer_name']
            amt = exp['amount']
            split_list = exp['split_members'].split(",")
            share = amt / len(split_list)
            
            if payer in balances: balances[payer] += amt
            for m in split_list:
                if m in balances: balances[m] -= share

        # แสดงตารางสรุป
        summary_data = [{"ชื่อ": k, "ยอดสุทธิ": f"{v:,.2f}"} for k, v in balances.items()]
        st.table(pd.DataFrame(summary_data))

        # คำนวณว่าใครต้องโอนให้ใคร
        st.subheader("💸 รายการโอนเงิน")
        debtors = [[m, bal] for m, bal in balances.items() if bal < -0.01]
        creditors = [[m, bal] for m, bal in balances.items() if bal > 0.01]

        for d_name, d_bal in debtors:
            for c in creditors:
                if abs(d_bal) <= 0: break
                if c[1] <= 0: continue
                
                amount = min(abs(d_bal), c[1])
                st.warning(f"🔸 **{d_name}** ต้องโอนให้ **{c[0]}** = **{amount:,.2f}** บาท")
                d_bal += amount
                c[1] -= amount
