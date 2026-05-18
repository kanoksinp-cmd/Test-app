import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# 1. ตั้งค่าหน้าจอและโครงสร้างพื้นฐาน (ปรับขนาด Layout)
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# 🔄 สั่งให้รีเฟรชหน้าจออัตโนมัติทุกๆ 1 วินาที
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
    # อัปเดตคอลัมน์ผู้ใช้งาน
    cursor.execute("PRAGMA table_info(all_users)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'promptpay' not in columns: cursor.execute("ALTER TABLE all_users ADD COLUMN promptpay TEXT")
    if 'bank_name' not in columns: cursor.execute("ALTER TABLE all_users ADD COLUMN bank_name TEXT")
    if 'bank_account' not in columns: cursor.execute("ALTER TABLE all_users ADD COLUMN bank_account TEXT")
    # อัปเดตคอลัมน์วันที่ทริป
    cursor.execute("PRAGMA table_info(trips)")
    trip_columns = [row[1] for row in cursor.fetchall()]
    if 'trip_date' not in trip_columns: cursor.execute("ALTER TABLE trips ADD COLUMN trip_date TEXT")
    # ตรวจสอบคอลัมน์ระบบแจ้งเตือน
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
    img.thumbnail((400, 400)) # 🖼️ ลดขนาดบีบอัดรูปภาพลงครึ่งหนึ่งจากเดิม 800x800
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=60)
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

# --- 4. เมนูข้าง SIDEBAR (ย่อขนาดส่วนควบคุมลงครึ่งหนึ่ง) ---
st.sidebar.markdown("### 🔐 บัญชีโปรไฟล์")

conn = get_db_connection()
existing_all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
conn.close()

if st.session_state["current_online_user"] is None:
    st.sidebar.warning("⚠️ ยังไม่ได้ล็อกอิน")
    login_mode = st.sidebar.radio("เลือก:", ["เลือกบัญชี", "สร้างใหม่"], horizontal=True)
    if login_mode == "เลือกบัญชี":
        if existing_all_users:
            user_select = st.sidebar.selectbox("ชื่อของคุณ:", existing_all_users)
            if st.sidebar.button("เข้าสู่ระบบ", use_container_width=True):
                st.session_state["current_online_user"] = user_select
                update_online_heartbeat(user_select)
                st.toast(f"👋 สวัสดี, {user_select}!")
                time.sleep(0.2)
                st.rerun()
        else:
            st.sidebar.caption("ยังไม่มีรายชื่อสมาชิก กรุณาสร้างใหม่")
    else:
        new_online_name = st.sidebar.text_input("ระบุชื่อของคุณ:").strip()
        if st.sidebar.button("ยืนยันสร้างโปรไฟล์", use_container_width=True):
            if new_online_name:
                try:
                    conn = get_db_connection()
                    conn.execute("INSERT INTO all_users (name) VALUES (?)", (new_online_name,))
                    conn.commit(); conn.close()
                    st.session_state["current_online_user"] = new_online_name
                    update_online_heartbeat(new_online_name)
                    st.sidebar.success(f"🎉 สำเร็จ!")
                    time.sleep(0.2)
                    st.rerun()
                except: st.sidebar.error("❌ ชื่อนี้มีในระบบออนไลน์แล้ว")
            else: st.sidebar.error("⚠️ กรุณากรอกชื่อ")
