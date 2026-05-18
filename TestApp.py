import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
import urllib.parse
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# 1. ตั้งค่าหน้าจอและโครงสร้างพื้นฐาน
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# 🔄 รีเฟรชหน้าจออัตโนมัติทุกๆ 1,000 มิลลิวินาที (1 วินาที)
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, to_user TEXT, from_user TEXT, message TEXT, 
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, is_auto INTEGER DEFAULT 0, is_read INTEGER DEFAULT 0,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')

    # ตรวจสอบและอัปเดตคอลัมน์
    cursor.execute("PRAGMA table_info(all_users)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'promptpay' not in columns: cursor.execute("ALTER TABLE all_users ADD COLUMN promptpay TEXT")
    if 'bank_name' not in columns: cursor.execute("ALTER TABLE all_users ADD COLUMN bank_name TEXT")
    if 'bank_account' not in columns: cursor.execute("ALTER TABLE all_users ADD COLUMN bank_account TEXT")
        
    cursor.execute("PRAGMA table_info(trips)")
    trip_columns = [row[1] for row in cursor.fetchall()]
    if 'trip_date' not in trip_columns: cursor.execute("ALTER TABLE trips ADD COLUMN trip_date TEXT")

    cursor.execute("PRAGMA table_info(notifications)")
    notif_columns = [row[1] for row in cursor.fetchall()]
    if 'is_auto' not in notif_columns: cursor.execute("ALTER TABLE notifications ADD COLUMN is_auto INTEGER DEFAULT 0")
    if 'is_read' not in notif_columns: cursor.execute("ALTER TABLE notifications ADD COLUMN is_read INTEGER DEFAULT 0")
    if 'timestamp' not in notif_columns: cursor.execute("ALTER TABLE notifications ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP")
        
    conn.commit()
    conn.close()

def compress_image(uploaded_file):
    if uploaded_file is None: return None
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    img.thumbnail((600, 600)) # ปรับขนาดให้เล็กลงพอดีหน้าจอ ประหยัดพื้นที่ฐานข้อมูล
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

if "current_online_user" not in st.session_state:
    st.session_state["current_online_user"] = None

if st.session_state["current_online_user"]:
    update_online_heartbeat(st.session_state["current_online_user"])

# --- 4. เมนูข้าง SIDEBAR (Compact Mode) ---
st.sidebar.markdown("### 🔐 บัญชีผู้ใช้งาน")

conn = get_db_connection()
existing_all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
conn.close()

if st.session_state["current_online_user"] is None:
    st.sidebar.warning("⚠️ ยังไม่ได้ล็อกอินโปรไฟล์")
    login_mode = st.sidebar.radio("ทางเลือกบัญชี:", ["เลือกโปรไฟล์เดิม", "สร้างใหม่"], horizontal=True)
    
    if login_mode == "เลือกโปรไฟล์เดิม":
        if existing_all_users:
            c1, c2 = st.sidebar.columns([2, 1])
            user_select = c1.selectbox("เลือกชื่อของคุณ:", existing_all_users, label_visibility="collapsed")
            if c2.button("เข้าสู่ระบบ", use_container_width=True):
                st.session_state["current_online_user"] = user_select
                update_online_heartbeat(user_select)
                st.toast(f"👋 ยินดีต้อนรับ, {user_select}!")
                time.sleep(0.5)
                st.rerun()
        else:
            st.sidebar.caption("ยังไม่มีข้อมูลสมาชิก กรุณาสร้างใหม่")
    else:
        c1, c2 = st.sidebar.columns([2, 1])
        new_online_name = c1.text_input("ชื่อของคุณ:", placeholder="ระบุชื่อเล่น", label_visibility="collapsed").strip()
        if c2.button("สร้าง", use_container_width=True):
            if new_online_name:
                try:
                    conn = get_db_connection()
                    conn.execute("INSERT INTO all_users (name) VALUES (?)", (new_online_name,))
                    conn.commit(); conn.close()
                    st.session_state["current_online_user"] = new_online_name
                    update_online_heartbeat(new_online_name)
                    st.toast(f"🎉 สร้างโปรไฟล์ '{new_online_name}' สำเร็จ!")
                    time.sleep(0.5)
                    st.rerun()
                except: st.sidebar.error("❌ ชื่อนี้มีในระบบแล้ว")
else:
    st.sidebar.markdown(f"🟢 ผู้ใช้งาน: **{st.session_state['current_online_user']}**")
    
    conn = get_db_connection()
    my_data = conn.execute("SELECT * FROM all_users WHERE name = ?", (st.session_state["current_online_user"],)).fetchone()
    conn.close()
    
    c1, c2 = st.sidebar.columns(2)
    with c1.expander("⚙️ ข้อมูลส่วนตัว"):
        edit_pp = st.text_input("เลขพร้อมเพย์:", value=my_data['promptpay'] if my_data['promptpay'] else "")
        db_bank = my_data['bank_name'] if my_data['bank_name'] else "-- เลือกธนาคาร --"
        bank_idx = BANK_LIST.index(db_bank) if db_bank in BANK_LIST else 0
        edit_bank_name = st.selectbox("เลือกธนาคาร:", BANK_LIST, index=bank_idx)
        edit_bank_acc = st.text_input("เลขบัญชีธนาคาร:", value=my_data['bank_account'] if my_data['bank_account'] else "")
        
        if st.button("💾 บันทึกประวัติ", use_container_width=True):
            final_bank = edit_bank_name if edit_bank_name != "-- เลือกธนาคาร --" else ""
            conn = get_db_connection()
            conn.execute("UPDATE all_users SET promptpay = ?, bank_name = ?, bank_account = ? WHERE name = ?", 
                         (edit_pp, final_bank, edit_bank_acc, st.session_state["current_online_user"]))
            conn.commit(); conn.close()
            st.toast("💾 บันทึกสำเร็จ!")
            time.sleep(0.5)
            st.rerun()
            
    if c2.button("🚪 ออกจากระบบ", type="secondary", use_container_width=True):
        conn = get_db_connection()
        conn.execute("DELETE FROM online_status WHERE name = ?", (st.session_state["current_online_user"],))
        conn.commit(); conn.close()
        st.session_state["current_online_user"] = None
        st.rerun()

# 🌐 รายชื่อสมาชิกแบบประหยัดบรรทัด (Inline Tags)
st.sidebar.markdown("---")
online_users = get_currently_online_users()
if online_users:
    online_badges = " ".join([f"🟢 `{u}`" if u != st.session_state["current_online_user"] else f"🌟 `{u}(คุณ)`" for u in online_users])
    st.sidebar.markdown(f"<span style='font-size:12px;'>🌐 <b>ออนไลน์ขณะนี้:</b> {online_badges}</span>", unsafe_allow_html=True)
else:
    st.sidebar.caption("ไม่มีผู้ใช้งานอื่นออนไลน์")

# ====== ส่วนสร้าง Event ใหม่พร้อมระบุวันที่ ======
st.sidebar.markdown("---")
st.sidebar.markdown("### ➕ สร้าง Event ใหม่")
new_trip_name = st.sidebar.text_input("ชื่อ Event:", key="add_trip_field", placeholder="เช่น ทริปหัวหิน").strip()
new_trip_date = st.sidebar.date_input("วันที่จัด Event:", value=datetime.today())

if st.sidebar.button("สร้าง Event ใหม่", use_container_width=True):
    if new_trip_name:
        try:
            conn = get_db_connection()
            date_str = new_trip_date.strftime("%Y-%m-%d")
            conn.execute("INSERT INTO trips (name, status, trip_date) VALUES (?, 0, ?)", (new_trip_name, date_str))
            conn.commit(); conn.close()
            st.toast(f"✈️ สร้าง Event '{new_trip_name}' สำเร็จ!")
            time.sleep(0.5)
            st.rerun()
        except: st.sidebar.error("❌ ชื่อ Event ซ้ำ")

# --- ส่วนจัดการระบบถังขยะย่อส่วน ---
conn = get_db_connection()
with st.sidebar.expander("🗑️ ถังขยะ"):
    deleted_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
    if not deleted_trips:
        st.caption("ไม่มีรายการในถังขยะ")
    else:
        for dt in deleted_trips:
            c1, c2 = st.columns([1.8, 1.2])
            has_dt = dt['trip_date'] and str(dt['trip_date']).strip() and not pd.isna(dt['trip_date'])
            c1.caption(f"• {dt['name']}" + (f" ({dt['trip_date']})" if has_dt else ""))
            sub_c1, sub_c2 = c2.columns(2)
            if sub_c1.button("กู้", key=f"res_{dt['id']}", help="กู้คืน"):
                conn.execute("UPDATE trips SET status = 0 WHERE id = ?", (dt['id'],))
                conn.commit(); st.rerun()
            if sub_c2.button("ลบ", key=f"pdel_{dt['id']}", help="ลบถาวร"):
                conn.execute("DELETE FROM settlements WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM expenses WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM members WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM trips WHERE id = ?", (dt['id'],))
                conn.commit(); st.rerun()

active_trips_df = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)

