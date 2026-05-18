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

# 🔄 รีเฟรชหน้าจออัตโนมัติทุกๆ 1 วินาที
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

    # อัปเดตคอลัมน์เวอร์ชันโครงสร้างตาราง
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
    img.thumbnail((600, 600))  # ปรับลดขนาดรูปสลิปลงมาที่สูงสุด 600px เพื่อประหยัดพื้นที่คลาวด์/DB
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=65)
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

# --- 4. เมนูข้าง SIDEBAR (Compact Size ปรับปรุงให้กระชับพรีเมียมขึ้น) ---
st.sidebar.markdown("### 🔐 บัญชีผู้ใช้งาน")

conn = get_db_connection()
existing_all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
conn.close()

if st.session_state["current_online_user"] is None:
    st.sidebar.warning("⚠️ ยังไม่ได้ล็อกอิน")
    login_mode = st.sidebar.radio("ทางเลือกบัญชี:", ["เลือกโปรไฟล์", "สร้างใหม่"], horizontal=True)
    
    if login_mode == "เลือกโปรไฟล์":
        if existing_all_users:
            c1, c2 = st.sidebar.columns([2, 1])
            user_select = c1.selectbox("ชื่อคุณ:", existing_all_users, label_visibility="collapsed")
            if c2.button("เข้าสู่ระบบ", use_container_width=True):
                st.session_state["current_online_user"] = user_select
                update_online_heartbeat(user_select)
                st.toast(f"👋 ยินดีต้อนรับ, {user_select}!")
                time.sleep(0.5)
                st.rerun()
        else:
            st.sidebar.caption("ไม่มีข้อมูลสมาชิก กรุณาสร้างโปรไฟล์ใหม่")
    else:
        c1, c2 = st.sidebar.columns([2, 1])
        new_online_name = c1.text_input("ระบุชื่อเล่น:", placeholder="ชื่อเล่นของคุณ", label_visibility="collapsed").strip()
        if c2.button("สร้างและใช้", use_container_width=True):
            if new_online_name:
                try:
                    conn = get_db_connection()
                    conn.execute("INSERT INTO all_users (name) VALUES (?)", (new_online_name,))
                    conn.commit(); conn.close()
                    st.session_state["current_online_user"] = new_online_name
                    update_online_heartbeat(new_online_name)
                    st.sidebar.success(f"สร้างสำเร็จ!")
                    time.sleep(0.5)
                    st.rerun()
                except: st.sidebar.error("❌ ชื่อซ้ำ")
else:
    st.sidebar.markdown(f"🟢 ผู้ใช้: **{st.session_state['current_online_user']}**")
    
    conn = get_db_connection()
    my_data = conn.execute("SELECT * FROM all_users WHERE name = ?", (st.session_state["current_online_user"],)).fetchone()
    conn.close()
    
    c1, c2 = st.sidebar.columns(2)
    with c1.expander("⚙️ ตั้งค่า"):
        edit_pp = st.text_input("พร้อมเพย์:", value=my_data['promptpay'] if my_data['promptpay'] else "", max_chars=13)
        db_bank = my_data['bank_name'] if my_data['bank_name'] else "-- เลือกธนาคาร --"
        bank_idx = BANK_LIST.index(db_bank) if db_bank in BANK_LIST else 0
        edit_bank_name = st.selectbox("ธนาคาร:", BANK_LIST, index=bank_idx)
        edit_bank_acc = st.text_input("เลขบัญชี:", value=my_data['bank_account'] if my_data['bank_account'] else "")
        
        if st.button("💾 บันทึก", use_container_width=True):
            final_bank = edit_bank_name if edit_bank_name != "-- เลือกธนาคาร --" else ""
            conn = get_db_connection()
            conn.execute("UPDATE all_users SET promptpay = ?, bank_name = ?, bank_account = ? WHERE name = ?", 
                         (edit_pp, final_bank, edit_bank_acc, st.session_state["current_online_user"]))
            conn.commit(); conn.close()
            st.toast("💾 บันทึกสำเร็จ!")
            time.sleep(0.5)
            st.rerun()
            
    if c2.button("🚪 ออก", type="secondary", use_container_width=True):
        conn = get_db_connection()
        conn.execute("DELETE FROM online_status WHERE name = ?", (st.session_state["current_online_user"],))
        conn.commit(); conn.close()
        st.session_state["current_online_user"] = None
        st.rerun()

# 🌐 ออนไลน์สเตตัสแบบเรียงประหยัดบรรทัด
online_users = get_currently_online_users()
if online_users:
    online_dots = " ".join([f"🟢 {u}" if u != st.session_state["current_online_user"] else f"🌟 {u}(คุณ)" for u in online_users])
    st.sidebar.caption(f"🌐 **กำลังออนไลน์:** {online_dots}")

