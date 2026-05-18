import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
import urllib.parse
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
    # สร้างตารางพื้นฐาน
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, status INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS settlements (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    
    # 🌐 ตารางสำหรับระบบออนไลน์ร่วมกัน
    cursor.execute('CREATE TABLE IF NOT EXISTS online_status (name TEXT PRIMARY KEY, last_seen DATETIME)')

    # 🔔 ตารางสำหรับระบบข้อความแจ้งเตือนเรียกเก็บเงิน (ระบุ DEFAULT เป็นเวลาปัจจุบันเวลาบันทึกข้อมูล)
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

    # ตรวจสอบและอัปเดตคอลัมน์ผู้ใช้งาน
    cursor.execute("PRAGMA table_info(all_users)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'promptpay' not in columns:
        cursor.execute("ALTER TABLE all_users ADD COLUMN promptpay TEXT")
    if 'bank_name' not in columns:
        cursor.execute("ALTER TABLE all_users ADD COLUMN bank_name TEXT")
    if 'bank_account' not in columns:
        cursor.execute("ALTER TABLE all_users ADD COLUMN bank_account TEXT")
        
    # ตรวจสอบและอัปเดตคอลัมน์วันที่ทริป
    cursor.execute("PRAGMA table_info(trips)")
    trip_columns = [row[1] for row in cursor.fetchall()]
    if 'trip_date' not in trip_columns:
        cursor.execute("ALTER TABLE trips ADD COLUMN trip_date TEXT")

    # ตรวจสอบความปลอดภัยคอลัมน์ตารางแจ้งเตือนเก่า
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

# ฟังก์ชันอัปเดตสัญญาณชีพ (Heartbeat) บ่งบอกสถานะออนไลน์
def update_online_heartbeat(username):
    if username:
        conn = get_db_connection()
        conn.execute("INSERT INTO online_status (name, last_seen) VALUES (?, datetime('now', 'localtime')) "
                     "ON CONFLICT(name) DO UPDATE SET last_seen = datetime('now', 'localtime')", (username,))
        conn.commit()
        conn.close()

# ฟังก์ชันดึงรายชื่อผู้ใช้ที่กำลังออนไลน์อยู่ ณ ปัจจุบัน (ใครขยับภายใน 15 วินาทีล่าสุด)
def get_currently_online_users():
    conn = get_db_connection()
    rows = conn.execute("SELECT name FROM online_status WHERE last_seen >= datetime('now', 'localtime', '-15 seconds')").fetchall()
    conn.close()
    return [row["name"] for row in rows]

# รันเริ่มระบบฐานข้อมูล
init_db()

# 3. จัดการ Session สมาชิกในคอมพิวเตอร์เครื่องนั้นๆ
if "current_online_user" not in st.session_state:
    st.session_state["current_online_user"] = None

# ส่งสัญญาณสถานะออนไลน์ต่อเนื่องเมื่อหน้าจอรีเฟรชตัวเองทุกๆ 1 วินาที
if st.session_state["current_online_user"]:
    update_online_heartbeat(st.session_state["current_online_user"])

# --- 4. เมนูข้าง SIDEBAR ---
st.sidebar.header("🔐 บัญชีผู้ใช้งานเครื่องนี้")

conn = get_db_connection()
existing_all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
conn.close()

# ตรวจสอบสถานะการล็อกอินโปรไฟล์ของแท็บเบราว์เซอร์นี้
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

# 🌐 ====== ส่วนแสดงรายชื่อสมาชิกที่กำลัง ONLINE ร่วมกันในระบบปัจจุบัน ======
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


# ====== ส่วนสร้าง Event ใหม่พร้อมระบุวันที่ ======
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

# --- ส่วนจัดการระบบถังขยะ ---
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

# หยุดการทำงานชั่วคราวหากยังไม่มี Event ในฐานข้อมูล
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
        try:
            default_date = datetime.strptime(str(current_trip_date), "%Y-%m-%d")
        except ValueError:
            default_date = datetime.today()
    else:
        default_date = datetime.today()
        
    re_date_input = st.date_input("แก้ไขวันที่จัด Event:", value=default_date)
    
    if st.button("💾 ยืนยันเปลี่ยนข้อมูล"):
        if rename_input:
            try:
                conn_rename = get_db_connection()
                new_date_str = re_date_input.strftime("%Y-%m-%d")
                conn_rename.execute("UPDATE trips SET name = ?, trip_date = ? WHERE id = ?", (rename_input, new_date_str, trip_id))
                conn_rename.commit()
                conn_rename.close()
                st.success(f"✏️ อัปเดตข้อมูล Event เป็น '{rename_input}' เรียบร้อย!")
                time.sleep(1)
                st.rerun()
            except:
                st.error("❌ ชื่อ Event นี้ซ้ำกับ Event อื่นที่มีอยู่")
        else:
            st.error("⚠️ กรุณากรอกชื่อ Event")

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
        
        # 📨 เช็คจำนวนข้อความตกค้างของ Event นี้ที่ 'ยังไม่ได้อ่าน (is_read = 0)' ของสมาชิกแต่ละคน
        mem_notif_row = conn_member_notif.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE trip_id = ? AND to_user = ? AND is_read = 0", 
            (trip_id, member)
        ).fetchone()
        mem_notif_count = mem_notif_row["cnt"] if mem_notif_row else 0
        has_msg_badge = f" ✉️ ({mem_notif_count})" if mem_notif_count > 0 else ""
        
        # 🟢 ไฟสถานะเช็คจากกล่องเวลา 15 วินาทีล่าสุด
        is_online_dot = "🟢 " if member in online_users else "⚪ "
        m_col1.caption(f"{is_online_dot}{member}{is_me}{has_msg_badge}")
        
        if m_col2.button("ออก", key=f"remove_mem_{member}", help=f"ถอด {member} ออกจาก Event"):
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


# 🔔 =================================================================
# แก้ไขระบบ "แชทแบบกลุ่มประจำ Event (Unified Event Chat Timeline)" 💬
# =================================================================
st.sidebar.markdown("---")

if st.session_state["current_online_user"]:
    my_name = st.session_state["current_online_user"]
    
    # ดึงยอดแชทที่ยังไม่อ่านของตัวเองเฉพาะใน Event นี้
    conn_count = get_db_connection()
    count_row = conn_count.execute(
        "SELECT COUNT(*) as cnt FROM notifications WHERE trip_id = ? AND to_user = ? AND is_read = 0", 
        (trip_id, my_name)
    ).fetchone()
    notif_count = count_row["cnt"] if count_row else 0
    conn_count.close()

    if notif_count > 0:
        st.sidebar.markdown(f"<h3>💬 แชทกลุ่ม Event <span style='color:#FF4B4B; font-size:18px;'>🔴 ({notif_count})</span></h3>", unsafe_allow_html=True)
    else:
        st.sidebar.header("💬 แชทกลุ่ม Event")

    # อัปเดตสถานะให้อ่านแล้วทั้งหมดเมื่อเปิดดูหน้านี้
    if notif_count > 0:
        conn_read = get_db_connection()
        conn_read.execute("UPDATE notifications SET is_read = 1 WHERE trip_id = ? AND to_user = ?", (trip_id, my_name))
        conn_read.commit()
        conn_read.close()

    # ดึงข้อความทั้งหมดใน Event นี้ (ทั้งแบบคุยทั่วไป และบิลระบบอัตโนมัติที่ส่งหาเรา)
    conn_notif = get_db_connection()
    all_chat_rows = conn_notif.execute(
        """SELECT * FROM notifications 
           WHERE trip_id = ? 
           AND (to_user = 'ALL' OR from_user = ? OR to_user = ?) 
           ORDER BY timestamp ASC, id ASC""", 
        (trip_id, my_name, my_name)
    ).fetchall()
    conn_notif.close()

    with st.sidebar.expander("📥 เปิดกล่องข้อความประจำกลุ่ม", expanded=True):
        if not all_chat_rows:
            st.caption("ยังไม่มีประวัติการพูดคุยหรือการแจ้งเตือนบิลในทริปนี้")
        else:
            # 1. 💬 แสดงลำดับประวัติข้อความ (Timeline)
            for notif in all_chat_rows:
                time_str = ""
                if notif['timestamp']:
                    try:
                        dt_obj = datetime.strptime(notif['timestamp'], "%Y-%m-%d %H:%M:%S")
                        time_str = dt_obj.strftime("%H:%M")
                    except:
                        time_str = str(notif['timestamp'])[11:16]
                
                is_my_own_msg = (notif['from_user'] == my_name and notif['is_auto'] == 0)
                is_system = (notif['from_user'] == "ระบบสรุปยอด" or notif['is_auto'] == 1)
                
                if is_my_own_msg:
                    # 🟢 ข้อความฝั่งขวา (ตัวของเราเอง)
                    chat_html = f'''
                    <div style="display: flex; flex-direction: column; align-items: flex-end; margin-bottom: 10px; width: 100%;">
                        <div style="display: flex; align-items: flex-end;">
                            <span style="font-size: 10px; color: #AAA; margin-right: 6px; padding-bottom: 2px;">{time_str}</span>
                            <div style="background-color: #85E374; color: #000; padding: 8px 12px; border-radius: 15px 15px 2px 15px; max-width: 220px; word-wrap: break-word; font-size: 13px; box-shadow: 1px 1px 2px rgba(0,0,0,0.1);">
                                {notif['message']}
                            </div>
                        </div>
                    </div>
                    '''
                elif is_system:
                    # 🤖 ข้อความบิลอัตโนมัติจากระบบส่วนกลาง
                    chat_html = f'''
                    <div style="display: flex; flex-direction: column; align-items: flex-start; margin-bottom: 10px; width: 100%;">
                        <span style="font-size: 11px; color: #4A90E2; font-weight: bold; margin-left: 5px;">🤖 ระบบอัตโนมัติ</span>
                        <div style="display: flex; align-items: flex-end;">
                            <div style="background-color: #D6E4FF; color: #000; padding: 8px 12px; border-radius: 2px 15px 15px 15px; max-width: 220px; word-wrap: break-word; font-size: 13px; box-shadow: 1px 1px 2px rgba(0,0,0,0.1); border-left: 4px solid #4A90E2;">
                                {notif['message']}
                            </div>
                            <span style="font-size: 10px; color: #AAA; margin-left: 6px; padding-bottom: 2px;">{time_str}</span>
                        </div>
                    </div>
                    '''
                else:
                    # ⚪ ข้อความฝั่งซ้าย (เพื่อนคนอื่นใน Event ส่งมา)
                    chat_html = f'''
                    <div style="display: flex; flex-direction: column; align-items: flex-start; margin-bottom: 10px; width: 100%;">
                        <span style="font-size: 11px; color: #888; margin-left: 5px;">👤 {notif['from_user']}</span>
                        <div style="display: flex; align-items: flex-end;">
                            <div style="background-color: #EAEAEA; color: #000; padding: 8px 12px; border-radius: 2px 15px 15px 15px; max-width: 220px; word-wrap: break-word; font-size: 13px; box-shadow: 1px 1px 2px rgba(0,0,0,0.1);">
                                {notif['message']}
                            </div>
                            <span style="font-size: 10px; color: #AAA; margin-left: 6px; padding-bottom: 2px;">{time_str}</span>
                        </div>
                    </div>
                    '''
                st.markdown(chat_html, unsafe_allow_html=True)
                
                # ปุ่มลบสำหรับข้อความที่ตัวเราเองเป็นผู้ส่งหรือเกี่ยวข้อง
                if is_my_own_msg or is_system:
                    if st.button("🗑️ ลบ", key=f"del_global_notif_{notif['id']}", type="secondary"):
                        conn_del = get_db_connection()
                        conn_del.execute("DELETE FROM notifications WHERE id = ?", (notif['id'],))
                        conn_del.commit()
                        conn_del.close()
                        st.toast("ลบข้อความเรียบร้อย")
                        time.sleep(0.3)
                        st.rerun()
                st.markdown("<div style='margin-bottom: 10px; border-bottom: 1px dashed #EEE;'></div>", unsafe_allow_html=True)

        # 2. 📝 กล่องพิมพ์สำหรับส่งข้อความคุยในกลุ่ม Event (ส่งหาทุกคน)
        st.markdown("<div style='margin-top: 15px; margin-bottom: 5px; border-top: 2px solid #EEE;'></div>", unsafe_allow_html=True)
        with st.form(key=f"global_chat_form_{trip_id}", clear_on_submit=True):
            group_msg = st.text_input("พิมพ์คุยกับทุกคนใน Event:", placeholder="พิมพ์ข้อความที่นี่...")
            if st.form_submit_button("🚀 ส่งข้อความกลุ่ม", use_container_width=True, type="primary"):
                if group_msg.strip():
                    conn_send = get_db_connection()
                    # ส่งหาทุกคนในกลุ่มใช้ flag เป็น 'ALL'
                    conn_send.execute(
                        "INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, 'ALL', ?, ?, 0, 0, datetime('now', 'localtime'))",
                        (trip_id, my_name, group_msg.strip())
                    )
                    conn_send.commit()
                    conn_send.close()
                    st.toast("🚀 ส่งข้อความเข้ากลุ่มแล้ว!")
                    time.sleep(0.3)
                    st.rerun()
                else:
                    st.error("⚠️ กรุณากรอกข้อความก่อนส่ง")
else:
    st.sidebar.caption("กรุณาเข้าสู่ระบบเพื่อใช้งานระบบแชทกลุ่ม")
# ====================================================================


# --- 5. พื้นที่ทำงานหลัก (Main UI Display) ---
has_valid_date = current_trip_date and str(current_trip_date).strip() and not pd.isna(current_trip_date)

if st.session_state["current_online_user"] is None:
    st.title("🛄 กรุณาระบุข้อมูลผู้ใช้งานเครื่องนี้ก่อน")
    st.info("กรุณาเลือกโปรไฟล์ของคุณหรือสร้างผู้ใช้ใหม่ที่แถบซ้ายบน เพื่อเริ่มเปิดดูสถิติและลงรายการบิล")
    st.stop()

if not existing_members:
    st.title(f"✈️ Event: {current_trip}")
    if has_valid_date:
        st.caption(f"📅 วันที่จัดทริป: {current_trip_date}")
    st.warning("⚠️ ยังไม่มีใครอยู่ในกลุ่มนี้เลย ชวนเพื่อนหรือตัวคุณเองที่แถบซ้ายมือก่อนครับ")
    st.stop()

st.title(f"✈️ ข้อมูล Event: {current_trip}")
if has_valid_date:
    st.subheader(f"📅 วันที่จัด: {current_trip_date}")

tab1, tab2, tab3 = st.tabs(["📝 สร้างบิลใหม่", "📊 ประวัติบันทึกบิล", "💰 สรุปเคลียร์เงินสมาชิก"])

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
                
                # บันทึกข้อมูลลงตารางค่าใช้จ่ายหลัก
                cursor = conn.cursor()
                cursor.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit()
                
                # 🤖 แจ้งเตือนบิลระบบอัตโนมัติ: ส่งแจ้งเตือนตรงไปหาผู้ร่วมหารในหน้าแชทกลุ่มหลัก
                share_amt = amt / len(split_to)
                for member in split_to:
                    if member != payer: # ไม่ส่งหารตัวเอง
                        sys_msg = f"📌 บิลใหม่เพิ่มเข้ามา: '{desc}'\n💰 ยอดรวม {amt:,.2f} บาท\n👤 คนจ่าย: {payer}\n💸 ส่วนของ {member} ที่ต้องรับผิดชอบหารคือกำหนด: {share_amt:,.2f} บาท"
                        conn.execute(
                            "INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, 'ระบบสรุปยอด', ?, 1, 0, datetime('now', 'localtime'))",
                            (trip_id, member, sys_msg)
                        )
                conn.commit()
                conn.close()
                
                st.success(f"📝 บันทึกรายการบิล '{desc}' และส่งแจ้งเตือนออโต้เรียบร้อยแล้ว!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("⚠️ กรุณากรอกข้อมูลรายการ Jumlah และเลือกผู้มีส่วนร่วมหารให้ครบถ้วน")

with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    if not expenses: st.info("ยังไม่มีข้อมูลค่าใช้จ่ายในกลุ่มนี้ รายการจะอัปเดตทันทีเมื่อเครื่องอื่นกรอกข้อมูล")
    else:
        for row in expenses:
            with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} บาท (โดย {row['payer_name']})"):
                pass # วางส่วนขยายสลิปบิลเดิมของคุณที่นี่ต่อได้เลยครับ
