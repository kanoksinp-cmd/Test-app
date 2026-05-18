import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
from datetime import datetime
# 🔄 นำเข้าคอมโพเนนต์สำหรับดึงสัญญาณรีเฟรชอัตโนมัติ
from streamlit_autorefresh import st_autorefresh

# 1. ตั้งค่าหน้าจอและโครงสร้างพื้นฐาน
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# 🔄 สั่งให้ Streamlit รีเฟรชหน้าจออัตโนมัติทุกๆ 1,000 มิลลิวินาที (1 วินาที)
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


# ==========================================
# 🗺️ 3. ส่วนหัวและเมนูด้านบนเว็บไซต์ (TOP MENU BAR)
# ==========================================
st.title("✈️ Trip Expense Splitter Pro")
st.markdown("---")

# ใช้ระบบ Columns ในการแบ่งสัดส่วนเมนูด้านบน
top_col1, top_col2, top_col3 = st.columns([1.5, 1.5, 1.5], gap="medium")

conn = get_db_connection()
existing_all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
conn.close()

# --- COLUMN 1: บัญชีผู้ใช้งานเครื่องนี้ ---
with top_col1:
    st.subheader("🔐 บัญชีผู้ใช้งานเครื่องนี้")
    if st.session_state["current_online_user"] is None:
        st.warning("⚠️ ยังไม่ได้ล็อกอินโปรไฟล์")
        login_mode = st.radio("ทางเลือกบัญชี:", ["เลือกโปรไฟล์ที่มีอยู่", "สร้างโปรไฟล์ใหม่"], horizontal=True, key="top_login_mode")
        
        if login_mode == "เลือกโปรไฟล์ที่มีอยู่":
            if existing_all_users:
                user_select = st.selectbox("เลือกชื่อของคุณ:", existing_all_users, key="top_select_user")
                if st.button("เข้าสู่ระบบ", key="top_btn_login", use_container_width=True):
                    st.session_state["current_online_user"] = user_select
                    update_online_heartbeat(user_select)
                    st.toast(f"👋 ยินดีต้อนรับกลับมา, {user_select}!")
                    time.sleep(1)
                    st.rerun()
            else:
                st.caption("ยังไม่มีข้อมูลสมาชิกในระบบ กรุณาสร้างใหม่")
        else:
            new_online_name = st.text_input("ระบุชื่อเล่น/ชื่อของคุณ:", key="top_new_name").strip()
            if st.button("สร้างและเข้าสู่ระบบ", key="top_btn_create", use_container_width=True):
                if new_online_name:
                    try:
                        conn = get_db_connection()
                        conn.execute("INSERT INTO all_users (name) VALUES (?)", (new_online_name,))
                        conn.commit(); conn.close()
                        st.session_state["current_online_user"] = new_online_name
                        update_online_heartbeat(new_online_name)
                        st.success(f"🎉 สร้างโปรไฟล์ '{new_online_name}' สำเร็จ!")
                        time.sleep(1)
                        st.rerun()
                    except: st.error("❌ ชื่อนี้มีในระบบออนไลน์แล้ว")
                else: st.error("⚠️ กรุณากรอกชื่อ")
    else:
        st.success(f"🟢 ผู้ใช้งาน: **{st.session_state['current_online_user']}**")
        
        conn = get_db_connection()
        my_data = conn.execute("SELECT * FROM all_users WHERE name = ?", (st.session_state["current_online_user"],)).fetchone()
        conn.close()
        
        with st.expander("⚙️ Update ข้อมูลส่วนตัว"):
            edit_pp = st.text_input("เลขพร้อมเพย์:", value=my_data['promptpay'] if my_data['promptpay'] else "", key="top_pp")
            db_bank = my_data['bank_name'] if my_data['bank_name'] else "-- เลือกธนาคาร --"
            bank_idx = BANK_LIST.index(db_bank) if db_bank in BANK_LIST else 0
            edit_bank_name = st.selectbox("เลือกธนาคารบัญชี:", BANK_LIST, index=bank_idx, key="top_bank")
            edit_bank_acc = st.text_input("เลขบัญชีธนาคาร:", value=my_data['bank_account'] if my_data['bank_account'] else "", key="top_acc")
            
            if st.button("💾 บันทึกข้อมูลส่วนตัว", key="top_save_profile", use_container_width=True):
                final_bank = edit_bank_name if edit_bank_name != "-- เลือกธนาคาร --" else ""
                conn = get_db_connection()
                conn.execute("UPDATE all_users SET promptpay = ?, bank_name = ?, bank_account = ? WHERE name = ?", 
                             (edit_pp, final_bank, edit_bank_acc, st.session_state["current_online_user"]))
                conn.commit(); conn.close()
                st.toast("💾 บันทึกโปรไฟล์ส่วนตัวสำเร็จ!")
                time.sleep(1)
                st.rerun()
                
        if st.button("🚪 ออกจากระบบ", type="secondary", key="top_logout", use_container_width=True):
            conn = get_db_connection()
            conn.execute("DELETE FROM online_status WHERE name = ?", (st.session_state["current_online_user"],))
            conn.commit(); conn.close()
            st.session_state["current_online_user"] = None
            st.rerun()

