import streamlit as st
import pandas as pd
import sqlite3
import io
import time
from PIL import Image
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# 1. Setup & Auto-Refresh
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")
st_autorefresh(interval=1000, limit=None, key="trip_app_live_refresh")

DB_FILE = "trip_database.db"
BANK_LIST = ["-- เลือกธนาคาร --", "กสิกรไทย (KBank)", "ไทยพาณิชย์ (SCB)", "กรุงไทย (KTB)", "กรุงเทพ (BBL)", "กรุงศรีอยุธยา (BAY)", "ทหารไทยธนชาต (TTB)", "ออมสิน (GSB)", "ธ.ก.ส.", "ยูโอบี (UOB)"]

# 2. Database Functions
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, promptpay TEXT, bank_name TEXT, bank_account TEXT)')
        cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, status INTEGER DEFAULT 0, trip_date TEXT)')
        cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id))')
        cursor.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB, FOREIGN KEY(trip_id) REFERENCES trips(id))')
        cursor.execute('CREATE TABLE IF NOT EXISTS settlements (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(trip_id) REFERENCES trips(id))')
        cursor.execute('CREATE TABLE IF NOT EXISTS online_status (name TEXT PRIMARY KEY, last_seen DATETIME)')
        cursor.execute('''CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, to_user TEXT, from_user TEXT, message TEXT, 
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, is_auto INTEGER DEFAULT 0, is_read INTEGER DEFAULT 0, FOREIGN KEY(trip_id) REFERENCES trips(id))''')
        
        # Migration checks
        for tbl, col, df_val in [('all_users', 'promptpay', 'TEXT'), ('all_users', 'bank_name', 'TEXT'), ('all_users', 'bank_account', 'TEXT'), ('trips', 'trip_date', 'TEXT'), ('notifications', 'is_auto', 'INTEGER DEFAULT 0'), ('notifications', 'is_read', 'INTEGER DEFAULT 0'), ('notifications', 'timestamp', 'DATETIME DEFAULT CURRENT_TIMESTAMP')]:
            cursor.execute(f"PRAGMA table_info({tbl})")
            if col not in [r[1] for r in cursor.fetchall()]:
                cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {df_val}" if 'DEFAULT' in df_val or df_val=='TEXT' else f"ALTER TABLE {tbl} ADD COLUMN {col} {df_val}")
        conn.commit()

def compress_image(uploaded_file):
    if not uploaded_file: return None
    img = Image.open(uploaded_file).convert("RGB") if Image.open(uploaded_file).mode in ("RGBA", "P") else Image.open(uploaded_file)
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()

def update_online_heartbeat(username):
    if username:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO online_status (name, last_seen) VALUES (?, datetime('now', 'localtime')) ON CONFLICT(name) DO UPDATE SET last_seen = datetime('now', 'localtime')", (username,))
            conn.commit()

def get_currently_online_users():
    with get_db_connection() as conn:
        return [r["name"] for r in conn.execute("SELECT name FROM online_status WHERE last_seen >= datetime('now', 'localtime', '-15 seconds')").fetchall()]

init_db()

# 3. Session Status
if "current_online_user" not in st.session_state: st.session_state["current_online_user"] = None
my_user = st.session_state["current_online_user"]
if my_user: update_online_heartbeat(my_user)

# 4. Sidebar UI
st.sidebar.header("🔐 บัญชีผู้ใช้งานเครื่องนี้")
with get_db_connection() as conn:
    existing_all_users = [r["name"] for r in conn.execute("SELECT name FROM all_users").fetchall()]

if not my_user:
    st.sidebar.warning("⚠️ เครื่องนี้ยังไม่ได้ล็อกอินโปรไฟล์")
    login_mode = st.sidebar.radio("ทางเลือกบัญชี:", ["เลือกโปรไฟล์", "สร้างโปรไฟล์ใหม่"], horizontal=True)
    
    if login_mode == "เลือกโปรไฟล์":
        if existing_all_users:
            user_select = st.sidebar.selectbox("เลือกชื่อของคุณ:", existing_all_users)
            if st.sidebar.button("เข้าสู่ระบบ"):
                st.session_state["current_online_user"] = user_select
                update_online_heartbeat(user_select)
                st.toast(f"👋 ยินดีต้อนรับกลับมา, {user_select}!"); time.sleep(1); st.rerun()
        else: st.sidebar.caption("ยังไม่มีข้อมูลสมาชิก กรุณาสร้างใหม่")
    else:
        new_name = st.sidebar.text_input("ระบุชื่อเล่น/ชื่อของคุณ:").strip()
        if st.sidebar.button("สร้างและเข้าสู่ระบบ"):
            if new_name:
                try:
                    with get_db_connection() as conn:
                        conn.execute("INSERT INTO all_users (name) VALUES (?)", (new_name,))
                        conn.commit()
                    st.session_state["current_online_user"] = new_name
                    update_online_heartbeat(new_name)
                    st.sidebar.success(f"🎉 สร้างโปรไฟล์ '{new_name}' สำเร็จ!"); time.sleep(1); st.rerun()
                except: st.sidebar.error("❌ ชื่อนี้มีในระบบแล้ว")
            else: st.sidebar.error("⚠️ กรุณากรอกชื่อ")