if not active_trips_df.empty:
    active_trips_df['display_name'] = active_trips_df.apply(
        lambda r: f"{r['name']} 📅 ({r['trip_date']})" if r['trip_date'] and str(r['trip_date']).strip() and not pd.isna(r['trip_date']) else r['name'], axis=1
    )
    active_trip_display_list = active_trips_df["display_name"].tolist()
else:
    active_trip_display_list = []

if not active_trip_display_list:
    st.title("✈️ Trip Expense Splitter Pro")
    st.info("กรุณาสร้าง Event ใหม่ หรือกู้คืนจากถังขยะที่เมนูซ้ายมือเพื่อเริ่มต้นระบบ")
    st.stop()

st.sidebar.markdown("---")
selected_display_trip = st.sidebar.selectbox("🗺️ เลือก Event ปัจจุบัน:", active_trip_display_list)

matched_trip = active_trips_df[active_trips_df['display_name'] == selected_display_trip].iloc[0]
current_trip = matched_trip['name']
trip_id = int(matched_trip['id'])
current_trip_date = matched_trip['trip_date']

with st.sidebar.expander("✏️ แก้ไข Event ปัจจุบัน"):
    rename_input = st.text_input("เปลี่ยนชื่อ Event เป็น:", value=current_trip).strip()
    try: default_date = datetime.strptime(str(current_trip_date), "%Y-%m-%d") if current_trip_date else datetime.today()
    except: default_date = datetime.today()
    re_date_input = st.date_input("แก้ไขวันที่:", value=default_date)
    
    c_ev1, c_ev2 = st.columns(2)
    if c_ev1.button("💾 ยืนยัน", use_container_width=True):
        if rename_input:
            try:
                conn_rename = get_db_connection()
                conn_rename.execute("UPDATE trips SET name = ?, trip_date = ? WHERE id = ?", (rename_input, re_date_input.strftime("%Y-%m-%d"), trip_id))
                conn_rename.commit(); conn_rename.close()
                st.toast("✏️ อัปเดตข้อมูลสำเร็จ!")
                time.sleep(0.5)
                st.rerun()
            except: st.error("❌ ชื่อ Event ซ้ำ")
    if c_ev2.button("🗑️ ลบทริป", type="secondary", use_container_width=True):
        conn.execute("UPDATE trips SET status = 1 WHERE id = ?", (trip_id,))
        conn.commit(); st.toast("🗑️ ย้ายลงถังขยะแล้ว"); time.sleep(0.5); st.rerun()