else:
    st.sidebar.success(f"🟢 ผู้ใช้: **{st.session_state['current_online_user']}**")
    conn = get_db_connection()
    my_data = conn.execute("SELECT * FROM all_users WHERE name = ?", (st.session_state["current_online_user"],)).fetchone()
    conn.close()
    
    with st.sidebar.expander("⚙️ ตั้งค่าโปรไฟล์ส่วนตัว"):
        edit_pp = st.text_input("เลขพร้อมเพย์:", value=my_data['promptpay'] if my_data['promptpay'] else "")
        db_bank = my_data['bank_name'] if my_data['bank_name'] else "-- เลือกธนาคาร --"
        bank_idx = BANK_LIST.index(db_bank) if db_bank in BANK_LIST else 0
        edit_bank_name = st.selectbox("เลือกธนาคาร:", BANK_LIST, index=bank_idx)
        edit_bank_acc = st.text_input("เลขบัญชี:", value=my_data['bank_account'] if my_data['bank_account'] else "")
        if st.button("💾 บันทึก", use_container_width=True):
            final_bank = edit_bank_name if edit_bank_name != "-- เลือกธนาคาร --" else ""
            conn = get_db_connection()
            conn.execute("UPDATE all_users SET promptpay = ?, bank_name = ?, bank_account = ? WHERE name = ?", 
                         (edit_pp, final_bank, edit_bank_acc, st.session_state["current_online_user"]))
            conn.commit(); conn.close()
            st.toast("💾 บันทึกข้อมูลสำเร็จ")
            time.sleep(0.2)
            st.rerun()
            
    if st.sidebar.button("🚪 ออกจากระบบ", type="secondary", use_container_width=True):
        conn = get_db_connection()
        conn.execute("DELETE FROM online_status WHERE name = ?", (st.session_state["current_online_user"],))
        conn.commit(); conn.close()
        st.session_state["current_online_user"] = None
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("##### 🌐 สมาชิกออนไลน์อยู่")
online_users = get_currently_online_users()
if online_users:
    for o_user in online_users:
        status_txt = f"🌟 **{o_user}** *(คุณ)*" if o_user == st.session_state["current_online_user"] else f"🟢 {o_user}"
        st.sidebar.caption(status_txt)
else:
    st.sidebar.caption("ไม่มีคนอื่นออนไลน์")

st.sidebar.markdown("---")
st.sidebar.markdown("##### ➕ สร้าง Event ใหม่")
new_trip_name = st.sidebar.text_input("ชื่อ Event:", key="new_t_name").strip()
new_trip_date = st.sidebar.date_input("วันที่:", value=datetime.today())
if st.sidebar.button("➕ เพิ่ม Event", use_container_width=True):
    if new_trip_name:
        try:
            conn = get_db_connection()
            date_str = new_trip_date.strftime("%Y-%m-%d")
            conn.execute("INSERT INTO trips (name, status, trip_date) VALUES (?, 0, ?)", (new_trip_name, date_str))
            conn.commit(); conn.close()
            st.toast(f"✈️ เพิ่ม Event สำเร็จ")
            time.sleep(0.2)
            st.rerun()
        except: st.sidebar.error("❌ ชื่อซ้ำ")
    else: st.sidebar.error("⚠️ กรุณาระบุชื่อ")

conn = get_db_connection()
with st.sidebar.expander("🗑️ ถังขยะ"):
    deleted_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
    if not deleted_trips: st.caption("ว่างเปล่า")
    else:
        for dt in deleted_trips:
            c1, c2 = st.columns([2, 1.5])
            has_dt = dt['trip_date'] and str(dt['trip_date']).strip() and not pd.isna(dt['trip_date'])
            c1.caption(f"{dt['name']} ({dt['trip_date']})" if has_dt else dt['name'])
            sub_c1, sub_c2 = c2.columns(2)
            if sub_c1.button("กู้", key=f"res_{dt['id']}", help="กู้คืน"):
                conn.execute("UPDATE trips SET status = 0 WHERE id = ?", (dt['id'],))
                conn.commit(); st.toast("🔄 กู้คืนแล้ว"); time.sleep(0.2); st.rerun()
            if sub_c2.button("ลบ", key=f"pdel_{dt['id']}", help="ลบถาวร"):
                conn.execute("DELETE FROM settlements WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM expenses WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM members WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM trips WHERE id = ?", (dt['id'],))
                conn.commit(); st.toast("💥 ลบถาวรแล้ว"); time.sleep(0.2); st.rerun()

active_trips_df = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)
if not active_trips_df.empty:
    active_trips_df['display_name'] = active_trips_df.apply(
        lambda r: f"{r['name']} 📅 ({r['trip_date']})" if r['trip_date'] and str(r['trip_date']).strip() and not pd.isna(r['trip_date']) else r['name'], axis=1
    )
    active_trip_display_list = active_trips_df["display_name"].tolist()