else:
    st.sidebar.success(f"🟢 ผู้ใช้งาน: **{my_user}**")
    with get_db_connection() as conn:
        my_data = conn.execute("SELECT * FROM all_users WHERE name = ?", (my_user,)).fetchone()
    
    with st.sidebar.expander("⚙️ Update ข้อมูลส่วนตัว"):
        edit_pp = st.text_input("เลขพร้อมเพย์:", value=my_data['promptpay'] or "")
        bank_idx = BANK_LIST.index(my_data['bank_name']) if my_data['bank_name'] in BANK_LIST else 0
        edit_bank = st.selectbox("เลือกธนาคาร:", BANK_LIST, index=bank_idx)
        edit_acc = st.text_input("เลขบัญชีธนาคาร:", value=my_data['bank_account'] or "")
        
        if st.button("💾 บันทึกข้อมูลส่วนตัว"):
            with get_db_connection() as conn:
                conn.execute("UPDATE all_users SET promptpay=?, bank_name=?, bank_account=? WHERE name=?", (edit_pp, edit_bank if edit_bank != "-- เลือกธนาคาร --" else "", edit_acc, my_user))
                conn.commit()
            st.toast("💾 บันทึกโปรไฟล์สำเร็จ!"); time.sleep(1); st.rerun()
            
    if st.sidebar.button("🚪 ออกจากระบบ"):
        with get_db_connection() as conn:
            conn.execute("DELETE FROM online_status WHERE name = ?", (my_user,))
            conn.commit()
        st.session_state["current_online_user"] = None; st.rerun()

# Online Members List
st.sidebar.markdown("---")
st.sidebar.subheader("🌐 สมาชิกที่ออนไลน์ในขณะนี้")
online_users = get_currently_online_users()
for o in online_users:
    st.sidebar.markdown(f"🌟 **{o}** *(คุณ)*" if o == my_user else f"🟢 **{o}** *(คนอื่น)*")
if not online_users: st.sidebar.caption("ไม่มีผู้ใช้งานอื่นออนไลน์")

# Create Event
st.sidebar.markdown("---")
st.sidebar.subheader("➕ สร้าง Event ใหม่")
new_trip = st.sidebar.text_input("ชื่อ Event:").strip()
new_date = st.sidebar.date_input("วันที่จัด Event:", value=datetime.today())

if st.sidebar.button("สร้าง Event ใหม่"):
    if new_trip:
        try:
            with get_db_connection() as conn:
                conn.execute("INSERT INTO trips (name, status, trip_date) VALUES (?, 0, ?)", (new_trip, new_date.strftime("%Y-%m-%d")))
                conn.commit()
            st.success(f"✈️ สร้าง Event '{new_trip}' สำเร็จ!"); time.sleep(1); st.rerun()
        except: st.sidebar.error("❌ ชื่อ Event ซ้ำ")
    else: st.sidebar.error("⚠️ กรุณากรอกชื่อ Event")

# Trash bin System
with st.sidebar.expander("🗑️ ถังขยะ"):
    with get_db_connection() as conn:
        deleted_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
    if not deleted_trips: st.caption("ไม่มีรายการในถังขยะ")
    for dt in deleted_trips:
        c1, c2 = st.columns([1.5, 1.5])
        c1.write(f"{dt['name']} ({dt['trip_date']})" if dt['trip_date'] else dt['name'])
        sub_c1, sub_c2 = c2.columns(2)
        if sub_c1.button("กู้คืน", key=f"res_{dt['id']}"):
            with get_db_connection() as conn: conn.execute("UPDATE trips SET status=0 WHERE id=?", (dt['id'],)); conn.commit()
            st.toast(f"🔄 กู้คืน '{dt['name']}' เรียบร้อย!"); time.sleep(1); st.rerun()
        if sub_c2.button("ลบ", key=f"pdel_{dt['id']}"):
            with get_db_connection() as conn:
                for t in ["settlements", "expenses", "members", "trips"]: conn.execute(f"DELETE FROM {t} WHERE {'trip_id' if t!='trips' else 'id'} = ?", (dt['id'],))
                conn.commit()
            st.toast(f"💥 ลบ '{dt['name']}' ถาวรแล้ว!"); time.sleep(1); st.rerun()

