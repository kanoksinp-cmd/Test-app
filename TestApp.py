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

# 🔄 รีเฟรชหน้าจออัตโนมัติเพื่อให้แชทอัปเดตแบบ Real-time
st_autorefresh(interval=1000, limit=None, key="trip_app_live_refresh")

DB_FILE = "trip_database.db"

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

# 3. Session Management
if "current_online_user" not in st.session_state:
    st.session_state["current_online_user"] = None

if st.session_state["current_online_user"]:
    update_online_heartbeat(st.session_state["current_online_user"])

# --- 4. SIDEBAR & โปรไฟล์ ---
st.sidebar.header("🔐 โปรไฟล์ผู้ใช้งาน")
conn = get_db_connection()
existing_all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
conn.close()

if st.session_state["current_online_user"] is None:
    login_mode = st.sidebar.radio("เข้าใช้งาน:", ["เลือกชื่อเดิม", "สร้างใหม่"], horizontal=True)
    if login_mode == "เลือกชื่อเดิม" and existing_all_users:
        u_sel = st.sidebar.selectbox("ชื่อของคุณ:", existing_all_users)
        if st.sidebar.button("เข้าสู่ระบบ"):
            st.session_state["current_online_user"] = u_sel
            st.rerun()
    else:
        n_name = st.sidebar.text_input("ชื่อเล่น:").strip()
        if st.sidebar.button("สร้างโปรไฟล์"):
            if n_name:
                conn = get_db_connection()
                try:
                    conn.execute("INSERT INTO all_users (name) VALUES (?)", (n_name,))
                    conn.commit(); st.session_state["current_online_user"] = n_name; st.rerun()
                except: st.sidebar.error("ชื่อซ้ำ")
                finally: conn.close()
else:
    st.sidebar.success(f"🟢 ออนไลน์: {st.session_state['current_online_user']}")
    if st.sidebar.button("🚪 ออกจากระบบ"):
        st.session_state["current_online_user"] = None; st.rerun()

# --- 5. ค้นหาทริปปัจจุบัน ---
st.sidebar.markdown("---")
conn = get_db_connection()
active_trips_df = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)
if not active_trips_df.empty:
    sel_trip = st.sidebar.selectbox("🗺️ เลือก Event:", active_trips_df['name'].tolist())
    trip_id = int(active_trips_df[active_trips_df['name'] == sel_trip]['id'].iloc[0])
    current_trip_date = active_trips_df[active_trips_df['name'] == sel_trip]['trip_date'].iloc[0]
else:
    st.sidebar.warning("สร้าง Event ใหม่ก่อน")
    st.stop()
conn.close()

# --- 6. 💬 ระบบแชท (นำกลับมาให้แล้ว) ---
st.sidebar.markdown("---")
if st.session_state["current_online_user"]:
    my_name = st.session_state["current_online_user"]
    conn = get_db_connection()
    # นับข้อความที่ยังไม่อ่าน
    count_row = conn.execute("SELECT COUNT(*) as cnt FROM notifications WHERE trip_id = ? AND to_user = ? AND is_read = 0", (trip_id, my_name)).fetchone()
    unread_cnt = count_row['cnt'] if count_row else 0
    
    st.sidebar.subheader(f"🔔 แชท & แจ้งเตือน {'🔴' if unread_cnt > 0 else ''}")
    
    with st.sidebar.expander(f"📥 เปิดกล่องข้อความ ({unread_cnt})", expanded=unread_cnt > 0):
        messages = conn.execute("SELECT * FROM notifications WHERE trip_id = ? AND (to_user = ? OR from_user = ?) ORDER BY timestamp DESC LIMIT 10", (trip_id, my_name, my_name)).fetchall()
        if not messages:
            st.caption("ไม่มีข้อความ")
        else:
            for m in messages:
                role = "คุณ" if m['from_user'] == my_name else m['from_user']
                st.markdown(f"**{role}:** {m['message']}")
                if m['to_user'] == my_name and m['is_read'] == 0:
                    if st.button("อ่านแล้ว", key=f"read_{m['id']}"):
                        conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (m['id'],))
                        conn.commit(); st.rerun()
                st.divider()
        
        # ส่งข้อความใหม่
        members_in_trip = [r['name'] for r in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall() if r['name'] != my_name]
        if members_in_trip:
            st.write("ส่งข้อความถึง:")
            target = st.selectbox("เลือกเพื่อน:", members_in_trip, key="chat_target")
            msg_input = st.text_input("พิมพ์ข้อความ:", key="chat_msg")
            if st.button("🚀 ส่งแชท"):
                conn.execute("INSERT INTO notifications (trip_id, to_user, from_user, message) VALUES (?,?,?,?)", (trip_id, target, my_name, msg_input))
                conn.commit(); st.toast("ส่งแล้ว!"); st.rerun()
    conn.close()