st.sidebar.markdown("### 👥 สมาชิกภายใน Event")
all_users_list = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_users = [u for u in all_users_list if u not in existing_members]

if existing_members:
    conn_member_notif = get_db_connection()
    for member in existing_members:
        m_col1, m_col2 = st.sidebar.columns([5, 1])
        is_me = " (คุณ)" if member == st.session_state["current_online_user"] else ""
        mem_notif_row = conn_member_notif.execute("SELECT COUNT(*) as cnt FROM notifications WHERE trip_id = ? AND to_user = ? AND is_read = 0", (trip_id, member)).fetchone()
        mem_notif_count = mem_notif_row["cnt"] if mem_notif_row else 0
        has_msg_badge = f" ✉️({mem_notif_count})" if mem_notif_count > 0 else ""
        is_online_dot = "🟢 " if member in online_users else "⚪ "
        
        m_col1.markdown(f"<span style='font-size:13px;'>{is_online_dot}{member}{is_me}{has_msg_badge}</span>", unsafe_allow_html=True)
        if m_col2.button("✖", key=f"remove_mem_{member}", help=f"ถอดออก"):
            conn_member_notif.execute("DELETE FROM members WHERE trip_id = ? AND name = ?", (trip_id, member))
            conn_member_notif.commit(); st.toast(f"ถอด {member} ออกแล้ว"); time.sleep(0.5); st.rerun()
    conn_member_notif.close()