# --- COLUMN 2: การเลือกและจัดการ Event ---
with top_col2:
    st.subheader("🗺️ เลือกหรือสร้าง Event")
    conn = get_db_connection()
    active_trips_df = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)
    
    if not active_trips_df.empty:
        active_trips_df['display_name'] = active_trips_df.apply(
            lambda r: f"{r['name']} 📅 ({r['trip_date']})" if r['trip_date'] and str(r['trip_date']).strip() and not pd.isna(r['trip_date']) else r['name'], axis=1
        )
        active_trip_display_list = active_trips_df["display_name"].tolist()
    else:
        active_trip_display_list = []

    if active_trip_display_list:
        selected_display_trip = st.selectbox("เลือก Event ที่ต้องการดู:", active_trip_display_list, key="top_select_trip")
        matched_trip = active_trips_df[active_trips_df['display_name'] == selected_display_trip].iloc[0]
        current_trip = matched_trip['name']
        trip_id = int(matched_trip['id'])
        current_trip_date = matched_trip['trip_date']
        
        c_edit, c_del = st.columns(2)
        with c_edit:
            with st.expander("✏️ แก้ไข Event"):
                rename_input = st.text_input("เปลี่ยนชื่อเป็น:", value=current_trip, key="top_rename").strip()
                try: default_date = datetime.strptime(str(current_trip_date), "%Y-%m-%d") if current_trip_date else datetime.today()
                except: default_date = datetime.today()
                re_date_input = st.date_input("แก้ไขวันที่:", value=default_date, key="top_redate")
                
                if st.button("💾 ยืนยันเปลี่ยนข้อมูล", key="top_confirm_rename", use_container_width=True):
                    if rename_input:
                        try:
                            conn_rename = get_db_connection()
                            new_date_str = re_date_input.strftime("%Y-%m-%d")
                            conn_rename.execute("UPDATE trips SET name = ?, trip_date = ? WHERE id = ?", (rename_input, new_date_str, trip_id))
                            conn_rename.commit(); conn_rename.close()
                            st.success("✏️ อัปเดตข้อมูลเรียบร้อย!")
                            time.sleep(1)
                            st.rerun()
                        except: st.error("❌ ชื่อ Event นี้ซ้ำ")
                    else: st.error("⚠️ กรุณากรอกชื่อ")
        with c_del:
            if st.button("🗑️ ลบ Event", key="top_del_trip", use_container_width=True):
                conn.execute("UPDATE trips SET status = 1 WHERE id = ?", (trip_id,))
                conn.commit()
                st.toast(f"🗑️ ย้าย '{current_trip}' ลงถังขยะแล้ว")
                time.sleep(1)
                st.rerun()
    else:
        st.info("ยังไม่มี Event ในระบบ")
        current_trip, trip_id, current_trip_date = None, None, None

    # ส่วนเสริม: สร้าง Event ใหม่ & ถังขยะ
    with st.expander("➕ สร้าง Event ใหม่ / 🗑️ ถังขยะ"):
        st.markdown("**➕ สร้าง Event ใหม่**")
        new_trip_name = st.text_input("ชื่อ Event:", key="top_new_trip_name").strip()
        new_trip_date = st.date_input("วันที่จัด Event:", value=datetime.today(), key="top_new_trip_date")
        if st.button("สร้าง Event", key="top_btn_create_trip", use_container_width=True):
            if new_trip_name:
                try:
                    conn_new = get_db_connection()
                    date_str = new_trip_date.strftime("%Y-%m-%d")
                    conn_new.execute("INSERT INTO trips (name, status, trip_date) VALUES (?, 0, ?)", (new_trip_name, date_str))
                    conn_new.commit(); conn_new.close()
                    st.success("✈️ สร้าง Event สำเร็จ!")
                    time.sleep(1)
                    st.rerun()
                except: st.error("❌ ชื่อ Event ซ้ำ")
            else: st.error("⚠️ กรุณากรอกชื่อ Event")
        
        st.markdown("---")
        st.markdown("**🗑️ รายการในถังขยะ**")
        deleted_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
        if not deleted_trips: st.caption("ไม่มีรายการในถังขยะ")
        for dt in deleted_trips:
            dc1, dc2 = st.columns([2, 1])
            dc1.write(dt['name'])
            if dc2.button("กู้คืน", key=f"top_res_{dt['id']}"):
                conn.execute("UPDATE trips SET status = 0 WHERE id = ?", (dt['id'],))
                conn.commit(); time.sleep(0.5); st.rerun()
    conn.close()