st.sidebar.markdown("---")

# ====== ส่วนเลือกและสร้าง Event แบบ Compact ======
st.sidebar.markdown("### 🗺️ การจัดการ Event")

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
    selected_display_trip = st.sidebar.selectbox("เลือก Event ปัจจุบัน:", active_trip_display_list, label_visibility="collapsed")
    matched_trip = active_trips_df[active_trips_df['display_name'] == selected_display_trip].iloc[0]
    current_trip = matched_trip['name']
    trip_id = int(matched_trip['id'])
    current_trip_date = matched_trip['trip_date']
else:
    st.title("✈️ Trip Expense Splitter Pro")
    st.info("กรุณาสร้าง Event ใหม่ทางเมนูด้านซ้ายเพื่อเริ่มต้นใช้งานครับ")
    # เปิดบล็อกให้สามารถกดสร้าง Event แรกได้โดยไม่พังค้างหน้าจอดับ
    current_trip, trip_id, current_trip_date = None, None, None

with st.sidebar.expander("➕ สร้าง / ✏️ แก้ไข Event"):
    t_mode = st.radio("จัดการ บิล:", ["สร้างทริปใหม่", "แก้ไขทริปปัจจุบัน"], horizontal=True, label_visibility="collapsed")
    if t_mode == "สร้างทริปใหม่":
        new_trip_name = st.text_input("ชื่อ Event ใหม่:", placeholder="เช่น ทริปพัทยา 2026")
        new_trip_date = st.date_input("วันที่จัด Event:", value=datetime.today())
        if st.button("➕ ยืนยันสร้างทริป", use_container_width=True):
            if new_trip_name.strip():
                try:
                    conn_new = get_db_connection()
                    date_str = new_trip_date.strftime("%Y-%m-%d")
                    conn_new.execute("INSERT INTO trips (name, status, trip_date) VALUES (?, 0, ?)", (new_trip_name.strip(), date_str))
                    conn_new.commit(); conn_new.close()
                    st.toast("✈️ สร้าง Event สำเร็จ!")
                    time.sleep(0.5)
                    st.rerun()
                except: st.error("❌ ชื่อ Event ซ้ำ")
    elif t_mode == "แก้ไขทริปปัจจุบัน" and trip_id:
        rename_input = st.text_input("แก้ไขชื่อ:", value=current_trip).strip()
        try: default_date = datetime.strptime(str(current_trip_date), "%Y-%m-%d") if current_trip_date else datetime.today()
        except: default_date = datetime.today()
        re_date_input = st.date_input("แก้ไขวันที่:", value=default_date)
        
        col_ed1, col_ed2 = st.columns(2)
        if col_ed1.button("💾 อัปเดตข้อมูล", use_container_width=True):
            if rename_input:
                try:
                    conn_rename = get_db_connection()
                    conn_rename.execute("UPDATE trips SET name = ?, trip_date = ? WHERE id = ?", (rename_input, re_date_input.strftime("%Y-%m-%d"), trip_id))
                    conn_rename.commit(); conn_rename.close()
                    st.toast("✏️ อัปเดตข้อมูลแล้ว")
                    time.sleep(0.5)
                    st.rerun()
                except: st.error("❌ ชื่อซ้ำ")
        if col_ed2.button("🗑️ ลบลงถังขยะ", type="secondary", use_container_width=True):
            conn.execute("UPDATE trips SET status = 1 WHERE id = ?", (trip_id,))
            conn.commit()
            st.toast("🗑️ ย้ายลงถังขยะแล้ว")
            time.sleep(0.5)
            st.rerun()

# ส่วนจัดการระบบถังขยะย่อส่วนพิเศษ
with st.sidebar.expander("🗑️ ถังขยะ"):
    deleted_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
    if not deleted_trips: st.caption("ถังขยะว่างเปล่า")
    else:
        for dt in deleted_trips:
            c_del1, c_del2 = st.columns([2, 1.2])
            c_del1.caption(f"• {dt['name']}")
            sub_c1, sub_c2 = c_del2.columns(2)
            if sub_c1.button("🔄", key=f"res_{dt['id']}", help="กู้คืน"):
                conn.execute("UPDATE trips SET status = 0 WHERE id = ?", (dt['id'],))
                conn.commit(); st.rerun()
            if sub_c2.button("❌", key=f"pdel_{dt['id']}", help="ลบถาวร"):
                conn.execute("DELETE FROM settlements WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM expenses WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM members WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM trips WHERE id = ?", (dt['id'],))
                conn.commit(); st.rerun()

if trip_id is None:
    st.stop()