# --- 7. พื้นที่หลัก TAB ---
st.title(f"✈️ Event: {sel_trip}")
tab1, tab2, tab3 = st.tabs(["📝 สร้างบิลใหม่", "📊 ประวัติบิล", "💰 สรุปเคลียร์เงิน"])

with tab1:
    conn = get_db_connection()
    existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
    conn.close()
    with st.form("add_bill"):
        st.header("➕ เพิ่มบิล")
        desc = st.text_input("รายการ:")
        amt = st.number_input("จำนวนเงิน:", min_value=0.0)
        payer = st.selectbox("คนจ่าย:", existing_members if existing_members else [my_name])
        splitters = [m for m in existing_members if st.checkbox(m, value=True, key=f"split_{m}")]
        if st.form_submit_button("บันทึก"):
            if desc and amt > 0:
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members) VALUES (?,?,?,?,?)",
                             (trip_id, desc, amt, payer, ",".join(splitters)))
                conn.commit(); conn.close(); st.success("บันทึกสำเร็จ"); st.rerun()

with tab2:
    conn = get_db_connection()
    exps = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    for e in exps:
        st.write(f"📌 {e['description']} | {e['amount']} บาท (โดย {e['payer_name']})")
    conn.close()

# ==================== TAB 3: สรุปยอดแบบเดิม (ตามภาพ) ====================
with tab3:
    st.header("🤝 สรุปยอดแผนการกระจายเงิน")
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
    
    if not expenses:
        st.info("ยังไม่มีข้อมูลค่าใช้จ่าย")
    else:
        balance = {m: 0.0 for m in members}
        for row in expenses:
            p, a = row['payer_name'], row['amount']
            sm = row['split_members'].split(',') if row['split_members'] else []
            if not sm: continue
            share = a / len(sm)
            if p in balance: balance[p] += a
            for m in sm:
                if m in balance: balance[m] -= share

        creditors = [[n, b] for n, b in balance.items() if b > 0.01]
        debtors = [[n, -b] for n, b in balance.items() if b < -0.01]

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("🟢 **คนที่ต้องได้รับเงินคืน:**")
            for cn, ca in creditors: st.success(f"{cn}: {ca:,.2f} บาท")
        with c2:
            st.markdown("🔴 **คนที่ต้องจ่ายออก:**")
            for dn, da in debtors: st.error(f"{dn}: {da:,.2f} บาท")

        st.markdown("---")
        st.header("🚀 แผนการโอนเงินคืน")
        summary_text = f"📊 สรุปยอดทริป: {sel_trip}\n----------------------------\n"
        
        i, j = 0, 0
        while i < len(debtors) and j < len(creditors):
            dn, da = debtors[i]
            cn, ca = creditors[j]
            settled = min(da, ca)
            
            b_data = conn.execute("SELECT promptpay FROM all_users WHERE name = ?", (cn,)).fetchone()
            pp = b_data['promptpay'] if b_data and b_data['promptpay'] else "ยังไม่ได้ระบุ"

            st.markdown(f"💳 **{dn}** โอนให้ 👉 **{cn}** จำนวน **{settled:,.2f} บาท** ****")
            st.caption(f"📭 พร้อมเพย์ {cn}")
            st.code(pp, language="")
            
            summary_text += f"💳 {dn} โอนให้ 👉 {cn} = {settled:,.2f} บาท\n( 📭 พร้อมเพย์: {pp} )\n"
            debtors[i][1] -= settled; creditors[j][1] -= settled
            if debtors[i][1] < 0.01: i += 1
            if creditors[j][1] < 0.01: j += 1

        st.markdown("---")
        st.header("📲 ส่งสรุปยอดเข้า LINE")
        line_msg = st.text_area("สรุปยอดสำหรับแชร์:", value=summary_text, height=150)
        encoded_msg = urllib.parse.quote(line_msg)
        st.markdown(f"""<a href="https://line.me/R/msg/text/?{encoded_msg}" target="_blank" style="text-decoration: none;">
                <div style="background-color: #ff4b4b; color: white; padding: 10px; border-radius: 10px; text-align: center; font-weight: bold;">
                    🟢 แชร์สรุปยอดเข้าแอป LINE
                </div></a>""", unsafe_allow_html=True)
    conn.close()
