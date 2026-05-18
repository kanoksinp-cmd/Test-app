import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
import urllib.parse
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# 1. ตั้งค่าหน้าจอ
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# 🔄 รีเฟรชหน้าจออัตโนมัติทุกๆ 1 วินาที เพื่อให้แชทและสถานะออนไลน์สดใหม่เสมอ
st_autorefresh(interval=1000, limit=None, key="trip_app_live_refresh")

DB_FILE = "trip_database.db"
BANK_LIST = ["-- เลือกธนาคาร --", "กสิกรไทย", "ไทยพาณิชย์", "กรุงไทย", "กรุงเทพ", "กรุงศรี", "ทหารไทยธนชาต", "ออมสิน", "ธ.ก.ส.", "ยูโอบี"]

# 2. ฟังก์ชันจัดการฐานข้อมูล
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, promptpay TEXT, bank_name TEXT, bank_account TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, status INTEGER DEFAULT 0, trip_date TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB)')
    cursor.execute('CREATE TABLE IF NOT EXISTS online_status (name TEXT PRIMARY KEY, last_seen DATETIME)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, to_user TEXT, from_user TEXT, 
                        message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, is_auto INTEGER DEFAULT 0, is_read INTEGER DEFAULT 0)''')
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
        conn.commit(); conn.close()

def get_currently_online_users():
    conn = get_db_connection()
    rows = conn.execute("SELECT name FROM online_status WHERE last_seen >= datetime('now', 'localtime', '-15 seconds')").fetchall()
    conn.close()
    return [row["name"] for row in rows]

init_db()

# 3. จัดการ Session สมาชิก
if "current_online_user" not in st.session_state:
    st.session_state["current_online_user"] = None

if st.session_state["current_online_user"]:
    update_online_heartbeat(st.session_state["current_online_user"])

# --- 4. SIDEBAR ---
st.sidebar.header("🔐 โปรไฟล์ผู้ใช้งาน")
conn = get_db_connection()
existing_all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
conn.close()

if st.session_state["current_online_user"] is None:
    login_mode = st.sidebar.radio("เข้าใช้งาน:", ["เลือกชื่อที่มีอยู่", "สร้างชื่อใหม่"], horizontal=True)
    if login_mode == "เลือกชื่อที่มีอยู่" and existing_all_users:
        user_select = st.sidebar.selectbox("ชื่อของคุณ:", existing_all_users)
        if st.sidebar.button("เข้าสู่ระบบ"):
            st.session_state["current_online_user"] = user_select
            st.rerun()
    else:
        new_name = st.sidebar.text_input("ชื่อเล่น/ชื่อจริง:").strip()
        if st.sidebar.button("สร้างโปรไฟล์"):
            if new_name:
                conn = get_db_connection()
                try:
                    conn.execute("INSERT INTO all_users (name) VALUES (?)", (new_name,))
                    conn.commit(); st.session_state["current_online_user"] = new_name; st.rerun()
                except: st.sidebar.error("ชื่อนี้ซ้ำ")
                finally: conn.close()
else:
    st.sidebar.success(f"🟢 ออนไลน์: {st.session_state['current_online_user']}")
    # อัปเดตข้อมูลบัญชี
    conn = get_db_connection()
    my_data = conn.execute("SELECT * FROM all_users WHERE name = ?", (st.session_state["current_online_user"],)).fetchone()
    with st.sidebar.expander("⚙️ ตั้งค่าบัญชีรับเงิน"):
        new_pp = st.text_input("เลขพร้อมเพย์:", value=my_data['promptpay'] if my_data['promptpay'] else "")
        new_bank_acc = st.text_input("เลขบัญชีธนาคาร:", value=my_data['bank_account'] if my_data['bank_account'] else "")
        if st.button("💾 บันทึก"):
            conn.execute("UPDATE all_users SET promptpay = ?, bank_account = ? WHERE name = ?", (new_pp, new_bank_acc, st.session_state["current_online_user"]))
            conn.commit(); st.toast("บันทึกสำเร็จ!"); time.sleep(0.5); st.rerun()
    if st.sidebar.button("🚪 ออกจากระบบ"):
        st.session_state["current_online_user"] = None; st.rerun()
    conn.close()

# --- 5. จัดการ Event (ทริป) ---
st.sidebar.markdown("---")
conn = get_db_connection()
active_trips_df = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)
if not active_trips_df.empty:
    selected_trip_name = st.sidebar.selectbox("🗺️ เลือก Event:", active_trips_df['name'].tolist())
    trip_id = int(active_trips_df[active_trips_df['name'] == selected_trip_name]['id'].iloc[0])
    current_trip_date = active_trips_df[active_trips_df['name'] == selected_trip_name]['trip_date'].iloc[0]
else:
    st.sidebar.info("สร้างทริปใหม่ก่อนครับ")
    st.title("🛄 กรุณาสร้าง Event ใหม่ที่เมนูด้านซ้าย")
    st.stop()
conn.close()

# --- 6. พื้นที่หลัก (Main UI) ---
st.title(f"✈️ ข้อมูล Event: {selected_trip_name}")
if current_trip_date:
    st.subheader(f"📅 วันที่จัด: {current_trip_date}")

tab1, tab2, tab3 = st.tabs(["📝 สร้างบิลใหม่", "📊 ประวัติบันทึกบิล", "💰 สรุปเคลียร์เงินสมาชิก"])

# 👥 สมาชิก (จัดการที่ Sidebar)
st.sidebar.subheader("👥 สมาชิกในกลุ่ม")
conn = get_db_connection()
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
all_u = [u for u in existing_all_users if u not in existing_members]
new_m = st.sidebar.selectbox("ชวนเพื่อนเข้ากลุ่ม:", ["-- เลือกเพื่อน --"] + all_u)
if st.sidebar.button("➕ เพิ่มเข้ากลุ่ม") and new_m != "-- เลือกเพื่อน --":
    conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, new_m))
    conn.commit(); st.rerun()
conn.close()

# ==================== TAB 1 & 2 (ย่อส่วนไว้เพื่อเน้น TAB 3) ====================
with tab1:
    with st.form("bill_form"):
        st.header("➕ เพิ่มบิลใหม่")
        d_val = st.text_input("รายการ:")
        a_val = st.number_input("จำนวนเงิน:", min_value=0.0)
        p_val = st.selectbox("ใครจ่ายก่อน:", existing_members)
        s_val = [m for m in existing_members if st.checkbox(m, value=True, key=f"s_{m}")]
        if st.form_submit_button("💾 บันทึก"):
            if d_val and a_val > 0:
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members) VALUES (?,?,?,?,?)",
                             (trip_id, d_val, a_val, p_val, ",".join(s_val)))
                conn.commit(); conn.close(); st.success("บันทึกบิลแล้ว!"); st.rerun()

with tab2:
    st.header("📊 รายการบิลทั้งหมด")
    conn = get_db_connection()
    exps = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    for e in exps:
        st.text(f"📌 {e['description']} | {e['amount']} บาท (โดย {e['payer_name']})")
    conn.close()

# ==================== TAB 3: สรุปเคลียร์เงินสมาชิก (แบบที่คุณต้องการ) ====================
with tab3:
    st.header("🤝 สรุปยอดแผนการกระจายเงิน")
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
    conn.close()

    if not expenses:
        st.info("ยังไม่มีข้อมูลค่าใช้จ่าย")
    else:
        balance = {m: 0.0 for m in members}
        for row in expenses:
            payer, amount = row['payer_name'], row['amount']
            split_members = row['split_members'].split(',') if row['split_members'] else []
            if not split_members: continue
            share = amount / len(split_members)
            if payer in balance: balance[payer] += amount
            for m in split_members:
                if m in balance: balance[m] -= share

        creditors = [[name, bal] for name, bal in balance.items() if bal > 0.01]
        debtors = [[name, -bal] for name, bal in balance.items() if bal < -0.01]

        col_c, col_d = st.columns(2)
        with col_c:
            st.markdown("🟢 **คนที่ต้องได้รับเงินคืน:**")
            for c_n, c_a in creditors: st.success(f"{c_n}: {c_a:,.2f} บาท")
        with col_d:
            st.markdown("🔴 **คนที่ต้องจ่ายออก:**")
            for d_n, d_a in debtors: st.error(f"{d_n}: {d_a:,.2f} บาท")

        st.markdown("---")
        st.header("🚀 แผนการโอนเงินคืน")
        
        summary_text = f"📊 สรุปยอดค่าใช้จ่ายทริป: {selected_trip_name}\n📅 วันที่: {current_trip_date if current_trip_date else '-'}\n----------------------------\n"
        temp_debtors, temp_creditors = [list(d) for d in debtors], [list(c) for c in creditors]
        i, j = 0, 0
        while i < len(temp_debtors) and j < len(temp_creditors):
            d_n, d_a = temp_debtors[i]
            c_n, c_a = temp_creditors[j]
            settled = min(d_a, c_a)
            
            conn = get_db_connection()
            bank_data = conn.execute("SELECT promptpay FROM all_users WHERE name = ?", (c_n,)).fetchone()
            conn.close()
            pp = bank_data['promptpay'] if bank_data and bank_data['promptpay'] else "ยังไม่ได้ระบุ"

            st.markdown(f"💳 **{d_n}** โอนให้ 👉 **{c_n}** จำนวน **{settled:,.2f} บาท** ****")
            st.caption(f"📭 พร้อมเพย์ {c_n}")
            st.code(pp, language="")
            
            summary_text += f"💳 {d_n} โอนให้ 👉 {c_n} = {settled:,.2f} บาท\n( 📭 พร้อมเพย์: {pp} )\n"
            
            temp_debtors[i][1] -= settled; temp_creditors[j][1] -= settled
            if temp_debtors[i][1] < 0.01: i += 1
            if temp_creditors[j][1] < 0.01: j += 1

        st.markdown("---")
        st.header("📲 ส่งสรุปยอดเข้า LINE")
        line_msg = st.text_area("สรุปยอดสำหรับคัดลอก:", value=summary_text, height=200)
        encoded_msg = urllib.parse.quote(line_msg)
        line_url = f"https://line.me/R/msg/text/?{encoded_msg}"
        
        st.markdown(f"""<a href="{line_url}" target="_blank" style="text-decoration: none;">
                <div style="background-color: #ff4b4b; color: white; padding: 10px; border-radius: 10px; text-align: center; font-weight: bold;">
                    🔴 แชร์สรุปยอดเข้าแอป LINE
                </div></a>""", unsafe_allow_html=True)