with get_db_connection() as conn:
    active_trips_df = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)

if active_trips_df.empty:
    st.title("✈️ Trip Expense Splitter Pro")
    st.info("กรุณาสร้าง Event ใหม่ หรือกู้คืนจากถังขยะที่เมนูซ้ายมือเพื่อเริ่มต้นระบบ"); st.stop()

active_trips_df['display_name'] = active_trips_df.apply(lambda r: f"{r['name']} 📅 ({r['trip_date']})" if r['trip_date'] else r['name'], axis=1)
st.sidebar.markdown("---")
sel_trip_disp = st.sidebar.selectbox("🗺️ เลือกEvent:", active_trips_df["display_name"].tolist())
matched_trip = active_trips_df[active_trips_df['display_name'] == sel_trip_disp].iloc[0]
trip_id, current_trip, current_trip_date = int(matched_trip['id']), matched_trip['name'], matched_trip['trip_date']

with st.sidebar.expander("✏️ แก้ไขข้อมูล Event ปัจจุบัน"):
    re_name = st.text_input("เปลี่ยนชื่อ Event เป็น:", value=current_trip).strip()
    try: def_date = datetime.strptime(str(current_trip_date), "%Y-%m-%d")
    except: def_date = datetime.today()
    re_date = st.date_input("แก้ไขวันที่จัด Event:", value=def_date)
    if st.button("💾 ยืนยันเปลี่ยนข้อมูล"):
        if re_name:
            try:
                with get_db_connection() as conn:
                    conn.execute("UPDATE trips SET name=?, trip_date=? WHERE id=?", (re_name, re_date.strftime("%Y-%m-%d"), trip_id))
                    conn.commit()
                st.success("✏️ อัปเดตข้อมูลสำเร็จ!"); time.sleep(1); st.rerun()
            except: st.error("❌ ชื่อ Event นี้ซ้ำ")
        else: st.error("⚠️ กรุณากรอกชื่อ")

if st.sidebar.button("🗑️ ลบ Event"):
    with get_db_connection() as conn: conn.execute("UPDATE trips SET status = 1 WHERE id = ?", (trip_id,)); conn.commit()
    st.toast(f"🗑️ ย้าย '{current_trip}' ลงถังขยะแล้ว"); time.sleep(1); st.rerun()

# Event Members Management
st.sidebar.subheader("👥 สมาชิกภายใน Event")
with get_db_connection() as conn:
    all_users_list = [r["name"] for r in conn.execute("SELECT name FROM all_users").fetchall()]
    existing_members = [r["name"] for r in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_users = [u for u in all_users_list if u not in existing_members]

for mem in existing_members:
    m1, m2 = st.sidebar.columns([4, 1])
    with get_db_connection() as conn:
        unread_c = conn.execute("SELECT COUNT(*) as cnt FROM notifications WHERE trip_id=? AND to_user=? AND is_read=0", (trip_id, mem)).fetchone()["cnt"]
    badge = f" ✉️ ({unread_c})" if unread_c > 0 else ""
    m1.caption(f"{'🟢 ' if mem in online_users else '⚪ '}{mem}{' (คุณ)' if mem==my_user else ''}{badge}")
    if m2.button("ออก", key=f"rm_{mem}"):
        with get_db_connection() as conn: conn.execute("DELETE FROM members WHERE trip_id=? AND name=?", (trip_id, mem)); conn.commit()
        st.toast(f"🗑️ ถอด {mem} ออกแล้ว"); time.sleep(1); st.rerun()

sel_u = st.sidebar.selectbox("ชวนเพื่อนออนไลน์เข้าร่วมบิล:", ["-- เลือกเพื่อน --"] + available_users)
if st.sidebar.button("ดึงเข้ากลุ่ม") and sel_u != "-- เลือกเพื่อน --":
    with get_db_connection() as conn: conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, sel_u)); conn.commit()
    st.toast(f"➕ ดึง {sel_u} เข้ากลุ่มสำเร็จ!"); time.sleep(1); st.rerun()

