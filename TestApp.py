import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
import urllib.parse
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# 1. ตั้งค่าหน้าจอและโครงสร้างพื้นฐาน
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# 🔄 รีเฟรชหน้าจออัตโนมัติทุกๆ 1 วินาที เพื่อให้ข้อความแจ้งเตือนเด้งทันที
st_autorefresh(interval=1000, limit=None, key="trip_app_live_refresh")

DB_FILE = "trip_database.db"

BANK_LIST = [
    "-- เลือกธนาคาร --", "กสิกรไทย (KBank)", "ไทยพาณิชย์ (SCB)", "กรุงไทย (KTB)",
    "กรุงเทพ (BBL)", "กรุงศรีอยุธยา (BAY)", "ทหารไทยธนชาต (TTB)", "ออมสิน (GSB)",
    "ธ.ก.ส.", "ยูโอบี (UOB)"
]

# 2. ฟังก์ชันจัดการฐานข้อมูล SQL
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, status INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS settlements (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS online_status (name TEXT PRIMARY KEY, last_seen DATETIME)')
    
    # 🔔 ตารางสำหรับระบบข้อความแจ้งเตือนเรียกเก็บเงิน
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            trip_id INTEGER, 
            to_user TEXT, 
            from_user TEXT, 
            message TEXT, 
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')

    cursor.execute("PRAGMA table_info(all_users)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'promptpay' not in columns: cursor.execute("ALTER TABLE all_users ADD COLUMN promptpay TEXT")
    if 'bank_name' not in columns: cursor.execute("ALTER TABLE all_users ADD COLUMN bank_name TEXT")
    if 'bank_account' not in columns: cursor.execute("ALTER TABLE all_users ADD COLUMN bank_account TEXT")
        
    cursor.execute("PRAGMA table_info(trips)")
    trip_columns = [row[1] for row in cursor.fetchall()]
    if 'trip_date' not in trip_columns: cursor.execute("ALTER TABLE trips ADD COLUMN trip_date TEXT")
        
    conn.commit()
    conn.close()

def compress_image(uploaded_file):
    if uploaded_file is None: return None
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()

def update_online_heartbeat(username):
    if username:
        conn = get_db_connection()
        conn.execute("INSERT INTO online_status (name, last_seen) VALUES (?, datetime('now', 'localtime')) "
                     "ON CONFLICT(name) DO UPDATE SET last_seen = datetime('now', 'localtime')", (username,))
        conn.commit()
        conn.close()

def get_currently_online_users():
    conn = get_db_connection()
    rows = conn.execute("SELECT name FROM online_status WHERE last_seen >= datetime('now', 'localtime', '-15 seconds')").fetchall()
    conn.close()
    return [row["name"] for row in rows]

init_db()

if "current_online_user" not in st.session_state:
    st.session_state["current_online_user"] = None

if st.session_state["current_online_user"]:
    update_online_heartbeat(st.session_state["current_online_user"])

# --- 4. เมนูข้าง SIDEBAR ---
st.sidebar.header("🔐 บัญชีผู้ใช้งานเครื่องนี้")
conn = get_db_connection()
existing_all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
conn.close()

if st.session_state["current_online_user"] is None:
    st.sidebar.warning("⚠️ ยังไม่ได้ล็อกอิน")
    login_mode = st.sidebar.radio("ทางเลือก:", ["เลือกโปรไฟล์", "สร้างใหม่"], horizontal=True)
    if login_mode == "เลือกโปรไฟล์" and existing_all_users:
        user_select = st.sidebar.selectbox("เลือกชื่อของคุณ:", existing_all_users)
        if st.sidebar.button("เข้าสู่ระบบ"):
            st.session_state["current_online_user"] = user_select
            st.rerun()
    elif login_mode == "สร้างใหม่":
        new_name = st.sidebar.text_input("ระบุชื่อ:").strip()
        if st.sidebar.button("สร้างและล็อกอิน") and new_name:
            try:
                conn = get_db_connection(); conn.execute("INSERT INTO all_users (name) VALUES (?)", (new_name,))
                conn.commit(); conn.close()
                st.session_state["current_online_user"] = new_name
                st.rerun()
            except: st.sidebar.error("ชื่อซ้ำ")
else:
    st.sidebar.success(f"🟢 ผู้ใช้งาน: **{st.session_state['current_online_user']}**")
    conn = get_db_connection()
    my_data = conn.execute("SELECT * FROM all_users WHERE name = ?", (st.session_state["current_online_user"],)).fetchone()
    conn.close()
    
    with st.sidebar.expander("⚙️ แก้ไขข้อมูลรับเงินส่วนตัว"):
        edit_pp = st.text_input("เลขพร้อมเพย์:", value=my_data['promptpay'] or "")
        db_bank = my_data['bank_name'] or "-- เลือกธนาคาร --"
        bank_idx = BANK_LIST.index(db_bank) if db_bank in BANK_LIST else 0
        edit_bank_name = st.selectbox("ธนาคาร:", BANK_LIST, index=bank_idx)
        edit_bank_acc = st.text_input("เลขบัญชี:", value=my_data['bank_account'] or "")
        if st.button("💾 บันทึกส่วนตัว"):
            conn = get_db_connection()
            conn.execute("UPDATE all_users SET promptpay=?, bank_name=?, bank_account=? WHERE name=?", 
                         (edit_pp, edit_bank_name if edit_bank_name != "-- เลือกธนาคาร --" else "", edit_bank_acc, st.session_state["current_online_user"]))
            conn.commit(); conn.close(); st.toast("บันทึกแล้ว!"); time.sleep(0.5); st.rerun()
            
    if st.sidebar.button("🚪 ออกจากระบบ"):
        st.session_state["current_online_user"] = None
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🌐 ออนไลน์")
online_users = get_currently_online_users()
for o_user in online_users:
    st.sidebar.markdown(f"{'🌟' if o_user == st.session_state['current_online_user'] else '🟢'} **{o_user}**")

# --- การเลือก Event ---
st.sidebar.markdown("---")
conn = get_db_connection()
active_trips = conn.execute("SELECT * FROM trips WHERE status = 0").fetchall()
conn.close()

if not active_trips:
    st.sidebar.info("สร้าง Event ใหม่เพื่อเริ่ม")
    new_t_name = st.sidebar.text_input("ชื่อ Event ใหม่:")
    if st.sidebar.button("สร้าง") and new_t_name:
        conn = get_db_connection(); conn.execute("INSERT INTO trips (name, trip_date) VALUES (?, ?)", (new_t_name, datetime.today().strftime("%Y-%m-%d")))
        conn.commit(); conn.close(); st.rerun()
    st.stop()

trip_options = {f"{t['name']} ({t['trip_date']})": t['id'] for t in active_trips}
selected_t_display = st.sidebar.selectbox("🗺️ เลือก Event:", list(trip_options.keys()))
trip_id = trip_options[selected_t_display]
current_trip = selected_t_display.split(" (")[0]

# --- สมาชิกใน Event ---
conn = get_db_connection()
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
all_system_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
conn.close()

st.sidebar.subheader("👥 สมาชิกในกลุ่ม")
for m in existing_members:
    st.sidebar.caption(f"👤 {m}")
new_mem = st.sidebar.selectbox("ชวนเพื่อน:", ["-- เลือก --"] + [u for u in all_system_users if u not in existing_members])
if st.sidebar.button("ดึงเข้ากลุ่ม") and new_mem != "-- เลือก --":
    conn = get_db_connection(); conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, new_mem))
    conn.commit(); conn.close(); st.rerun()