# ====== 👥 สมาชิกภายใน Event (Compact Inline Badge Layout) ======
st.sidebar.markdown("### 👥 สมาชิกในกลุ่ม")
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_users = [u for u in existing_all_users if u not in existing_members]

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
        if m_col2.button("✖", key=f"rem_{member}", help=f"ถอดออก"):
            conn_member_notif.execute("DELETE FROM members WHERE trip_id = ? AND name = ?", (trip_id, member))
            conn_member_notif.commit(); st.rerun()
    conn_member_notif.close()

c_mem1, c_mem2 = st.sidebar.columns([2, 1])
selected_u = c_mem1.selectbox("ชวนเพื่อนร่วมกลุ่ม:", ["-- เลือกเพื่อน --"] + available_users, label_visibility="collapsed")
if c_mem2.button("ดึงเข้า", use_container_width=True) and selected_u != "-- เลือกเพื่อน --":
    conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
    conn.commit(); st.rerun()
conn.close()

# 🔔 =================================================================
# 📥 ศูนย์แชทส่วนตัวและการแจ้งเตือนขนาดกระทัดรัด (Mini Chat-Center)
# =================================================================
st.sidebar.markdown("---")
notif_count = 0
if st.session_state["current_online_user"]:
    conn_count = get_db_connection()
    count_row = conn_count.execute("SELECT COUNT(*) as cnt FROM notifications WHERE trip_id = ? AND to_user = ? AND is_read = 0", (trip_id, st.session_state["current_online_user"])).fetchone()
    notif_count = count_row["cnt"] if count_row else 0
    conn_count.close()

notif_title = f"🔔 แชท & แจ้งเตือน (🔴 {notif_count})" if notif_count > 0 else "🔔 แชท & แจ้งเตือน"

if st.session_state["current_online_user"]:
    my_name = st.session_state["current_online_user"]
    with st.sidebar.expander(notif_title, expanded=False):
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

        if not chat_groups:
            st.caption("ไม่มีข้อความ")
        else:
            sender_keys = list(chat_groups.keys())
            tab_labels = [f"🤖 ระบบ" if p == "ระบบสรุปยอด" else f"👤 {p}" + (f"({unread_status[p]})" if unread_status[p]>0 else "") for p in sender_keys]
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
                    
                    # กล่องแสดงแชทแบบมินิ ประหยัดพิกเซลแนวตั้ง
                    st.markdown("<div style='max-height: 160px; overflow-y: auto; padding: 2px;'>", unsafe_allow_html=True)
                    for notif in chat_groups[partner]:
                        t_str = notif['timestamp'][11:16] if notif['timestamp'] else ""
                        is_me_msg = (notif['from_user'] == my_name and notif['is_auto'] == 0)
                        is_sys = (notif['from_user'] == "ระบบสรุปยอด" or notif['is_auto'] == 1)
                        
                        if is_me_msg:
                            bg, align, border_r = "#DCF8C6", "flex-end", "10px 10px 0px 10px"
                        elif is_sys:
                            bg, align, border_r = "#E8F0FE", "flex-start", "0px 10px 10px 10px; border-left: 3px solid #1a73e8;"
                        else:
                            bg, align, border_r = "#F1F0F0", "flex-start", "0px 10px 10px 10px"
                            
                        st.markdown(f'''
                        <div style="display: flex; flex-direction: column; align-items: {align}; margin-bottom: 4px;">
                            <div style="background-color: {bg}; color: #111; padding: 4px 8px; border-radius: {border_r}; max-width: 90%; font-size: 11px; line-height:1.3;">
                                {notif['message']} <span style="font-size: 8px; color: #888; margin-left: 4px;">{t_str}</span>
                            </div>
                        </div>
                        ''', unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    if partner != "ระบบสรุปยอด":
                        with st.form(key=f"reply_{partner}", clear_on_submit=True):
                            c_rp1, c_rp2 = st.columns([3, 1])
                            txt = c_rp1.text_input("ตอบ:", placeholder="พิมพ์...", key=f"in_{partner}", label_visibility="collapsed")
                            if c_rp2.form_submit_button("↩️", use_container_width=True) and txt.strip():
                                conn_rep = get_db_connection()
                                conn_rep.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, ?, ?, 0, 0, datetime('now', 'localtime'))",
                                                 (trip_id, partner, my_name, txt.strip()))
                                conn_rep.commit(); conn_rep.close(); st.rerun()

        with st.expander("📝 ส่งหาคนอื่น"):
            other_m = [m for m in existing_members if m != my_name]
            if other_m:
                to_user = st.selectbox("ถึง:", other_m, key="new_to")
                new_msg = st.text_input("ข้อความ:", key="new_txt")
                if st.button("🚀 ส่ง", use_container_width=True) and new_msg.strip():
                    conn_s = get_db_connection()
                    conn_s.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, ?, ?, 0, 0, datetime('now', 'localtime'))",
                                   (trip_id, to_user, my_name, new_msg.strip()))
                    conn_s.commit(); conn_s.close(); st.rerun()