# --- COLUMN 3: สมาชิกและสถานะออนไลน์ ---
with top_col3:
    st.subheader("👥 สมาชิกและสถานะออนไลน์")
    online_users = get_currently_online_users()
    
    with st.expander(f"🟢 ผู้ใช้งานที่ออนไลน์ขณะนี้ ({len(online_users)})"):
        if online_users:
            for o_user in online_users:
                me_badge = " *(คุณ)*" if o_user == st.session_state["current_online_user"] else " *(คนอื่น)*"
                st.markdown(f"🟢 **{o_user}** {me_badge}")
        else: st.caption("ไม่มีผู้ใช้งานอื่นออนไลน์")

    if trip_id:
        st.markdown("**สมาชิกภายใน Event ปัจจุบัน:**")
        conn = get_db_connection()
        all_users_list = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
        existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
        available_users = [u for u in all_users_list if u not in existing_members]
        
        # แสดงรายชื่อพร้อมปุ่มเตะออก
        for member in existing_members:
            m_col1, m_col2 = st.columns([3, 1])
            is_me = " (คุณ)" if member == st.session_state["current_online_user"] else ""
            mem_notif_row = conn.execute("SELECT COUNT(*) as cnt FROM notifications WHERE trip_id = ? AND to_user = ? AND is_read = 0", (trip_id, member)).fetchone()
            mem_notif_count = mem_notif_row["cnt"] if mem_notif_row else 0
            has_msg_badge = f" ✉️ ({mem_notif_count})" if mem_notif_count > 0 else ""
            is_online_dot = "🟢 " if member in online_users else "⚪ "
            
            m_col1.caption(f"{is_online_dot}{member}{is_me}{has_msg_badge}")
            if m_col2.button("ออก", key=f"top_rm_{member}"):
                conn.execute("DELETE FROM members WHERE trip_id = ? AND name = ?", (trip_id, member))
                conn.commit(); st.rerun()
                
        selected_u = st.selectbox("ชวนเพื่อนออนไลน์เข้าร่วม:", ["-- เลือกเพื่อน --"] + available_users, key="top_add_member")
        if st.button("ดึงเข้ากลุ่ม", key="top_btn_add_member", use_container_width=True):
            if selected_u != "-- เลือกเพื่อน --":
                conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
                conn.commit(); st.rerun()
        conn.close()

st.markdown("---")