# 🔔 ================= ระบบแจ้งเตือนใน SIDEBAR =================
st.sidebar.markdown("---")
st.sidebar.header("🔔 กล่องข้อความของคุณ")
if st.session_state["current_online_user"]:
    my_name = st.session_state["current_online_user"]
    conn = get_db_connection()
    my_notifs = conn.execute("SELECT * FROM notifications WHERE trip_id = ? AND to_user = ? ORDER BY id DESC", (trip_id, my_name)).fetchall()
    conn.close()
    
    with st.sidebar.expander(f"📥 ข้อความใหม่ ({len(my_notifs)})", expanded=True):
        if not my_notifs: st.caption("ไม่มีข้อความ")
        for notif in my_notifs:
            st.info(f"✍️ **จาก:** {notif['from_user']}\n\n{notif['message']}")
            if st.button("🗑️ ลบ", key=f"del_{notif['id']}", use_container_width=True):
                conn = get_db_connection(); conn.execute("DELETE FROM notifications WHERE id = ?", (notif['id'],))
                conn.commit(); conn.close(); st.rerun()
# ==========================================================

# --- 5. พื้นที่ทำงานหลัก ---
st.title(f"✈️ {selected_t_display}")
tab1, tab2, tab3 = st.tabs(["📝 สร้างบิลใหม่", "📊 ประวัติบิล", "💰 สรุปเคลียร์เงิน"])