else: active_trip_display_list = []

if not active_trip_display_list:
    st.title("✈️ Trip Expense Splitter Pro")
    st.info("กรุณาสร้างหรือกู้คืน Event ที่เมนูซ้ายมือเพื่อเริ่มต้น")
    st.stop()

st.sidebar.markdown("---")
selected_display_trip = st.sidebar.selectbox("🗺️ เลือก Event:", active_trip_display_list)
matched_trip = active_trips_df[active_trips_df['display_name'] == selected_display_trip].iloc[0]
current_trip = matched_trip['name']
trip_id = int(matched_trip['id'])
current_trip_date = matched_trip['trip_date']

with st.sidebar.expander("✏️ แก้ไขข้อมูล Event"):
    rename_input = st.text_input("เปลี่ยนชื่อเป็น:", value=current_trip).strip()
    try: default_date = datetime.strptime(str(current_trip_date), "%Y-%m-%d")
    except: default_date = datetime.today()
    re_date_input = st.date_input("แก้ไขวันที่:", value=default_date)
    if st.button("💾 ยืนยันแก้ไขข้อมูล", use_container_width=True):
        if rename_input:
            try:
                conn_rename = get_db_connection()
                new_date_str = re_date_input.strftime("%Y-%m-%d")
                conn_rename.execute("UPDATE trips SET name = ?, trip_date = ? WHERE id = ?", (rename_input, new_date_str, trip_id))
                conn_rename.commit(); conn_rename.close()
                st.toast("✏️ อัปเดตข้อมูลแล้ว"); time.sleep(0.2); st.rerun()
            except: st.error("❌ ชื่อ Event นี้ซ้ำ")
        else: st.error("⚠️ กรุณากรอกชื่อ")

if st.sidebar.button("🗑️ ย้าย Event ลงถังขยะ", type="secondary", use_container_width=True):
    conn.execute("UPDATE trips SET status = 1 WHERE id = ?", (trip_id,))
    conn.commit(); st.toast("🗑️ ย้ายลงถังขยะแล้ว"); time.sleep(0.2); st.rerun()

st.sidebar.markdown("##### 👥 สมาชิกในกลุ่ม")
all_users_list = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_users = [u for u in all_users_list if u not in existing_members]

if existing_members:
    conn_member_notif = get_db_connection()
    for member in existing_members:
        m_col1, m_col2 = st.sidebar.columns([4, 1])
        is_me = " (คุณ)" if member == st.session_state["current_online_user"] else ""
        mem_notif_row = conn_member_notif.execute("SELECT COUNT(*) as cnt FROM notifications WHERE trip_id = ? AND to_user = ? AND is_read = 0", (trip_id, member)).fetchone()
        mem_notif_count = mem_notif_row["cnt"] if mem_notif_row else 0
        has_msg_badge = f" ✉️({mem_notif_count})" if mem_notif_count > 0 else ""
        is_online_dot = "🟢 " if member in online_users else "⚪ "
        m_col1.caption(f"{is_online_dot}{member}{is_me}{has_msg_badge}")
        if m_col2.button("ออก", key=f"remove_mem_{member}", help=f"ถอดออก"):
            conn_member_notif.execute("DELETE FROM members WHERE trip_id = ? AND name = ?", (trip_id, member))
            conn_member_notif.commit(); st.toast(f"ถอด {member} แล้ว"); time.sleep(0.2); st.rerun()
    conn_member_notif.close()

selected_u = st.sidebar.selectbox("ชวนเพื่อนเข้าบิล:", ["-- เลือกเพื่อน --"] + available_users)
if st.sidebar.button("ดึงเข้ากลุ่มกลุ่ม", use_container_width=True):
    if selected_u != "-- เลือกเพื่อน --":
        conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
        conn.commit(); st.toast("➕ ดึงเข้าสำเร็จ!"); time.sleep(0.2); st.rerun()