c_inv1, c_inv2 = st.sidebar.columns([2, 1])
selected_u = c_inv1.selectbox("ชวนเพื่อนร่วมบิล:", ["-- ชวนเพื่อน --"] + available_users, label_visibility="collapsed")
if c_inv2.button("ดึงเข้า", use_container_width=True) and selected_u != "-- ชวนเพื่อน --":
    conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
    conn.commit(); st.rerun()
conn.close()

# 🔔 =================================================================
# ระบบ "ศูนย์แชทส่วนตัวและการแจ้งเตือนอัตโนมัติย่อส่วนพิเศษ" 💬
# =================================================================
st.sidebar.markdown("---")
notif_count = 0
if st.session_state["current_online_user"]:
    conn_count = get_db_connection()
    count_row = conn_count.execute("SELECT COUNT(*) as cnt FROM notifications WHERE trip_id = ? AND to_user = ? AND is_read = 0", (trip_id, st.session_state["current_online_user"])).fetchone()
    notif_count = count_row["cnt"] if count_row else 0
    conn_count.close()

notif_label = f"🔔 ศูนย์แชทส่วนตัว (🔴 {notif_count})" if notif_count > 0 else "🔔 ศูนย์แชทส่วนตัว"

if st.session_state["current_online_user"]:
    my_name = st.session_state["current_online_user"]
    
    conn_notif = get_db_connection()
    all_chat_rows = conn_notif.execute(
        "SELECT * FROM notifications WHERE trip_id = ? AND (to_user = ? OR from_user = ? OR (to_user = ? AND is_auto = 1)) ORDER BY timestamp ASC, id ASC", 
        (trip_id, my_name, my_name, my_name)
    ).fetchall()
    conn_notif.close()
    
    chat_groups, unread_status = {}, {}
    for n in all_chat_rows:
        partner = "ระบบสรุปยอด" if (n['is_auto'] == 1 or n['from_user'] == "ระบบสรุปยอด") else (n['from_user'] if n['to_user'] == my_name else n['to_user'])
        if partner not in chat_groups:
            chat_groups[partner], unread_status[partner] = [], 0
        chat_groups[partner].append(n)
        if n['to_user'] == my_name and n['is_read'] == 0: unread_status[partner] += 1

    with st.sidebar.expander(f"📥 ข้อความแจ้งเตือน ({len(chat_groups)})", expanded=True):
        if not chat_groups:
            st.caption("ไม่มีประวัติข้อความแจ้งเตือน")
        else:
            sender_keys = list(chat_groups.keys())
            tab_labels = [f"🤖 ระบบ" if p == "ระบบสรุปยอด" else f"👤 {p}" + (f"(🔴 {unread_status[p]})" if unread_status[p] > 0 else "") for p in sender_keys]
            chat_tabs = st.tabs(tab_labels)
            
            for idx, partner in enumerate(sender_keys):
                with chat_tabs[idx]:
                    if unread_status[partner] > 0:
                        conn_reset = get_db_connection()
                        if partner == "ระบบสรุปยอด":
                            conn_reset.execute("UPDATE notifications SET is_read = 1 WHERE trip_id = ? AND to_user = ? AND is_auto = 1 AND is_read = 0", (trip_id, my_name))
                        else:
                            conn_reset.execute("UPDATE notifications SET is_read = 1 WHERE trip_id = ? AND to_user = ? AND from_user = ? AND is_read = 0", (trip_id, my_name, partner))
                        conn_reset.commit(); conn_reset.close(); st.rerun()
                    
                    # กล่อง Chat Bubble แบบ Mini กะทัดรัด
                    st.markdown("<div style='max-height: 150px; overflow-y: auto; padding: 2px;'>", unsafe_allow_html=True)
                    for notif in chat_groups[partner]:
                        time_str = notif['timestamp'][11:16] if notif['timestamp'] else ""
                        is_my_own = (notif['from_user'] == my_name and notif['is_auto'] == 0)
                        is_system_msg = (notif['from_user'] == "ระบบสรุปยอด" or notif['is_auto'] == 1)
                        
                        if is_my_own:
                            bg, align, radius = "#85E374", "flex-end", "12px 12px 2px 12px"
                        elif is_system_msg:
                            bg, align, radius = "#D6E4FF", "flex-start", "2px 12px 12px 12px; border-left: 3px solid #4A90E2;"
                        else:
                            bg, align, radius = "#EAEAEA", "flex-start", "2px 12px 12px 12px"
                            
                        st.markdown(f'''
                        <div style="display: flex; flex-direction: column; align-items: {align}; margin-bottom: 4px;">
                            <div style="background-color: {bg}; color: #000; padding: 5px 9px; border-radius: {radius}; max-width: 90%; font-size: 11px; line-height: 1.3; box-shadow: 1px 1px 1px rgba(0,0,0,0.05);">
                                {notif['message']} <span style="font-size: 8px; color: #777; margin-left: 4px;">{time_str}</span>
                            </div>
                        </div>
                        ''', unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    c_del1, c_del2 = st.columns([4, 1])
                    if c_del2.button("🗑️", key=f"del_notif_{partner}", help="ล้างประวัติห้องนี้"):
                        conn_d = get_db_connection()
                        conn_d.execute("DELETE FROM notifications WHERE trip_id = ? AND (to_user = ? OR from_user = ?)", (trip_id, partner, partner))
                        conn_d.commit(); conn_d.close(); st.rerun()
                        
                    if partner != "ระบบสรุปยอด":
                        with st.form(key=f"reply_form_{partner}", clear_on_submit=True):
                            c_tx, c_btn = st.columns([3, 1])
                            reply_text = c_tx.text_input("คุยย่อย:", placeholder="พิมพ์ตอบ...", key=f"in_{partner}", label_visibility="collapsed")
                            if c_btn.form_submit_button("↩️") and reply_text.strip():
                                conn_reply = get_db_connection()
                                conn_reply.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, ?, ?, 0, 0, datetime('now', 'localtime'))",
                                                 (trip_id, partner, my_name, reply_text.strip()))
                                conn_reply.commit(); conn_reply.close(); st.rerun()

    with st.sidebar.expander("📝 เปิดกล่องคุยกับเพื่อนใหม่"):
        other_members = [m for m in existing_members if m != my_name]
        if other_members:
            send_to = st.selectbox("เลือกเพื่อนในทริป:", other_members, key="notif_send_to")
            with st.form(key="new_chat_form", clear_on_submit=True):
                notif_msg = st.text_input("ข้อความสั้น:", placeholder="ทักทาย...")
                if st.form_submit_button("🚀 ส่งแชท", type="primary", use_container_width=True) and notif_msg.strip():
                    conn_send = get_db_connection()
                    conn_send.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, ?, ?, 0, 0, datetime('now', 'localtime'))",
                                   (trip_id, send_to, my_name, notif_msg.strip()))
                    conn_send.commit(); conn_send.close(); st.rerun()