with tab1:
    if not existing_members: st.warning("กรุณาเพิ่มสมาชิกในกลุ่มก่อนที่แถบซ้ายมือ"); st.stop()
    with st.form("add_bill"):
        desc = st.text_input("รายการ:")
        amt = st.number_input("จำนวนเงิน:", min_value=0.0)
        payer = st.selectbox("ใครสำรองจ่าย:", existing_members)
        st.write("คนหาร:")
        split_to = [m for m in existing_members if st.checkbox(m, value=True, key=f"split_{m}")]
        file = st.file_uploader("รูปสลิป:", type=['jpg','png','jpeg'])
        if st.form_submit_button("💾 บันทึกบิล") and desc and amt > 0 and split_to:
            blob = compress_image(file)
            conn = get_db_connection()
            conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                         (trip_id, desc, amt, payer, ",".join(split_to), blob))
            conn.commit(); conn.close(); st.success("บันทึกสำเร็จ!"); time.sleep(0.5); st.rerun()

with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    for row in expenses:
        with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} (โดย {row['payer_name']})"):
            if row['image_blob']: st.image(row['image_blob'])
            if st.button("🗑️ ลบรายการ", key=f"del_exp_{row['id']}"):
                conn = get_db_connection(); conn.execute("DELETE FROM expenses WHERE id=?", (row['id'],))
                conn.commit(); conn.close(); st.rerun()

with tab3:
    st.header("🚀 แผนการโอนเงินคืน")
    conn = get_db_connection()
    expenses_rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    user_profiles = {row['name']: {"promptpay": row['promptpay'], "bank_name": row['bank_name'], "bank_acc": row['bank_account']} 
                     for row in conn.execute("SELECT name, promptpay, bank_name, bank_account FROM all_users").fetchall()}
    conn.close()
    
    if not expenses_rows: st.info("ยังไม่มีข้อมูลค่าใช้จ่าย")
    else:
        net = {m: 0.0 for m in existing_members}
        for r in expenses_rows:
            net[r['payer_name']] += r['amount']
            s_list = r['split_members'].split(",")
            share = r['amount'] / len(s_list)
            for m in s_list: net[m] -= share
            
        debtors = [[m, b] for m, b in net.items() if b < -0.01]
        creditors = [[m, b] for m, b in net.items() if b > 0.01]
        
        while debtors and creditors:
            amt = min(abs(debtors[0][1]), creditors[0][1])
            d_name, c_name = debtors[0][0], creditors[0][0]
            prof = user_profiles.get(c_name, {})
            pp, b_name, b_acc = prof.get("promptpay") or "", prof.get("bank_name") or "", prof.get("bank_acc") or ""
            
            st.markdown(f"💳 **{d_name}** โอนให้ 👉 **{c_name}** จำนวน **{amt:,.2f}** บาท")
            
            # 🟢 ปุ่มส่งเรียกเก็บเงินเข้ากล่องข้อความ
            if st.button(f"📲 ส่งคำขอเก็บเงินไปที่ {d_name}", key=f"notif_{d_name}_{c_name}_{amt}"):
                auto_msg = f"รบกวนโอนค่าทริป '{current_trip}' จำนวน {amt:,.2f} บาท ให้ {c_name} ด้วยน้า"
                if pp: auto_msg += f"\n📱 พร้อมเพย์: {pp}"
                if b_acc: auto_msg += f"\n🏦 {b_name}: {b_acc}"
                conn = get_db_connection()
                conn.execute("INSERT INTO notifications (trip_id, to_user, from_user, message) VALUES (?,?,?,?)", (trip_id, d_name, c_name, auto_msg))
                conn.commit(); conn.close(); st.toast(f"ส่งข้อความหา {d_name} แล้ว!")

            if pp or b_acc:
                c1, c2 = st.columns(2)
                if pp: c1.code(f"PromptPay: {pp}")
                if b_acc: c2.code(f"{b_name}: {b_acc}")
            else: st.warning(f"⚠️ {c_name} ยังไม่ระบุเลขบัญชี")
            st.write("---")
            debtors[0][1] += amt; creditors[0][1] -= amt
            if abs(debtors[0][1]) < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)