conn.close()

# 🔔 ศูนย์การแชทส่วนตัว (ย่อขนาดฟอนต์สัดส่วนลง 50%)
st.sidebar.markdown("---")
notif_count = 0
if st.session_state["current_online_user"]:
    conn_count = get_db_connection()
    count_row = conn_count.execute("SELECT COUNT(*) as cnt FROM notifications WHERE trip_id = ? AND to_user = ? AND is_read = 0", (trip_id, st.session_state["current_online_user"])).fetchone()
    notif_count = count_row["cnt"] if count_row else 0
    conn_count.close()

st.sidebar.markdown(f"##### 🔔 ศูนย์แชทส่วนตัว " + (f"<span style='color:red;'>🔴 ({notif_count})</span>" if notif_count > 0 else ""), unsafe_allow_html=True)

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
            chat_groups[partner] = []
            unread_status[partner] = 0
        chat_groups[partner].append(n)
        if n['to_user'] == my_name and n['is_read'] == 0: unread_status[partner] += 1

    with st.sidebar.expander(f"📥 แชทและการแจ้งเตือน ({len(chat_groups)})", expanded=True):
        if not chat_groups: st.caption("ไม่มีข้อความแจ้งเตือน")
        else:
            sender_keys = list(chat_groups.keys())
            tab_labels = [f"🤖 ระบบ" + (f"(🔴{unread_status[p]})" if unread_status[p]>0 else "") if p == "ระบบสรุปยอด" else f"👤 {p}" + (f"(🔴{unread_status[p]})" if unread_status[p]>0 else "") for p in sender_keys]
            chat_tabs = st.tabs(tab_labels)
            
            for idx, partner in enumerate(sender_keys):
                with chat_tabs[idx]:
                    if unread_status[partner] > 0:
                        conn_reset_person = get_db_connection()
                        if partner == "ระบบสรุปยอด":
                            conn_reset_person.execute("UPDATE notifications SET is_read = 1 WHERE trip_id = ? AND to_user = ? AND is_auto = 1 AND is_read = 0", (trip_id, my_name))
                        else:
                            conn_reset_person.execute("UPDATE notifications SET is_read = 1 WHERE trip_id = ? AND to_user = ? AND from_user = ? AND is_read = 0", (trip_id, my_name, partner))
                        conn_reset_person.commit(); conn_reset_person.close(); st.rerun()
                    
                    for notif in chat_groups[partner]:
                        try: time_str = datetime.strptime(notif['timestamp'], "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
                        except: time_str = str(notif['timestamp'])[11:16]
                        is_my_own_msg = (notif['from_user'] == my_name and notif['is_auto'] == 0)
                        is_system = (notif['from_user'] == "ระบบสรุปยอด" or notif['is_auto'] == 1)
                        
                        if is_my_own_msg:
                            chat_html = f'<div style="display: flex; flex-direction: column; align-items: flex-end; margin-bottom: 4px;"><div style="background-color: #85E374; color: #000; padding: 4px 8px; border-radius: 10px 10px 2px 10px; max-width: 180px; font-size: 11px;">{notif["message"]} <span style="font-size:8px; color:#666;">{time_str}</span></div></div>'
                        elif is_system:
                            chat_html = f'<div style="display: flex; flex-direction: column; align-items: flex-start; margin-bottom: 4px;"><div style="background-color: #D6E4FF; color: #000; padding: 4px 8px; border-radius: 2px 10px 10px 10px; max-width: 180px; font-size: 11px; border-left: 3px solid #4A90E2;">🤖 {notif["message"]} <span style="font-size:8px; color:#666;">{time_str}</span></div></div>'
                        else:
                            chat_html = f'<div style="display: flex; flex-direction: column; align-items: flex-start; margin-bottom: 4px;"><div style="background-color: #EAEAEA; color: #000; padding: 4px 8px; border-radius: 2px 10px 10px 10px; max-width: 180px; font-size: 11px;">👤 {notif["message"]} <span style="font-size:8px; color:#666;">{time_str}</span></div></div>'
                        st.markdown(chat_html, unsafe_allow_html=True)
                        if st.button("🗑️", key=f"del_notif_{notif['id']}", type="secondary", help="ลบ"):
                            conn_del_notif = get_db_connection()
                            conn_del_notif.execute("DELETE FROM notifications WHERE id = ?", (notif['id'],))
                            conn_del_notif.commit(); conn_del_notif.close(); st.toast("ลบแล้ว"); time.sleep(0.1); st.rerun()
                    
                    if partner != "ระบบสรุปยอด":
                        with st.form(key=f"reply_form_{partner}", clear_on_submit=True):
                            reply_text = st.text_input("พิมพ์ตอบกลับ:", placeholder="คุย...", key=f"reply_in_{partner}")
                            if st.form_submit_button("↩️ ส่ง", use_container_width=True):
                                if reply_text.strip():
                                    conn_reply = get_db_connection()
                                    conn_reply.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, ?, ?, 0, 0, datetime('now', 'localtime'))", (trip_id, partner, my_name, reply_text.strip()))
                                    conn_reply.commit(); conn_reply.close(); st.toast("🚀 ส่งแล้ว"); time.sleep(0.1); st.rerun()

    with st.sidebar.expander("📝 เปิดกล่องคุยกับเพื่อนใหม่"):
        other_members = [m for m in existing_members if m != my_name]
        if not other_members: st.caption("ไม่มีสมาชิกคนอื่น")
        else:
            send_to = st.selectbox("เลือกเพื่อน:", other_members, key="notif_send_to")
            with st.form(key="new_chat_form", clear_on_submit=True):
                notif_msg = st.text_area("ข้อความ:", placeholder="ทักทาย...", key="notif_msg_text")
                if st.form_submit_button("🚀 ส่งข้อความ", use_container_width=True):
                    if notif_msg.strip():
                        conn_send_notif = get_db_connection()
                        conn_send_notif.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, ?, ?, 0, 0, datetime('now', 'localtime'))", (trip_id, send_to, my_name, notif_msg.strip()))
                        conn_send_notif.commit(); conn_send_notif.close(); st.toast("🚀 ส่งแล้ว"); time.sleep(0.1); st.rerun()