else:
    st.sidebar.caption("กรุณาเข้าสู่ระบบเพื่อใช้งานระบบแชท")

# ====================================================================
# --- 5. พื้นที่ทำงานหลัก (Main UI Display ขนาดกระทัดรัดครบฟังก์ชัน) ---
# ====================================================================
has_valid_date = current_trip_date and str(current_trip_date).strip() and not pd.isna(current_trip_date)

if st.session_state["current_online_user"] is None:
    st.title("🛄 กรุณาระบุข้อมูลผู้ใช้งานเครื่องนี้ก่อน")
    st.info("กรุณาเลือกโปรไฟล์ของคุณหรือสร้างผู้ใช้ใหม่ที่แถบซ้ายบน เพื่อเริ่มเปิดดูสถิติและลงรายการบิล")
    st.stop()

if not existing_members:
    st.title(f"✈️ Event: {current_trip}")
    if has_valid_date: st.caption(f"📅 วันที่จัดทริป: {current_trip_date}")
    st.warning("⚠️ ยังไม่มีใครอยู่ในกลุ่มนี้เลย ชวนเพื่อนหรือตัวคุณเองที่แถบซ้ายมือก่อนครับ")
    st.stop()

st.markdown(f"### ✈️ ข้อมูล Event: {current_trip} " + (f"<span style='font-size:15px; color:#555;'>(📅 วันที่จัด: {current_trip_date})</span>" if has_valid_date else ""), unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📝 สร้างบิลใหม่", "📊 ประวัติบันทึกบิล", "💰 Сlear บิลสรุปเคลียร์เงิน"])

# --- TAB 1: สร้างบิลใหม่ ---
with tab1:
    with st.form("add_bill", clear_on_submit=True):
        st.markdown("##### ➕ เพิ่มบิลค่าใช้จ่ายประจำกลุ่ม")
        
        f_c1, f_c2 = st.columns([2, 1])
        desc = f_c1.text_input("รายการค่าใช้จ่าย:", placeholder="เช่น ค่าข้าวเที่ยง, ค่าน้ำมันรถ")
        amt = f_c2.number_input("จำนวนเงินรวม (บาท):", min_value=0.0, step=50.0)
        
        my_name = st.session_state["current_online_user"]
        default_idx = existing_members.index(my_name) if my_name in existing_members else 0
        
        f_c3, f_c4 = st.columns([1, 2])
        payer = f_c3.selectbox("คนสำรองจ่ายเงินก่อน:", existing_members, index=default_idx)
        file = f_c4.file_uploader("แนบรูปภาพสลิปเงิน:", type=['jpg','png','jpeg'])
        
        st.markdown("<span style='font-size:12px; font-weight:bold;'>คนร่วมหารในบิลนี้:</span>", unsafe_allow_html=True)
        chk_grid = st.columns(max(len(existing_members), 1))
        split_to = []
        for idx, m in enumerate(existing_members):
            if chk_grid[idx].checkbox(m, value=True, key=f"add_{m}"):
                split_to.append(m)
                
        if st.form_submit_button("💾 บันทึกบิลรายการนี้", type="primary", use_container_width=True):
            if desc and amt > 0 and split_to:
                blob = compress_image(file)
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                               (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit()
                
                share_amt = amt / len(split_to)
                for member in split_to:
                    if member != payer:
                        sys_msg = f"📌 บิลใหม่: '{desc}'\n💰 ยอดรวม {amt:,.2f} บาท\n👤 คนจ่าย: {payer}\n💸 ส่วนของคุณคือ: {share_amt:,.2f} บาท"
                        conn.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, 'ระบบสรุปยอด', ?, 1, 0, datetime('now', 'localtime'))",
                                     (trip_id, member, sys_msg))
                conn.commit(); conn.close()
                st.toast(f"📝 รายการบิล '{desc}' บันทึกสำเร็จ!")
                time.sleep(0.5); st.rerun()
            else:
                st.error("⚠️ กรุณากรอกข้อมูลรายการ จำนวนเงิน และเลือกผู้รับหารให้ครบถ้วน")

