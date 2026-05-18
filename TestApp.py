import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
from datetime import datetime
# 🔄 สำหรับการรีเฟรชหน้าจออัตโนมัติเพื่อให้แชทและสถานะออนไลน์อัปเดตแบบ Real-time
from streamlit_autorefresh import st_autorefresh

# 1. ตั้งค่าหน้าจอและโครงสร้างพื้นฐาน
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# รีเฟรชหน้าจออัตโนมัติทุกๆ 1 วินาที
st_autorefresh(interval=1000, limit=None, key="trip_app_live_refresh")

DB_FILE = "trip_database.db"

BANK_LIST = [
    "-- เลือกธนาคาร --",
    "กสิกรไทย (KBank)",
    "ไทยพาณิชย์ (SCB)",
    "กรุงไทย (KTB)",
    "กรุงเทพ (BBL)",
    "กรุงศรีอยุธยา (BAY)",
    "ทหารไทยธนชาต (TTB)",
    "ออมสิน (GSB)",
    "ธ.ก.ส.",
    "ยูโอบี (UOB)"
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
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            trip_id INTEGER, 
            to_user TEXT, 
            from_user TEXT, 
            message TEXT, 
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_auto INTEGER DEFAULT 0,
            is_read INTEGER DEFAULT 0,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        )
    ''')

    # อัปเดตโครงสร้างตารางหากยังไม่มีคอลัมน์
    cursor.execute("PRAGMA table_info(all_users)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'promptpay' not in columns:
        cursor.execute("ALTER TABLE all_users ADD COLUMN promptpay TEXT")
    if 'bank_name' not in columns:
        cursor.execute("ALTER TABLE all_users ADD COLUMN bank_name TEXT")
    if 'bank_account' not in columns:
        cursor.execute("ALTER TABLE all_users ADD COLUMN bank_account TEXT")
        
    cursor.execute("PRAGMA table_info(trips)")
    trip_columns = [row[1] for row in cursor.fetchall()]
    if 'trip_date' not in trip_columns:
        cursor.execute("ALTER TABLE trips ADD COLUMN trip_date TEXT")

    cursor.execute("PRAGMA table_info(notifications)")
    notif_columns = [row[1] for row in cursor.fetchall()]
    if 'is_auto' not in notif_columns:
        cursor.execute("ALTER TABLE notifications ADD COLUMN is_auto INTEGER DEFAULT 0")
    if 'is_read' not in notif_columns:
        cursor.execute("ALTER TABLE notifications ADD COLUMN is_read INTEGER DEFAULT 0")
    if 'timestamp' not in notif_columns:
        cursor.execute("ALTER TABLE notifications ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP")
        
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

# --- 3. SIDEBAR (เมนูข้าง) ---
st.sidebar.header("🔐 บัญชีผู้ใช้งานเครื่องนี้")

conn = get_db_connection()
existing_all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
conn.close()

if st.session_state["current_online_user"] is None:
    st.sidebar.warning("⚠️ เครื่องนี้ยังไม่ได้ล็อกอินโปรไฟล์")
    login_mode = st.sidebar.radio("ทางเลือกบัญชี:", ["เลือกโปรไฟล์ที่มีอยู่", "สร้างโปรไฟล์ใหม่"], horizontal=True)
    
    if login_mode == "เลือกโปรไฟล์ที่มีอยู่":
        if existing_all_users:
            user_select = st.sidebar.selectbox("เลือกชื่อของคุณ:", existing_all_users)
            if st.sidebar.button("เข้าสู่ระบบ"):
                st.session_state["current_online_user"] = user_select
                update_online_heartbeat(user_select)
                st.toast(f"👋 ยินดีต้อนรับกลับมา, {user_select}!")
                time.sleep(1)
                st.rerun()
        else:
            st.sidebar.caption("ยังไม่มีข้อมูลสมาชิกในระบบ กรุณาสร้างใหม่")
    else:
        new_online_name = st.sidebar.text_input("ระบุชื่อเล่น/ชื่อของคุณ:").strip()
        if st.sidebar.button("สร้างและเข้าสู่ระบบ"):
            if new_online_name:
                try:
                    conn = get_db_connection()
                    conn.execute("INSERT INTO all_users (name) VALUES (?)", (new_online_name,))
                    conn.commit(); conn.close()
                    st.session_state["current_online_user"] = new_online_name
                    update_online_heartbeat(new_online_name)
                    st.sidebar.success(f"🎉 สร้างโปรไฟล์ '{new_online_name}' สำเร็จ!")
                    time.sleep(1)
                    st.rerun()
                except: st.sidebar.error("❌ ชื่อนี้มีในระบบออนไลน์แล้ว")
            else:
                st.sidebar.error("⚠️ กรุณากรอกชื่อ")
else:
    st.sidebar.success(f"🟢 ผู้ใช้งานเครื่องนี้: **{st.session_state['current_online_user']}**")
    
    conn = get_db_connection()
    my_data = conn.execute("SELECT * FROM all_users WHERE name = ?", (st.session_state["current_online_user"],)).fetchone()
    conn.close()
    
    with st.sidebar.expander("⚙️ Update ข้อมูลส่วนตัว"):
        edit_pp = st.text_input("เลขพร้อมเพย์:", value=my_data['promptpay'] if my_data['promptpay'] else "")
        db_bank = my_data['bank_name'] if my_data['bank_name'] else "-- เลือกธนาคาร --"
        bank_idx = BANK_LIST.index(db_bank) if db_bank in BANK_LIST else 0
        edit_bank_name = st.selectbox("เลือกธนาคารบัญชี:", BANK_LIST, index=bank_idx)
        edit_bank_acc = st.text_input("เลขบัญชีธนาคาร:", value=my_data['bank_account'] if my_data['bank_account'] else "")
        
        if st.button("💾 บันทึกข้อมูลส่วนตัว"):
            final_bank = edit_bank_name if edit_bank_name != "-- เลือกธนาคาร --" else ""
            conn = get_db_connection()
            conn.execute("UPDATE all_users SET promptpay = ?, bank_name = ?, bank_account = ? WHERE name = ?", 
                         (edit_pp, final_bank, edit_bank_acc, st.session_state["current_online_user"]))
            conn.commit(); conn.close()
            st.toast("💾 บันทึกโปรไฟล์ส่วนตัวของคุณสำเร็จ!")
            time.sleep(1)
            st.rerun()
            
    if st.sidebar.button("🚪 ออกจากระบบ", type="secondary"):
        conn = get_db_connection()
        conn.execute("DELETE FROM online_status WHERE name = ?", (st.session_state["current_online_user"],))
        conn.commit(); conn.close()
        st.session_state["current_online_user"] = None
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🌐 สมาชิกที่ออนไลน์ในขณะนี้")
online_users = get_currently_online_users()

if online_users:
    for o_user in online_users:
        if o_user == st.session_state["current_online_user"]:
            st.sidebar.markdown(f"🌟 **{o_user}** *(คุณ)*")
        else:
            st.sidebar.markdown(f"🟢 **{o_user}** *(คนอื่น)*")
else:
    st.sidebar.caption("ไม่มีผู้ใช้งานอื่นออนไลน์")
st.sidebar.markdown("---")

st.sidebar.subheader("➕ สร้าง Event ใหม่")
new_trip_name = st.sidebar.text_input("ชื่อ Event:").strip()
new_trip_date = st.sidebar.date_input("วันที่จัด Event:", value=datetime.today())

if st.sidebar.button("สร้าง Event ใหม่"):
    if new_trip_name:
        try:
            conn = get_db_connection()
            date_str = new_trip_date.strftime("%Y-%m-%d")
            conn.execute("INSERT INTO trips (name, status, trip_date) VALUES (?, 0, ?)", (new_trip_name, date_str))
            conn.commit(); conn.close()
            st.success(f"✈️ สร้าง Event ใหม่ '{new_trip_name}' สำเร็จ!")
            time.sleep(1)
            st.rerun()
        except: st.sidebar.error("❌ ชื่อ Event ซ้ำ")
    else:
        st.sidebar.error("⚠️ กรุณากรอกชื่อ Event")

conn = get_db_connection()
with st.sidebar.expander("🗑️ ถังขยะ"):
    deleted_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
    if not deleted_trips:
        st.caption("ไม่มีรายการในถังขยะ")
    else:
        for dt in deleted_trips:
            c1, c2 = st.columns([1.5, 1.5])
            has_dt = dt['trip_date'] and str(dt['trip_date']).strip() and not pd.isna(dt['trip_date'])
            display_deleted_name = f"{dt['name']} ({dt['trip_date']})" if has_dt else dt['name']
            c1.write(display_deleted_name)
            sub_c1, sub_c2 = c2.columns(2)
            if sub_c1.button("กู้คืน", key=f"res_{dt['id']}"):
                conn.execute("UPDATE trips SET status = 0 WHERE id = ?", (dt['id'],))
                conn.commit()
                st.toast(f"🔄 กู้คืน Event '{dt['name']}' เรียบร้อย!")
                time.sleep(1)
                st.rerun()
            if sub_c2.button("ลบ", key=f"pdel_{dt['id']}"):
                conn.execute("DELETE FROM settlements WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM expenses WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM members WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM trips WHERE id = ?", (dt['id'],))
                conn.commit()
                st.toast(f"💥 ลบ Event '{dt['name']}' ถาวรแล้ว!")
                time.sleep(1)
                st.rerun()

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
selected_display_trip = st.sidebar.selectbox("🗺️ เลือกEvent:", active_trip_display_list)

matched_trip = active_trips_df[active_trips_df['display_name'] == selected_display_trip].iloc[0]
current_trip = matched_trip['name']
trip_id = int(matched_trip['id'])
current_trip_date = matched_trip['trip_date']

with st.sidebar.expander("✏️ แก้ไขข้อมูล Event ปัจจุบัน"):
    rename_input = st.text_input("เปลี่ยนชื่อ Event เป็น:", value=current_trip).strip()
    if current_trip_date and str(current_trip_date).strip() and not pd.isna(current_trip_date):
        try: default_date = datetime.strptime(str(current_trip_date), "%Y-%m-%d")
        except ValueError: default_date = datetime.today()
    else: default_date = datetime.today()
        
    re_date_input = st.date_input("แก้ไขวันที่จัด Event:", value=default_date)
    if st.button("💾 ยืนยันเปลี่ยนข้อมูล"):
        if rename_input:
            try:
                conn_rename = get_db_connection()
                new_date_str = re_date_input.strftime("%Y-%m-%d")
                conn_rename.execute("UPDATE trips SET name = ?, trip_date = ? WHERE id = ?", (rename_input, new_date_str, trip_id))
                conn_rename.commit(); conn_rename.close()
                st.success(f"✏️ อัปเดตข้อมูล Event เป็น '{rename_input}' เรียบร้อย!")
                time.sleep(1)
                st.rerun()
            except: st.error("❌ ชื่อ Event นี้ซ้ำกับ Event อื่นที่มีอยู่")
        else: st.error("⚠️ กรุณากรอกชื่อ Event")

if st.sidebar.button("🗑️ ลบ Event"):
    conn.execute("UPDATE trips SET status = 1 WHERE id = ?", (trip_id,))
    conn.commit()
    st.toast(f"🗑️ ย้ายEvent '{current_trip}' ลงถังขยะแล้ว")
    time.sleep(1)
    st.rerun()

st.sidebar.subheader(f"👥 สมาชิกภายใน Event")
all_users_list = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_users = [u for u in all_users_list if u not in existing_members]

if existing_members:
    conn_member_notif = get_db_connection()
    for member in existing_members:
        m_col1, m_col2 = st.sidebar.columns([4, 1])
        is_me = f" (คุณ)" if member == st.session_state["current_online_user"] else ""
        mem_notif_row = conn_member_notif.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE trip_id = ? AND to_user = ? AND is_read = 0", (trip_id, member)
        ).fetchone()
        mem_notif_count = mem_notif_row["cnt"] if mem_notif_row else 0
        has_msg_badge = f" ✉️ ({mem_notif_count})" if mem_notif_count > 0 else ""
        is_online_dot = "🟢 " if member in online_users else "⚪ "
        m_col1.caption(f"{is_online_dot}{member}{is_me}{has_msg_badge}")
        
        if m_col2.button("ออก", key=f"remove_mem_{member}"):
            conn_member_notif.execute("DELETE FROM members WHERE trip_id = ? AND name = ?", (trip_id, member))
            conn_member_notif.commit()
            st.toast(f"🗑️ ถอด {member} ออกแล้ว")
            time.sleep(1)
            st.rerun()
    conn_member_notif.close()

selected_u = st.sidebar.selectbox("ชวนเพื่อนออนไลน์เข้าร่วมบิล:", ["-- เลือกเพื่อน --"] + available_users)
if st.sidebar.button("ดึงเข้ากลุ่ม"):
    if selected_u != "-- เลือกเพื่อน --":
        conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
        conn.commit()
        st.toast(f"➕ ดึง {selected_u} เข้ากลุ่มสำเร็จ!")
        time.sleep(1)
        st.rerun()
conn.close()

# --- 4. ระบบศูนย์แชทส่วนตัวและการแจ้งเตือนออโต้ ---
st.sidebar.markdown("---")
notif_count = 0
if st.session_state["current_online_user"]:
    conn_count = get_db_connection()
    count_row = conn_count.execute(
        "SELECT COUNT(*) as cnt FROM notifications WHERE trip_id = ? AND to_user = ? AND is_read = 0", 
        (trip_id, st.session_state["current_online_user"])
    ).fetchone()
    notif_count = count_row["cnt"] if count_row else 0
    conn_count.close()

if notif_count > 0:
    st.sidebar.markdown(f"<h3>🔔 ศูนย์แชทส่วนตัว <span style='color:#FF4B4B; font-size:18px;'>🔴 ({notif_count})</span></h3>", unsafe_allow_html=True)
else:
    st.sidebar.header("🔔 ศูนย์แชทส่วนตัว")

if st.session_state["current_online_user"]:
    my_name = st.session_state["current_online_user"]
    conn_notif = get_db_connection()
    all_chat_rows = conn_notif.execute(
        """SELECT * FROM notifications WHERE trip_id = ? 
           AND (to_user = ? OR from_user = ? OR (to_user = ? AND is_auto = 1)) 
           ORDER BY timestamp ASC, id ASC""", (trip_id, my_name, my_name, my_name)
    ).fetchall()
    conn_notif.close()
    
    chat_groups = {}
    unread_status = {}
    for n in all_chat_rows:
        if n['is_auto'] == 1 or n['from_user'] == "ระบบสรุปยอด": partner = "ระบบสรุปยอด"
        else: partner = n['from_user'] if n['to_user'] == my_name else n['to_user']
            
        if partner not in chat_groups:
            chat_groups[partner] = []
            unread_status[partner] = 0
        chat_groups[partner].append(n)
        if n['to_user'] == my_name and n['is_read'] == 0: unread_status[partner] += 1

    with st.sidebar.expander(f"📥 แชทและการแจ้งเตือน ({len(chat_groups)})", expanded=True):
        if not chat_groups:
            st.caption("ไม่มีประวัติข้อความหรือการแจ้งเตือน")
        else:
            sender_keys = list(chat_groups.keys())
            tab_labels = [f"🤖 ระบบ (🔴 {unread_status[p]})" if p == "ระบบสรุปยอด" and unread_status[p] > 0 else f"🤖 ระบบ" if p == "ระบบสรุปยอด" else f"👤 {p} (🔴 {unread_status[p]})" if unread_status[p] > 0 else f"👤 {p}" for p in sender_keys]
            chat_tabs = st.tabs(tab_labels)
            
            for idx, partner in enumerate(sender_keys):
                with chat_tabs[idx]:
                    if unread_status[partner] > 0:
                        conn_reset = get_db_connection()
                        if partner == "ระบบสรุปยอด":
                            conn_reset.execute("UPDATE notifications SET is_read = 1 WHERE trip_id = ? AND to_user = ? AND is_auto = 1 AND is_read = 0", (trip_id, my_name))
                        else:
                            conn_reset.execute("UPDATE notifications SET is_read = 1 WHERE trip_id = ? AND to_user = ? AND from_user = ? AND is_read = 0", (trip_id, my_name, partner))
                        conn_reset.commit(); conn_reset.close()
                        st.rerun()
                    
                    for notif in chat_groups[partner]:
                        time_str = str(notif['timestamp'])[11:16] if notif['timestamp'] else ""
                        is_my_own_msg = (notif['from_user'] == my_name and notif['is_auto'] == 0)
                        is_system = (notif['from_user'] == "ระบบสรุปยอด" or notif['is_auto'] == 1)
                        
                        if is_my_own_msg:
                            chat_html = f'<div style="display: flex; justify-content: flex-end; margin-bottom: 10px;"><span style="font-size: 10px; color: #AAA; align-self: flex-end; margin-right: 5px;">{time_str}</span><div style="background-color: #85E374; color: #000; padding: 8px 12px; border-radius: 15px 15px 2px 15px; max-width: 220px; word-wrap: break-word; font-size: 13px;">{notif["message"]}</div></div>'
                        elif is_system:
                            chat_html = f'<div style="margin-bottom: 10px;"><span style="font-size: 11px; color: #4A90E2; font-weight: bold;">🤖 ระบบอัตโนมัติ</span><div style="display: flex;"><div style="background-color: #D6E4FF; color: #000; padding: 8px 12px; border-radius: 2px 15px 15px 15px; max-width: 220px; word-wrap: break-word; font-size: 13px; border-left: 4px solid #4A90E2;">{notif["message"].replace("\n", "<br>")}</div><span style="font-size: 10px; color: #AAA; align-self: flex-end; margin-left: 5px;">{time_str}</span></div></div>'
                        else:
                            chat_html = f'<div style="margin-bottom: 10px;"><span style="font-size: 11px; color: #888;">👤 {notif["from_user"]}</span><div style="display: flex;"><div style="background-color: #EAEAEA; color: #000; padding: 8px 12px; border-radius: 2px 15px 15px 15px; max-width: 220px; word-wrap: break-word; font-size: 13px;">{notif["message"]}</div><span style="font-size: 10px; color: #AAA; align-self: flex-end; margin-left: 5px;">{time_str}</span></div></div>'
                        st.markdown(chat_html, unsafe_allow_html=True)
                        
                        if st.button("🗑️ ลบ", key=f"del_notif_{notif['id']}", type="secondary"):
                            conn_del = get_db_connection()
                            conn_del.execute("DELETE FROM notifications WHERE id = ?", (notif['id'],))
                            conn_del.commit(); conn_del.close()
                            st.toast("ลบข้อความเรียบร้อย")
                            time.sleep(0.3)
                            st.rerun()
                        st.markdown("<div style='margin-bottom: 10px; border-bottom: 1px dashed #EEE;'></div>", unsafe_allow_html=True)

                    if partner != "ระบบสรุปยอด":
                        st.markdown("<div style='margin-top: 15px; border-top: 2px solid #EEE;'></div>", unsafe_allow_html=True)
                        with st.form(key=f"reply_form_{partner}", clear_on_submit=True):
                            reply_text = st.text_input("พิมพ์ตอบกลับเพื่อนที่นี่:", placeholder=f"คุยกับ {partner}...")
                            if st.form_submit_button("↩️ ตอบกลับ", use_container_width=True, type="primary"):
                                if reply_text.strip():
                                    conn_reply = get_db_connection()
                                    conn_reply.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, ?, ?, 0, 0, datetime('now', 'localtime'))", (trip_id, partner, my_name, reply_text.strip()))
                                    conn_reply.commit(); conn_reply.close()
                                    st.toast(f"🚀 ส่งคำตอบกลับหา {partner} แล้ว!")
                                    time.sleep(0.3)
                                    st.rerun()

    with st.sidebar.expander("📝 เปิดกล่องคุยกับเพื่อนใหม่"):
        other_members = [m for m in existing_members if m != my_name]
        if not other_members: st.caption("ไม่มีสมาชิกคนอื่นในกลุ่มนี้")
        else:
            send_to = st.selectbox("เลือกเพื่อนในทริป:", other_members, key="notif_send_to")
            with st.form(key="new_chat_form", clear_on_submit=True):
                notif_msg = st.text_area("ข้อความแรก:", placeholder="ทักทายสร้างบิลแชทที่นี่...")
                if st.form_submit_button("🚀 เริ่มส่งแชท", type="primary", use_container_width=True):
                    if notif_msg.strip():
                        conn_send = get_db_connection()
                        conn_send.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, ?, ?, 0, 0, datetime('now', 'localtime'))", (trip_id, send_to, my_name, notif_msg.strip()))
                        conn_send.commit(); conn_send.close()
                        st.toast(f"🚀 ส่งข้อความถึง {send_to} แล้ว!")
                        time.sleep(0.5)
                        st.rerun()
else:
    st.sidebar.caption("กรุณาเข้าสู่ระบบเพื่อใช้งานระบบแชท")

# --- 5. พื้นที่ทำงานหลัก (Main UI Display) ---
if st.session_state["current_online_user"] is None:
    st.title("🛄 กรุณาระบุข้อมูลผู้ใช้งานเครื่องนี้ก่อน")
    st.info("กรุณาเลือกโปรไฟล์ของคุณหรือสร้างผู้ใช้ใหม่ที่แถบซ้ายบนเพื่อเริ่มต้นระบบ")
    st.stop()

if not existing_members:
    st.title(f"✈️ Event: {current_trip}")
    st.warning("⚠️ ยังไม่มีใครอยู่ในกลุ่มนี้เลย ชวนเพื่อนหรือตัวคุณเองที่แถบซ้ายมือก่อนครับ")
    st.stop()

st.title(f"✈️ ข้อมูล Event: {current_trip}")
has_valid_date = current_trip_date and str(current_trip_date).strip() and not pd.isna(current_trip_date)
if has_valid_date:
    st.subheader(f"📅 วันที่จัด: {current_trip_date}")

tab1, tab2, tab3 = st.tabs(["📝 สร้างบิลใหม่", "📊 ประวัติบันทึกบิล", "💰 สรุปเคลียร์เงินสมาชิก"])

# ==================== TAB 1: สร้างบิลใหม่ ====================
with tab1:
    with st.form("add_bill", clear_on_submit=True):
        st.header("➕ เพิ่มบิลค่าใช้จ่าย")
        desc = st.text_input("รายการ:")
        amt = st.number_input("จำนวนเงิน:", min_value=0.0)
        
        my_name = st.session_state["current_online_user"]
        default_idx = existing_members.index(my_name) if my_name in existing_members else 0
        payer = st.selectbox("คนสำรองจ่ายเงินก่อน:", existing_members, index=default_idx)
        
        st.write("คนร่วมหารในบิลนี้:")
        split_to = [m for m in existing_members if st.checkbox(m, value=True, key=f"add_{m}")]
        file = st.file_uploader("แนบรูปภาพสลิปเงิน:", type=['jpg','png','jpeg'])
        
        if st.form_submit_button("💾 บันทึกบิล", type="primary"):
            if desc and amt > 0 and split_to:
                blob = compress_image(file)
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, desc, amt, payer, ",".join(split_to), blob))
                
                share_amt = amt / len(split_to)
                for member in split_to:
                    if member != payer:
                        sys_msg = f"📌 บิลใหม่เพิ่มเข้ามา: '{desc}'\n💰 ยอดรวม {amt:,.2f} บาท\n👤 คนจ่าย: {payer}\n💸 ส่วนของคุณคือ: {share_amt:,.2f} บาท"
                        conn.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, 'ระบบสรุปยอด', ?, 1, 0, datetime('now', 'localtime'))", (trip_id, member, sys_msg))
                conn.commit(); conn.close()
                st.success(f"📝 บันทึกรายการบิล '{desc}' เรียบร้อยแล้ว!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("⚠️ กรุณากรอกข้อมูลรายการ จำนวนเงิน และเลือกผู้มีส่วนร่วมหารให้ครบถ้วน")

# ==================== TAB 2: ประวัติบันทึกบิล & แก้ไขข้อมูลอัปเดต ====================
with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    
    if not expenses: 
        st.info("ยังไม่มีข้อมูลค่าใช้จ่ายในกลุ่มนี้")
    else:
        for row in expenses:
            with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} บาท (โดย {row['payer_name']})"):
                col_img, col_detail = st.columns([1, 2])
                
                with col_img:
                    if row['image_blob']:
                        st.image(row['image_blob'], caption="สลิปหลักฐาน", use_container_width=True)
                    else:
                        st.caption("ไม่มีรูปภาพประกอบ")
                
                with col_detail:
                    st.markdown("### ✏️ แก้ไขข้อมูลบิลนี้")
                    with st.form(key=f"edit_form_{row['id']}", clear_on_submit=False):
                        edit_desc = st.text_input("แก้ไขรายการ:", value=row['description'])
                        edit_amt = st.number_input("แก้ไขจำนวนเงิน:", min_value=0.0, value=float(row['amount']))
                        
                        old_split_members = row['split_members'].split(',') if row['split_members'] else []
                        st.write("คนร่วมหารในบิลนี้:")
                        edit_split_to = [m for m in existing_members if st.checkbox(m, value=(m in old_split_members), key=f"edit_{row['id']}_{m}")]
                        
                        file_change = st.file_uploader("เปลี่ยนรูปภาพสลิปเงิน (ปล่อยว่างไว้หากใช้รูปเดิม):", type=['jpg','png','jpeg'], key=f"file_edit_{row['id']}")
                        
                        c_btn1, c_btn2 = st.columns(2)
                        submit_update = c_btn1.form_submit_button("💾 บันทึกการอัปเดตบิล", type="primary", use_container_width=True)
                        submit_delete = c_btn2.form_submit_button("🗑️ ลบบิลนี้", type="secondary", use_container_width=True)
                        
                        # 🔄 LOGIC ยิงแชทเตือนซ้ำเมื่อบิลถูกแก้
                        if submit_update:
                            if edit_desc and edit_amt > 0 and edit_split_to:
                                conn = get_db_connection()
                                if file_change is not None:
                                    blob_data = compress_image(file_change)
                                    conn.execute("UPDATE expenses SET description=?, amount=?, split_members=?, image_blob=? WHERE id=?", (edit_desc, edit_amt, ",".join(edit_split_to), blob_data, row['id']))
                                else:
                                    conn.execute("UPDATE expenses SET description=?, amount=?, split_members=? WHERE id=?", (edit_desc, edit_amt, ",".join(edit_split_to), row['id']))
                                
                                share_amt = edit_amt / len(edit_split_to)
                                for member in edit_split_to:
                                    if member != row['payer_name']:
                                        sys_update_msg = (
                                            f"🔄 [อัปเดตบิล] รายการ: '{row['description']}' ถูกแก้ไขแล้ว!\n"
                                            f"📝 ข้อมูลใหม่: '{edit_desc}'\n"
                                            f"💰 ยอดรวมใหม่ {edit_amt:,.2f} บาท (โดย {row['payer_name']})\n"
                                            f"💸 ส่วนของคุณที่ปรับปรุงใหม่คือ: {share_amt:,.2f} บาท"
                                        )
                                        conn.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, 'ระบบสรุปยอด', ?, 1, 0, datetime('now', 'localtime'))", (trip_id, member, sys_update_msg))
                                conn.commit(); conn.close()
                                st.success("🔄 อัปเดตข้อมูลบิลสำเร็จ และส่งแจ้งเตือนเข้าแชทเพื่อนๆ อีกครั้งแล้ว!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
                        
                        if submit_delete:
                            conn = get_db_connection()
                            conn.execute("DELETE FROM expenses WHERE id = ?", (row['id'],))
                            conn.commit(); conn.close()
                            st.toast(f"🗑️ ลบรายการบิล '{row['description']}' เรียบร้อย")
                            time.sleep(0.5)
                            st.rerun()

# ==================== TAB 3: สรุปเคลียร์เงินสมาชิก (แบบเดิม) ====================
with tab3:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
    conn.close()

    if not expenses:
        st.info("ยังไม่มีข้อมูลค่าใช้จ่าย")
    else:
        # คำนวณยอดสุทธิ (Net Balance) ของแต่ละคน
        balance = {m: 0.0 for m in members}
        for row in expenses:
            payer = row['payer_name']
            amount = row['amount']
            split_members = row['split_members'].split(',') if row['split_members'] else []
            if not split_members: continue
            
            share = amount / len(split_members)
            if payer in balance:
                balance[payer] += amount
            for m in split_members:
                if m in balance:
                    balance[m] -= share

        st.header("💰 สรุปยอดค้างชำระ")
        
        # แยกฝั่งคนได้เงินคืน (เจ้าหนี้) และคนต้องจ่าย (ลูกหนี้)
        creditors = [[name, bal] for name, bal in balance.items() if bal > 0.01]
        debtors = [[name, -bal] for name, bal in balance.items() if bal < -0.01]
        
        if not creditors and not debtors:
            st.success("🎉 ทุกคนเคลียร์ยอดกันลงตัวเรียบร้อย")
        else:
            # อัลกอริทึมจับคู่หักลบหนี้ (Greedy Approach)
            results = []
            i = 0
            j = 0
            while i < len(debtors) and j < len(creditors):
                d_name, d_amt = debtors[i]
                c_name, c_amt = creditors[j]
                
                settled_amt = min(d_amt, c_amt)
                results.append({"จาก": d_name, "ส่งให้": c_name, "จำนวน": settled_amt})
                
                debtors[i][1] -= settled_amt
                creditors[j][1] -= settled_amt
                
                if debtors[i][1] < 0.01: i += 1
                if creditors[j][1] < 0.01: j += 1

            # แสดงการจับคู่โอนเงิน
            for res in results:
                col1, col2, col3 = st.columns([2, 1, 2])
                col1.metric("ลูกหนี้", res["จาก"])
                col2.markdown("<h2 style='text-align: center;'>➡️</h2>", unsafe_allow_html=True)
                col3.metric("ส่งให้ (เจ้าหนี้)", res["ส่งให้"], f"{res['จำนวน']:,.2f} ฿")
                
                # ดึงข้อมูลบัญชีธนาคารของเจ้าหนี้มาแสดงผลแบบเดิม
                conn = get_db_connection()
                bank_data = conn.execute("SELECT * FROM all_users WHERE name = ?", (res["ส่งให้"],)).fetchone()
                conn.close()
                
                if bank_data and (bank_data['promptpay'] or bank_data['bank_account']):
                    with st.expander(f"🏦 ดูเลขบัญชีของ {res['ส่งให้']}"):
                        if bank_data['promptpay']: st.write(f"📲 **PromptPay:** {bank_data['promptpay']}")
                        if bank_data['bank_name']: st.write(f"🏛️ **ธนาคาร:** {bank_data['bank_name']}")
                        if bank_data['bank_account']: st.write(f"💳 **เลขบัญชี:** {bank_data['bank_account']}")
                else:
                    st.caption(f"⚠️ {res['ส่งให้']} ยังไม่ได้ลงข้อมูลบัญชีไว้")
                st.divider()