else: st.sidebar.caption("กรุณาเข้าสู่ระบบ")

# --- 5. พื้นที่ทำงานหลัก (Main UI Display) ---
has_valid_date = current_trip_date and str(current_trip_date).strip() and not pd.isna(current_trip_date)

if st.session_state["current_online_user"] is None:
    st.title("🛄 กรุณาระบุข้อมูลผู้ใช้งานก่อน")
    st.info("กรุณาเลือกโปรไฟล์ของคุณหรือสร้างผู้ใช้ใหม่ที่แถบซ้ายบน เพื่อเริ่มต้นใช้งาน")
    st.stop()

if not existing_members:
    st.title(f"✈️ Event: {current_trip}")
    if has_valid_date: st.caption(f"📅 วันที่จัดทริป: {current_trip_date}")
    st.warning("⚠️ ยังไม่มีใครอยู่ในกลุ่มนี้เลย ชวนตัวเองหรือเพื่อนๆ ที่แถบซ้ายมือก่อนครับ")
    st.stop()

st.subheader(f"🗺️ Event: {current_trip} " + (f"(📅 วันที่: {current_trip_date})" if has_valid_date else ""))
tab1, tab2, tab3 = st.tabs(["📝 สร้างบิลใหม่", "📊 ประวัติบันทึกบิล", "💰 สรุปเคลียร์เงินสมาชิก"])