# 🔔 Chat & Notification Center
st.sidebar.markdown("---")
if my_user:
    with get_db_connection() as conn:
        notif_count = conn.execute("SELECT COUNT(*) as cnt FROM notifications WHERE trip_id=? AND to_user=? AND is_read=0", (trip_id, my_user)).fetchone()["cnt"]
    st.sidebar.markdown(f"### 🔔 ศูนย์แชทส่วนตัว <span style='color:#FF4B4B; font-size:16px;'>🔴 ({notif_count})</span>" if notif_count > 0 else "### 🔔 ศูนย์แชทส่วนตัว", unsafe_allow_html=True)
    
    with get_db_connection() as conn:
        all_chats = conn.execute("SELECT * FROM notifications WHERE trip_id=? AND (to_user=? OR from_user=? OR (to_user=? AND is_auto=1)) ORDER BY timestamp ASC, id ASC", (trip_id, my_user, my_user, my_user)).fetchall()
    
    chat_groups, unread_status = {}, {}
    for n in all_chats:
        p = "ระบบสรุปยอด" if (n['is_auto'] == 1 or n['from_user'] == "ระบบสรุปยอด") else (n['from_user'] if n['to_user'] == my_user else n['to_user'])
        chat_groups.setdefault(p, []).append(n)
        unread_status[p] = unread_status.get(p, 0) + (1 if (n['to_user'] == my_user and n['is_read'] == 0) else 0)

    with st.sidebar.expander(f"📥 แชทและการแจ้งเตือน ({len(chat_groups)})", expanded=True):
        if not chat_groups: st.caption("ไม่มีประวัติข้อความ")
        else:
            p_keys = list(chat_groups.keys())
            tabs = st.tabs([f"🤖 ระบบ (🔴 {unread_status[pk]})" if pk=="ระบบสรุปยอด" and unread_status[pk]>0 else f"🤖 ระบบ" if pk=="ระบบสรุปยอด" else f"👤 {pk} (🔴 {unread_status[pk]})" if unread_status[pk]>0 else f"👤 {pk}" for pk in p_keys])
            
            for idx, pk in enumerate(p_keys):
                with tabs[idx]:
                    if unread_status[pk] > 0:
                        with get_db_connection() as conn:
                            conn.execute("UPDATE notifications SET is_read=1 WHERE trip_id=? AND to_user=? AND is_auto=1 AND is_read=0" if pk=="ระบบสรุปยอด" else "UPDATE notifications SET is_read=1 WHERE trip_id=? AND to_user=? AND from_user=? AND is_read=0", (trip_id, my_user) if pk=="ระบบสรุปยอด" else (trip_id, my_user, pk))
                            conn.commit()
                        st.rerun()
                    
                    for nt in chat_groups[pk]:
                        t_str = nt['timestamp'][11:16] if nt['timestamp'] else ""
                        is_me = (nt['from_user'] == my_user and nt['is_auto'] == 0)
                        is_sys = (nt['from_user'] == "ระบบสรุปยอด" or nt['is_auto'] == 1)
                        
                        bg, align, border, name_lbl = ("#85E374", "flex-end", "15px 15px 2px 15px", "") if is_me else (("#D6E4FF", "flex-start", "2px 15px 15px 15px", "🤖 ระบบ") if is_sys else ("#EAEAEA", "flex-start", "2px 15px 15px 15px", f"👤 {nt['from_user']}"))
                        st.markdown(f'''<div style="display:flex; flex-direction:column; align-items:{align}; margin-bottom:5px; width:100%;">
                            {f'<span style="font-size:11px; color:#4A90E2; font-weight:bold;">{name_lbl}</span>' if name_lbl else ''}
                            <div style="display:flex; align-items:flex-end;">
                                {f'<span style="font-size:9px; color:#AAA; margin-right:5px;">{t_str}</span>' if is_me else ''}
                                <div style="background-color:{bg}; color:#000; padding:6px 10px; border-radius:{border}; max-width:200px; word-wrap:break-word; font-size:12px; {'border-left: 4px solid #4A90E2;' if is_sys else ''}">{nt['message']}</div>
                                {f'<span style="font-size:9px; color:#AAA; margin-left:5px;">{t_str}</span>' if not is_me else ''}
                            </div>
                        </div>''', unsafe_allow_html=True)
                        
                        if st.button("🗑️ ลบ", key=f"del_{nt['id']}", type="secondary"):
                            with get_db_connection() as conn: conn.execute("DELETE FROM notifications WHERE id=?", (nt['id'],)); conn.commit()
                            st.toast("ลบแล้ว"); time.sleep(0.3); st.rerun()
                    
                    if pk != "ระบบสรุปยอด":
                        with st.form(key=f"fm_{pk}", clear_on_submit=True):
                            txt = st.text_input("พิมพ์ตอบกลับ:", placeholder=f"คุยกับ {pk}...", key=f"txt_{pk}")
                            if st.form_submit_button("↩️ ตอบกลับ") and txt.strip():
                                with get_db_connection() as conn:
                                    conn.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?,?,?,?,0,0,datetime('now', 'localtime'))", (trip_id, pk, my_user, txt.strip()))
                                    conn.commit()
                                st.toast("🚀 ส่งแล้ว!"); time.sleep(0.3); st.rerun()

    with st.sidebar.expander("📝 เปิดกล่องคุยกับเพื่อนใหม่"):
        others = [m for m in existing_members if m != my_user]
        if others:
            to_user = st.selectbox("เลือกเพื่อน:", others)
            with st.form(key="new_chat", clear_on_submit=True):
                new_msg = st.text_area("ข้อความ:")
                if st.form_submit_button("🚀 ส่งแชท") and new_msg.strip():
                    with get_db_connection() as conn:
                        conn.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?,?,?,?,0,0,datetime('now', 'localtime'))", (trip_id, to_user, my_user, new_msg.strip()))
                        conn.commit()
                    st.toast("🚀 ส่งแล้ว!"); time.sleep(0.3); st.rerun()
        else: st.caption("ไม่มีสมาชิกอื่น")