# ==========================================
# 🔔 4. ศูนย์แชทส่วนตัวด้านบนหลัก (ศูนย์ข้อความย้ายมาด้านบนก่อนเข้าตารางงาน)
# ==========================================
if st.session_state["current_online_user"] and trip_id:
    my_name = st.session_state["current_online_user"]
    conn_count = get_db_connection()
    count_row = conn_count.execute("SELECT COUNT(*) as cnt FROM notifications WHERE trip_id = ? AND to_user = ? AND is_read = 0", (trip_id, my_name)).fetchone()
    notif_count = count_row["cnt"] if count_row else 0
    
    chat_title = f"📥 ศูนย์แชทและการแจ้งเตือนส่วนตัว 🔴 ({notif_count})" if notif_count > 0 else "📥 ศูนย์แชทและการแจ้งเตือนส่วนตัว"
    
    with st.expander(chat_title):
        all_chat_rows = conn_count.execute(
            "SELECT * FROM notifications WHERE trip_id = ? AND (to_user = ? OR from_user = ? OR (to_user = ? AND is_auto = 1)) ORDER BY timestamp ASC, id ASC",
            (trip_id, my_name, my_name, my_name)
        ).fetchall()
        
        chat_groups = {}
        unread_status = {}
        for n in all_chat_rows:
            partner = "ระบบสรุปยอด" if (n['is_auto'] == 1 or n['from_user'] == "ระบบสรุปยอด") else (n['from_user'] if n['to_user'] == my_name else n['to_user'])
            if partner not in chat_groups:
                chat_groups[partner], unread_status[partner] = [], 0
            chat_groups[partner].append(n)
            if n['to_user'] == my_name and n['is_read'] == 0: unread_status[partner] += 1
            
        if not chat_groups:
            st.caption("ไม่มีประวัติข้อความการแจ้งเตือน")
        else:
            sender_keys = list(chat_groups.keys())
            tab_labels = [f"🤖 ระบบ (🔴 {unread_status[p]})" if p == "ระบบสรุปยอด" else f"👤 {p} (🔴 {unread_status[p]})" if unread_status[p] > 0 else f"👤 {p}" for p in sender_keys]
            chat_tabs = st.tabs(tab_labels)
            
            for idx, partner in enumerate(sender_keys):
                with chat_tabs[idx]:
                    if unread_status[partner] > 0:
                        conn_res = get_db_connection()
                        if partner == "ระบบสรุปยอด":
                            conn_res.execute("UPDATE notifications SET is_read = 1 WHERE trip_id = ? AND to_user = ? AND is_auto = 1 AND is_read = 0", (trip_id, my_name))
                        else:
                            conn_res.execute("UPDATE notifications SET is_read = 1 WHERE trip_id = ? AND to_user = ? AND from_user = ? AND is_read = 0", (trip_id, my_name, partner))
                        conn_res.commit(); conn_res.close(); st.rerun()
                        
                    for notif in chat_groups[partner]:
                        time_str = notif['timestamp'][11:16] if notif['timestamp'] else ""
                        if notif['from_user'] == my_name and notif['is_auto'] == 0:
                            st.markdown(f'<div style="text-align: right;"><span style="background-color: #85E374; padding: 6px 12px; border-radius: 10px; display: inline-block; margin-bottom:5px;">{notif["message"]} <small style="color:#666;">{time_str}</small></span></div>', unsafe_allow_html=True)
                        elif notif['from_user'] == "ระบบสรุปยอด" or notif['is_auto'] == 1:
                            st.markdown(f'<div style="text-align: left;"><span style="background-color: #D6E4FF; padding: 6px 12px; border-radius: 10px; display: inline-block; margin-bottom:5px; border-left: 4px solid #4A90E2;">🤖 บิลระบบ: {notif["message"]} <small style="color:#666;">{time_str}</small></span></div>', unsafe_allow_html=True)
                        else:
                            st.markdown(f'<div style="text-align: left;"><span style="background-color: #EAEAEA; padding: 6px 12px; border-radius: 10px; display: inline-block; margin-bottom:5px;"><b>{notif["from_user"]}</b>: {notif["message"]} <small style="color:#666;">{time_str}</small></span></div>', unsafe_allow_html=True)
                    
                    if partner != "ระบบสรุปยอด":
                        with st.form(key=f"top_reply_{partner}", clear_on_submit=True):
                            rep_txt = st.text_input("พิมพ์ตอบกลับ:")
                            if st.form_submit_button("↩️ ส่งข้อความ") and rep_txt.strip():
                                conn_rep = get_db_connection()
                                conn_rep.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, ?, ?, 0, 0, datetime('now', 'localtime'))", (trip_id, partner, my_name, rep_txt.strip()))
                                conn_rep.commit(); conn_rep.close(); st.rerun()
    conn_count.close()

# ==========================================
# 🛑 5. ตรวจสอบเงื่อนไขตัวแอปพลิเคชันก่อนรันต่อ
# ==========================================
if st.session_state["current_online_user"] is None:
    st.info("💡 กรุณาระบุหรือเลือกข้อมูลผู้ใช้งานที่ เมนูด้านบน เพื่อเริ่มต้นระบบบันทึกบิล")
    st.stop()

if not active_trip_display_list:
    st.info("💡 กรุณาสร้าง Event ใหม่ ที่บล็อกตรงกลางด้านบนเพื่อเริ่มต้นใช้งาน")
    st.stop()

if not existing_members:
    st.warning(f"⚠️ Event '{current_trip}' ยังไม่มีสมาชิกกรุณาดึงชื่อตัวคุณหรือเพื่อนเข้ากลุ่มที่เมนูด้านบนก่อน")
    st.stop()


# ==========================================
# 📝 6. พื้นที่ทำงานหลัก (MAIN WORKSPACE TABS)
# ==========================================
has_valid_date = current_trip_date and str(current_trip_date).strip() and not pd.isna(current_trip_date)
st.subheader(f"🗺️ กำลังทำงานอยู่ที่ Event: {current_trip} " + (f"📅 ({current_trip_date})" if has_valid_date else ""))