with tab1:
    with st.form("add_bill", clear_on_submit=True):
        st.markdown("##### ➕ เพิ่มบิลค่าใช้จ่ายใหม่")
        desc = st.text_input("รายการบิล (เช่น ค่าข้าว, ค่าน้ำมัน):")
        amt = st.number_input("จำนวนเงินรวม (฿):", min_value=0.0)
        my_name = st.session_state["current_online_user"]
        default_idx = existing_members.index(my_name) if my_name in existing_members else 0
        payer = st.selectbox("คนสำรองจ่ายเงินก่อน:", existing_members, index=default_idx)
        st.write("คนร่วมหารในบิลนี้:")
        split_to = [m for m in existing_members if st.checkbox(m, value=True, key=f"add_{m}")]
        file = st.file_uploader("แนบสลิป (ถ้ามี):", type=['jpg','png','jpeg'])
        if st.form_submit_button("💾 บันทึกบิลรายการนี้", type="primary"):
            if desc and amt > 0 and split_to:
                blob = compress_image(file)
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                               (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit()
                # ระบบแจ้งเตือนบิลระบบอัตโนมัติยิงหาผู้ใช้
                share_amt = amt / len(split_to)
                for member in split_to:
                    if member != payer:
                        sys_msg = f"📌 บิลใหม่: '{desc}'\n💰 ยอดรวม {amt:,.2f} ฿ โดย {payer}\n💸 ส่วนของคุณคือ: {share_amt:,.2f} ฿"
                        conn.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, 'ระบบสรุปยอด', ?, 1, 0, datetime('now', 'localtime'))", (trip_id, member, sys_msg))
                conn.commit(); conn.close()
                st.success(f"📝 บันทึกบิล '{desc}' เรียบร้อย!")
                time.sleep(0.2)
                st.rerun()
            else: st.error("⚠️ กรุณากรอกข้อมูลและผู้ร่วมหารให้ครบ")

with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    if not expenses: st.info("ยังไม่มีข้อมูลค่าใช้จ่ายในกลุ่มนี้")
    else:
        for row in expenses:
            with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} ฿ (โดย {row['payer_name']})"):
                # 🛠️ ลดสัดส่วนคอลัมน์การแสดงผลลง 50% ให้กระชับขึ้นสแกนง่าย
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.markdown(f"**💰 ยอด:** {row['amount']:,.2f} ฿")
                    st.markdown(f"**👤 คนจ่าย:** {row['payer_name']}")
                    st.caption(f"👥 คนหาร: {row['split_members']}")
                    m_list = row['split_members'].split(",")
                    share = row['amount'] / len(m_list) if m_list else 0
                    st.caption(f"💸 ตกคนละ {share:,.2f} ฿")
                with c2:
                    if row['image_blob']:
                        with st.container(border=True):
                            st.image(row['image_blob'], caption="สลิปบิล", width=120) # 🖼️ ลดขนาดแสดงผลสลิปเหลือ 120px
                    else: st.caption("ไม่มีสลิป")
                    if st.button("🗑️ ลบ", key=f"del_exp_{row['id']}", type="secondary", icon="🗑️"):
                        conn_del = get_db_connection()
                        conn_del.execute("DELETE FROM expenses WHERE id = ?", (row['id'],))
                        conn_del.commit(); conn_del.close(); st.toast("🗑️ ลบแล้ว"); time.sleep(0.2); st.rerun()