else:
    st.sidebar.caption("ล็อกอินระบบก่อนใช้งานแชทพาส")

# ====================================================================
# --- 5. พื้นที่ทำงานหลัก (Main UI Display ขนาดเล็กลง กระชับ Scannable) ---
# ====================================================================
has_valid_date = current_trip_date and str(current_trip_date).strip() and not pd.isna(current_trip_date)

if st.session_state["current_online_user"] is None:
    st.title("🛄 กรุณาระบุบัญชีผู้ใช้งาน")
    st.info("เลือกหรือสร้างโปรไฟล์ที่แถบซ้ายมือก่อนเข้าเริ่มลงรายการสถิติทริปเงินครับ")
    st.stop()

if not existing_members:
    st.title(f"✈️ Event: {current_trip}")
    st.warning("⚠️ ยังไม่มีสมาชิกในกลุ่มนี้เลย ชวนตัวคุณเองหรือเพื่อนร่วมบิลที่แถบซ้ายมือก่อนครับ")
    st.stop()

# ส่วนหัวหลักแบบ Slim กะทัดรัด
st.markdown(f"## ✈️ Event: {current_trip} " + (f"<span style='font-size:16px; color:#666;'>(📅 วันที่: {current_trip_date})</span>" if has_valid_date else ""), unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📝 สร้างบิลใหม่", "📊 ประวัติบันทึกบิล", "💰 สรุปเคลียร์เงินสมาชิก"])

with tab1:
    with st.form("add_bill", clear_on_submit=True):
        st.markdown("#### ➕ บันทึกรายการบิลค่าใช้จ่าย")
        
        row_f1, row_f2 = st.columns([2, 1])
        desc = row_f1.text_input("ชื่อรายการ:", placeholder="เช่น ค่าอาหารเย็น, ค่าน้ำมันรถ")
        amt = row_f2.number_input("จำนวนเงินรวม (บาท):", min_value=0.0, step=100.0)
        
        my_name = st.session_state["current_online_user"]
        default_idx = existing_members.index(my_name) if my_name in existing_members else 0
        
        row_f3, row_f4 = st.columns([1, 2])
        payer = row_f3.selectbox("คนสำรองจ่ายเงิน:", existing_members, index=default_idx)
        file = row_f4.file_uploader("สลิปหลักฐาน (ถ้ามี):", type=['jpg','png','jpeg'])
        
        st.markdown("<span style='font-size:13px; font-weight:bold;'>👥 คนร่วมหารในบิลนี้:</span>", unsafe_allow_html=True)
        # จัด Layout ตัวเลือก Checkbox คนหารให้เป็นแถวแนวนอนประหยัดพื้นที่มาก ๆ
        chk_cols = st.columns(max(len(existing_members), 1))
        split_to = []
        for i, m in enumerate(existing_members):
            if chk_cols[i].checkbox(m, value=True, key=f"add_{m}"):
                split_to.append(m)
                
        if st.form_submit_button("💾 ยืนยันการบันทึกบิลบิลค่าใช้จ่ายนี้", type="primary", use_container_width=True):
            if desc and amt > 0 and split_to:
                blob = compress_image(file)
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                               (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit()
                
                # 🤖 ยิงแจ้งเตือน Auto-Notification หาคนโดนหาร
                share_amt = amt / len(split_to)
                for member in split_to:
                    if member != payer:
                        sys_msg = f"📌 บิลใหม่: '{desc}'\n💰 ยอด {amt:,.2f} บ. (จ่ายโดย {payer})\n💸 ส่วนของคุณคือ: {share_amt:,.2f} บาท"
                        conn.execute(
                            "INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, 'ระบบสรุปยอด', ?, 1, 0, datetime('now', 'localtime'))",
                            (trip_id, member, sys_msg)
                        )
                conn.commit(); conn.close()
                st.success("📝 บันทึกบิลสำเร็จและแจ้งเตือนออโต้เรียบร้อยแล้ว!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("⚠️ ข้อมูลไม่ครบถ้วน กรุณากรอกรายการ จำนวนเงิน และเลือกผู้รับหาร")

with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    if not expenses: 
        st.info("ยังไม่มีข้อมูลค่าใช้จ่ายในกลุ่มนี้")
    else:
        # โค้ดส่วนดึงประวัติจะมาต่อตรง Expander ของแถวประวัติบิลย่อส่วน
        for row in expenses:
            with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} บาท (โดย {row['payer_name']})"):
                st.caption(f"👥 คนร่วมหาร: {row['split_members']}")
                if row['image_blob']:
                    st.image(Image.open(io.BytesIO(row['image_blob'])), width=250)