else: st.sidebar.caption("กรุณาเข้าสู่ระบบเพื่อใช้งานแชท")

# 5. Main Content Area
if not my_user:
    st.title("🛄 กรุณาระบุข้อมูลผู้ใช้งานเครื่องนี้ก่อน")
    st.info("กรุณาเลือกโปรไฟล์ของคุณหรือสร้างผู้ใช้ใหม่ที่แถบซ้ายบน เพื่อเริ่มเปิดดูสถิติและลงรายการบิล"); st.stop()

if not existing_members:
    st.title(f"✈️ Event: {current_trip}")
    if current_trip_date: st.caption(f"📅 วันที่จัดทริป: {current_trip_date}")
    st.warning("⚠️ ยังไม่มีใครอยู่ในกลุ่มนี้เลย ชวนเพื่อนหรือตัวคุณเองที่แถบซ้ายมือก่อนครับ"); st.stop()

st.title(f"✈️ ข้อมูล Event: {current_trip}")
if current_trip_date: st.subheader(f"📅 วันที่จัด: {current_trip_date}")

tab1, tab2, tab3 = st.tabs(["📝 สร้างบิลใหม่", "📊 ประวัติบันทึกบิล", "💰 สรุปเคลียร์เงินสมาชิก"])

with tab1:
    with st.form("add_bill", clear_on_submit=True):
        st.header("➕ เพิ่มบิลค่าใช้จ่าย")
        desc = st.text_input("รายการ:")
        amt = st.number_input("จำนวนเงิน:", min_value=0.0)
        payer = st.selectbox("คนสำรองจ่ายเงินก่อน:", existing_members, index=existing_members.index(my_user) if my_user in existing_members else 0)
        st.write("คนร่วมหารในบิลนี้:")
        split_to = [m for m in existing_members if st.checkbox(m, value=True, key=f"add_{m}")]
        file = st.file_uploader("แนบรูปภาพสลิปเงิน:", type=['jpg','png','jpeg'])
        
        if st.form_submit_button("💾 บันทึกบิล", type="primary"):
            if desc and amt > 0 and split_to:
                blob = compress_image(file)
                with get_db_connection() as conn:
                    conn.cursor().execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)", (trip_id, desc, amt, payer, ",".join(split_to), blob))
                    share = amt / len(split_to)
                    for m in split_to:
                        if m != payer:
                            conn.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?,?,'ระบบสรุปยอด',?,1,0,datetime('now', 'localtime'))", 
                                         (trip_id, m, f"📌 บิลใหม่: '{desc}'\n💰 ยอดรวม {amt:,.2f} บาท\n👤 คนจ่าย: {payer}\n💸 ส่วนของคุณคือ: {share:,.2f} บาท"))
                    conn.commit()
                st.success(f"📝 บันทึกรายการบิล '{desc}' สำเร็จ!"); time.sleep(1); st.rerun()
            else: st.error("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")

with tab2:
    with get_db_connection() as conn:
        expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    if not expenses: st.info("ยังไม่มีข้อมูลค่าใช้จ่ายในกลุ่มนี้")
    else:
        for row in expenses:
            with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} บาท (โดย {row['payer_name']})"):
                pass # พื้นที่แสดงข้อมูลเพิ่มเติมของแต่ละบิล