tab1, tab2, tab3 = st.tabs(["📝 สร้างบิลใหม่", "📊 ประวัติบันทึกบิล", "💰 สรุปเคลียร์เงินสมาชิก"])

# --- TAB 1: สร้างบิลใหม่ ---
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
                cursor = conn.cursor()
                cursor.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                               (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit()
                
                share_amt = amt / len(split_to)
                for member in split_to:
                    if member != payer:
                        sys_msg = f"📌 บิลใหม่: '{desc}' | ยอดรวม {amt:,.2f} บาท | ส่วนของคุณคือ: {share_amt:,.2f} บาท"
                        conn.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, 'ระบบสรุปยอด', ?, 1, 0, datetime('now', 'localtime'))", (trip_id, member, sys_msg))
                conn.commit(); conn.close()
                st.success(f"📝 บันทึกรายการบิล '{desc}' เรียบร้อยแล้ว!")
                time.sleep(1); st.rerun()
            else: st.error("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")

# --- TAB 2: ประวัติบันทึกบิล ---
with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    if not expenses: 
        st.info("ยังไม่มีข้อมูลค่าใช้จ่ายในกลุ่มนี้")
    else:
        for row in expenses:
            with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} บาท (โดย {row['payer_name']})"):
                c_img, c_info = st.columns([1, 2])
                with c_img:
                    if row['image_blob']: st.image(row['image_blob'], use_container_width=True)
                    else: st.caption("ไม่มีรูปภาพแนบ")
                with c_info:
                    st.write(f"**ผู้ร่วมหาร:** {row['split_members']}")
                    st.write(f"**ตกคนละ:** {row['amount'] / len(row['split_members'].split(',')):,.2f} บาท")
                    if st.button("🗑️ ลบบิลนี้", key=f"del_exp_{row['id']}"):
                        conn = get_db_connection()
                        conn.execute("DELETE FROM expenses WHERE id = ?", (row['id'],))
                        conn.commit(); conn.close(); st.rerun()

# --- TAB 3: สรุปเคลียร์เงินสมาชิก ---
with tab3:
    st.header("💰 สรุปยอดเคลียร์เงิน")
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
    conn.close()

    if not expenses:
        st.info("ยังไม่มีข้อมูลสำหรับคำนวณ")
    else:
        balances = {m: 0.0 for m in members}
        for exp in expenses:
            payer, amt, split_m = exp['payer_name'], exp['amount'], exp['split_members'].split(",")
            share = amt / len(split_m)
            if payer in balances: balances[payer] += amt
            for m in split_m:
                if m in balances: balances[m] -= share

        st.subheader("📊 ยอดสุทธิรายบุคคล")
        for m, bal in balances.items():
            color = "green" if bal >= 0 else "red"
            st.markdown(f"**{m}**: <span style='color:{color}'>{bal:,.2f} บาท</span>", unsafe_allow_html=True)

        st.subheader("💸 รายการที่ต้องโอนคืน")
        debtors = sorted([[m, bal] for m, bal in balances.items() if bal < -0.01], key=lambda x: x[1])
        creditors = sorted([[m, bal] for m, bal in balances.items() if bal > 0.01], key=lambda x: x[1], reverse=True)

        if not debtors and not creditors:
            st.success("🎉 ทุกคนเคลียร์เงินกันลงตัวแล้ว!")
        else:
            for d in debtors:
                for c in creditors:
                    transfer = min(-d[1], c[1])
                    if transfer > 0:
                        st.info(f"👉 **{d[0]}** ต้องโอนให้ **{c[0]}** จำนวน **{transfer:,.2f} บาท**")
                        conn = get_db_connection()
                        target_data = conn.execute("SELECT * FROM all_users WHERE name = ?", (c[0],)).fetchone()
                        conn.close()
                        if target_data and (target_data['promptpay'] or target_data['bank_account']):
                            with st.expander(f"🏦 ข้อมูลบัญชีสำหรับโอนให้ {c[0]}"):
                                if target_data['promptpay']: st.write(f"📲 พร้อมเพย์: {target_data['promptpay']}")
                                if target_data['bank_name']: st.write(f"🏦 ธนาคาร: {target_data['bank_name']} | 🔢 เลขบัญชี: {target_data['bank_account']}")
                        d[1] += transfer
                        c[1] -= transfer

st.markdown("---")
st.caption("Trip Expense Splitter Pro - Live Top Menu Mode Enabled")
