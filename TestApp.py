import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# 1. Page Config & Auto Refresh
st.set_page_config(page_title="Trip Splitter Pro", layout="wide")
# 🔄 ปรับรีเฟรชเป็น 3 วินาทีตามสั่ง
st_autorefresh(interval=3000, limit=None, key="trip_refresh_final")

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
    cursor.execute('''CREATE TABLE IF NOT EXISTS all_users 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, 
                       promptpay TEXT, bank_name TEXT, bank_account TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS trips 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, 
                       status INTEGER DEFAULT 0, trip_date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS members 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS expenses 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, 
                       amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS notifications 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, to_user TEXT, 
                       from_user TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                       is_auto INTEGER DEFAULT 0, is_read INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def compress_image(uploaded_file):
    if uploaded_file is None: return None
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    # 📉 ลดขนาดรูปสลิปลงเหลือครึ่งหนึ่ง (400px)
    img.thumbnail((400, 400))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()

init_db()

# 3. การจัดการ Session & Sidebar
if "current_online_user" not in st.session_state:
    st.session_state["current_online_user"] = "G" # ตัวอย่างชื่อผู้ใช้

# ดึงข้อมูลทริป (Logic สมมติว่าเลือกทริปแรกในฐานข้อมูล)
conn = get_db_connection()
trip_row = conn.execute("SELECT * FROM trips WHERE status = 0 LIMIT 1").fetchone()
conn.close()

if not trip_row:
    st.warning("⚠️ กรุณาสร้าง Event ใน Sidebar ก่อน")
    st.stop()

trip_id = trip_row['id']
current_trip_name = trip_row['name']

# 4. ส่วนการแสดงผลหลัก
st.title(f"✈️ Event: {current_trip_name}")

# ✅ ประกาศ Tabs (แก้ NameError ที่เจอในรูป)
tab1, tab2, tab3 = st.tabs(["📝 สร้างบิล", "📊 ประวัติบิล", "💰 สรุปยอดเงิน"])

# --- TAB 1: สร้างบิล ---
with tab1:
    with st.form("add_bill_form", clear_on_submit=True):
        st.subheader("➕ เพิ่มค่าใช้จ่าย")
        col_a, col_b = st.columns(2)
        desc = col_a.text_input("รายการ:")
        amt = col_b.number_input("จำนวนเงิน:", min_value=0.0)
        
        conn = get_db_connection()
        m_rows = conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()
        existing_members = [m['name'] for m in m_rows]
        conn.close()
        
        payer = st.selectbox("คนสำรองจ่าย:", existing_members if existing_members else ["ไม่มีสมาชิก"])
        st.write("คนร่วมหาร:")
        selected_members = [m for m in existing_members if st.checkbox(m, value=True, key=f"split_{m}")]
        
        file = st.file_uploader("แนบสลิป (ขนาดจะถูกปรับลงครึ่งหนึ่ง):", type=['jpg','jpeg','png'])
        
        if st.form_submit_button("💾 บันทึกบิล"):
            if desc and amt > 0 and selected_members:
                blob = compress_image(file)
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, desc, amt, payer, ",".join(selected_members), blob))
                conn.commit()
                conn.close()
                st.success("บันทึกสำเร็จ!")
                st.rerun()

# --- TAB 2: ประวัติบิล ---
with tab2:
    st.subheader("📋 ประวัติบิล (UI ขนาดกะทัดรัด)")
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    
    for row in expenses:
        with st.expander(f"📌 {row['description']} - {row['amount']:,.2f} บาท"):
            c1, c2 = st.columns([2, 1])
            with c1:
                st.caption(f"ผู้จ่าย: {row['payer_name']}")
                st.caption(f"คนหาร: {row['split_members']}")
                if st.button("🗑️ ลบ", key=f"del_{row['id']}"):
                    conn = get_db_connection()
                    conn.execute("DELETE FROM expenses WHERE id = ?", (row['id'],))
                    conn.commit(); conn.close()
                    st.rerun()
            with c2:
                if row['image_blob']:
                    st.image(row['image_blob'], width=150)

# --- TAB 3: สรุปยอดเงิน (Logic คำนวณอัตโนมัติ) ---
with tab3:
    st.subheader("💰 สรุปยอดค้างชำระ")
    conn = get_db_connection()
    m_rows = conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()
    members = [m['name'] for m in m_rows]
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()

    if not expenses:
        st.info("ยังไม่มีข้อมูลค่าใช้จ่าย")
    else:
        balances = {m: 0.0 for m in members}
        for exp in expenses:
            p, a = exp['payer_name'], exp['amount']
            splits = exp['split_members'].split(",")
            share = a / len(splits)
            if p in balances: balances[p] += a
            for s_m in splits:
                if s_m in balances: balances[s_m] -= share

        # แสดงยอด Net Balance ของทุกคน
        summary_list = [{"ชื่อ": k, "ยอดสุทธิ": f"{v:,.2f}"} for k, v in balances.items()]
        st.table(pd.DataFrame(summary_list))

        # คำนวณจับคู่โอนเงิน
        st.divider()
        st.subheader("💸 ใครต้องโอนให้ใครบ้าง?")
        debtors = [[m, b] for m, b in balances.items() if b < -0.01]
        creditors = [[m, b] for m, b in balances.items() if b > 0.01]

        for d in debtors:
            for c in creditors:
                if abs(d[1]) < 0.01 or c[1] < 0.01: continue
                pay = min(abs(d[1]), c[1])
                st.warning(f"🔴 **{d[0]}** โอนให้ **{c[0]}** 👉 **{pay:,.2f}** บาท")
                d[1] += pay
                c[1] -= pay

# --- ระบบแชทด้านล่าง (แก้ Error st.text_area) ---
st.sidebar.markdown("---")
st.sidebar.subheader("💬 ส่งแชท")
with st.sidebar.form("chat_side", clear_on_submit=True):
    # ✅ แก้ TypeError: ใช้ height แทน rows
    msg = st.text_area("ข้อความ:", height=80, key="side_msg")
    if st.form_submit_button("ส่ง"):
        st.toast("ส่งข้อความแล้ว!")