# --- TAB 2: ประวัติบันทึกบิล ---
with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    if not expenses: 
        st.info("ยังไม่มีข้อมูลค่าใช้จ่ายในกลุ่มนี้")
    else:
        for row in expenses:
            with st.expander(f"📌 {row['description']} | ยอด {row['amount']:,.2f} บาท (จ่ายโดย: {row['payer_name']})"):
                c_ex1, c_ex2 = st.columns([2, 1])
                c_ex1.caption(f"👥 ผู้หารบิล: {row['split_members']}")
                
                if c_ex1.button("🗑️ ลบบิลนี้ออก", key=f"del_bill_{row['id']}", type="secondary"):
                    conn_d = get_db_connection()
                    conn_d.execute("DELETE FROM expenses WHERE id = ?", (row['id'],))
                    conn_d.commit(); conn_d.close(); st.toast("ลบบิลเรียบร้อย"); time.sleep(0.3); st.rerun()
                    
                if row['image_blob']:
                    c_ex2.image(Image.open(io.BytesIO(row['image_blob'])), width=180)

# --- TAB 3: สรุปเคลียร์เงินสมาชิก ---
with tab3:
    st.markdown("##### 💰 ตารางคำนวณสรุปยอดหักลบกลบหนี้")
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    
    # 🧮 ส่วนคำนวณอัลกอริทึมแยกหนี้
    balances = {m: 0.0 for m in existing_members}
    for row in expenses:
        payer = row['payer_name']
        amt = row['amount']
        split_m = row['split_members'].split(",") if row['split_members'] else []
        if not split_m: continue
        
        share = amt / len(split_m)
        if payer in balances:
            balances[payer] += amt
        for sm in split_m:
            if sm in balances:
                balances[sm] -= share

    debtors = [(m, bal) for m, bal in balances.items() if bal < 0]
    creditors = [(m, bal) for m, bal in balances.items() if bal > 0]
    
    debtors.sort(key=lambda x: x[1])
    creditors.sort(key=lambda x: x[1], reverse=True)

    calculated_settlements = []
    i, j = 0, 0
    while i < len(debtors) and j < len(creditors):
        d_name, d_bal = debtors[i]
        c_name, c_bal = creditors[j]
        
        owes = min(-d_bal, c_bal)
        if owes > 0.01:
            calculated_settlements.append({"debtor": d_name, "creditor": c_name, "amount": owes})
            
        debtors[i] = (d_name, d_bal + owes)
        creditors[j] = (c_name, c_bal - owes)
        
        if abs(debtors[i][1]) < 0.01: i += 1
        if abs(creditors[j][1]) < 0.01: j += 1

    if not calculated_settlements:
        st.success("🎉 ทุกคนลงตัวกันหมดแล้ว! ไม่มีหนี้ค้างเคลียร์ต่อกันใน Event นี้")
    else:
        # แสดงตารางหนี้สิน
        df_set = pd.DataFrame(calculated_settlements)
        df_set.columns = ["👤 คนติดหนี้", "เจ้าหนี้ 👑", "💵 ยอดเงินที่ต้องคืน (บาท)"]
        st.dataframe(df_set.style.format({"💵 ยอดเงินที่ต้องคืน (บาท)": "{:,.2f}"}), use_container_width=True, hide_index=True)
        
        st.markdown("##### ⚡ จัดการส่งประวัติทวงถามและ PromptPay บิล")
        for s in calculated_settlements:
            c_s1, c_s2 = st.columns([3, 1])
            
            # โหลดประวัติพร้อมเพย์ของเจ้าหนี้
            creditor_data = conn.execute("SELECT * FROM all_users WHERE name = ?", (s['creditor'],)).fetchone()
            pp_str = creditor_data['promptpay'] if (creditor_data and creditor_data['promptpay']) else ""
            bank_n = creditor_data['bank_name'] if (creditor_data and creditor_data['bank_name']) else ""
            bank_a = creditor_data['bank_account'] if (creditor_data and creditor_data['bank_account']) else ""
            
            acc_details = f" (พร้อมเพย์: {pp_str})" if pp_str else (f" ({bank_n} {bank_a})" if bank_n else " (ยังไม่ลงข้อมูลธนาคาร)")
            c_s1.markdown(f"• **{s['debtor']}** ต้องจ่ายคืนให้ **{s['creditor']}** ยอด **{s['amount']:,.2f}** บาท {acc_details}")
            
            if c_s2.button("🔔 ทวงออนไลน์", key=f"ping_{s['debtor']}_{s['creditor']}_{s['amount']}"):
                t_msg = f"🚨 ทวงยอดค้าง: คุณมีคลังเคลียร์ที่ต้องจ่ายคืนให้ '{s['creditor']}' จำนวน {s['amount']:,.2f} บาท สำหรับทริปนี้ครับ!"
                conn.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, timestamp) VALUES (?, ?, 'ระบบสรุปยอด', ?, 1, datetime('now', 'localtime'))",
                             (trip_id, s['debtor'], t_msg))
                conn.commit(); st.toast(f"🚀 ยิงใบแจ้งหนี้หา {s['debtor']} แล้ว!")
    conn.close()