with tab3:
    st.markdown("##### 💰 สรุปยอดเคลียร์เงินและวิธีโอนคืน")
    conn = get_db_connection()
    all_expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    user_profiles = {r['name']: {"promptpay": r['promptpay'], "bank_name": r['bank_name'], "bank_account": r['bank_account']} for r in conn.execute("SELECT * FROM all_users").fetchall()}
    conn.close()
    
    # 🧮 คำนวณหนี้สินสุทธิรายบุคคล
    balances = {m: 0.0 for m in existing_members}
    for row in all_expenses:
        payer = row['payer_name']
        split_m = row['split_members'].split(",")
        if not split_m: continue
        share = row['amount'] / len(split_m)
        if payer in balances: balances[payer] += row['amount']
        for m in split_m:
            if m in balances: balances[m] -= share

    st.write("**📊 สถานะดุลเงินสุทธิรายบุคคล:**")
    b_cols = st.columns(len(existing_members))
    for idx, member in enumerate(existing_members):
        bal = balances[member]
        with b_cols[idx]:
            # 📉 ใช้กระชับ Layout ด้วยสีสันแทนวิตเจ็ตขนาดใหญ่ดั้งเดิม
            if bal > 0: st.markdown(f"**{member}**\n<span style='color:green'>+{bal:,.2f} ฿</span>", unsafe_allow_html=True)
            elif bal < 0: st.markdown(f"**{member}**\n<span style='color:red'>{bal:,.2f} ฿</span>", unsafe_allow_html=True)
            else: st.markdown(f"**{member}**\n<span style='color:gray'>0.00 ฿</span>", unsafe_allow_html=True)

    st.markdown("---")
    st.write("**🤝 รายการชำระเงินแนะนำ (คู่โอนสั้นที่สุด):**")
    debtors = [[m, bal] for m, bal in balances.items() if bal < -0.01]
    creditors = [[m, bal] for m, bal in balances.items() if bal > 0.01]
    debtors.sort(key=lambda x: x[1])
    creditors.sort(key=lambda x: x[1], reverse=True)
    
    suggested_trans = []
    while debtors and creditors:
        d_name, d_bal = debtors[0]
        c_name, c_bal = creditors[0]
        amount_to_pay = min(abs(d_bal), c_bal)
        suggested_trans.append({"from": d_name, "to": c_name, "amount": amount_to_pay})
        debtors[0][1] += amount_to_pay
        creditors[0][1] -= amount_to_pay
        if abs(debtors[0][1]) < 0.01: debtors.pop(0)
        if abs(creditors[0][1]) < 0.01: creditors.pop(0)

    if not suggested_trans: st.success("🎉 ทุกคนเคลียร์ยอดเงินครบเท่ากันหมดแล้วไม่มีหนี้ค้าง!")
    else:
        for idx, trans in enumerate(suggested_trans):
            f_user, t_user, t_amt = trans["from"], trans["to"], trans["amount"]
            with st.container():
                c1, c2 = st.columns([3, 2])
                with c1:
                    st.markdown(f"🔴 **{f_user}** ต้องโอนคืน 🟢 **{t_user}** = **{t_amt:,.2f} ฿**")
                    p_info = user_profiles.get(t_user, {})
                    pp_num = p_info.get("promptpay", "")
                    b_name = p_info.get("bank_name", "")
                    b_acc = p_info.get("bank_account", "")
                    if pp_num or (b_name and b_acc):
                        if pp_num: st.caption(f"💳 พร้อมเพย์: {pp_num}")
                        if b_name and b_acc: st.caption(f"🏦 {b_name} เลขบัญชี: {b_acc}")
                    else: st.caption("⚠️ ปลายทางยังไม่ได้ลงข้อมูลพร้อมเพย์/บัญชีไว้")
                with c2:
                    sub_c1, sub_c2 = st.columns(2)
                    with sub_c1:
                        if pp_num:
                            qr_url = f"https://promptpay.io/{pp_num}/{t_amt:.2f}.png"
                            with st.popover("📱 QR", help="สแกนเพื่อจ่ายเงินคืน"):
                                st.image(qr_url, width=140) # 📱 บีบย่อขนาดคิวอาร์สแกนเหลือ 140px ประหยัดพื้นที่
                    with sub_c2:
                        if st.button("🔔 เตือน", key=f"bz_{idx}", help="ยิงใบเตือนหนี้เข้าห้องแชท"):
                            conn_buzz = get_db_connection()
                            buzz_msg = f"📢 แจ้งเตือนทวงยอด: รบกวนโอนคืนให้ {t_user} เป็นจำนวน {t_amt:,.2f} ฿ สำหรับทริป '{current_trip}' ด้วยน้า 🙏"
                            conn_buzz.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, 'ระบบสรุปยอด', ?, 1, 0, datetime('now', 'localtime'))", (trip_id, f_user, buzz_msg))
                            conn_buzz.commit(); conn_buzz.close(); st.toast("🚀 ส่งใบแจ้งหนี้เรียบร้อย")
            st.markdown("<div style='margin: 2px 0; border-bottom: 1px dashed #EEE;'></div>", unsafe_allow_html=True)
