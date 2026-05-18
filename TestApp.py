import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
from datetime import datetime

# 1. Page Configuration (Facebook Clean Theme)
st.set_page_config(
    page_title="TripSplit - Facebook Style", 
    page_icon="👥", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS เพื่อตกแต่งหน้าตาให้มีความเป็น Facebook (Clean, Rounded, Card-based)
st.markdown("""
<style>
    .stApp { background-color: #f0f2f5; }
    .fb-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
        margin-bottom: 15px;
    }
    .fb-header {
        color: #1877f2;
        font-weight: bold;
    }
    .online-badge {
        background-color: #31a24c;
        color: white;
        padding: 2px 8px;
        border-radius: 50px;
        font-size: 12px;
    }
</style>
""", unsafe_allow_html=True)

DB_FILE = "trip_facebook_style.db"
BANK_LIST = ["-- เลือกธนาคาร --", "กสิกรไทย (KBank)", "ไทยพาณิชย์ (SCB)", "กรุงไทย (KTB)", "กรุงเทพ (BBL)"]

# 2. Database Layer (Optimized Schema)
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        # User & Social Graph
        conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, promptpay TEXT, bank_name TEXT, bank_account TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, date TEXT, status INTEGER DEFAULT 0)')
        conn.execute('CREATE TABLE IF NOT EXISTS group_members (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER, username TEXT, FOREIGN KEY(group_id) REFERENCES groups(id))')
        
        # Feed Content (Expenses)
        conn.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)')
        
        # Real-time Engine
        conn.execute('CREATE TABLE IF NOT EXISTS presence (username TEXT PRIMARY KEY, last_seen DATETIME)')
        conn.execute('CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER, to_user TEXT, from_user TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)')
        conn.commit()

init_db()

# Session State Initialization
if "current_user" not in st.session_state:
    st.session_state["current_user"] = None

# Heartbeat System (Facebook Presence)
def update_presence(username):
    if username:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO presence (username, last_seen) VALUES (?, datetime('now', 'localtime')) ON CONFLICT(username) DO UPDATE SET last_seen = datetime('now', 'localtime')", (username,))
            conn.commit()

def get_online_users():
    with get_db_connection() as conn:
        rows = conn.execute("SELECT username FROM presence WHERE last_seen >= datetime('now', 'localtime', '-30 seconds')").fetchall()
        return [row["username"] for row in rows]

if st.session_state["current_user"]:
    update_presence(st.session_state["current_user"])

# --- SIDEBAR: Profile & Navigation ---
st.sidebar.markdown("<h2 class='fb-header'>👥 Facebook TripSplit</h2>", unsafe_allow_html=True)

# Authentication Block
if st.session_state["current_user"] is None:
    st.sidebar.subheader("🔐 เข้าสู่ระบบ / สร้างโปรไฟล์")
    with st.sidebar.form("login_form"):
        username_input = st.text_input("ชื่อผู้ใช้งานของคุณ:").strip()
        submit_login = st.form_submit_button("Log In")
        if submit_login and username_input:
            with get_db_connection() as conn:
                try:
                    conn.execute("INSERT INTO users (name) VALUES (?)", (username_input,))
                except sqlite3.IntegrityError:
                    pass # มีผู้ใช้นี้อยู่แล้ว
            st.session_state["current_user"] = username_input
            st.rerun()
else:
    my_user = st.session_state["current_user"]
    st.sidebar.markdown(f"🟢 เข้าสู่ระบบเป็น: **{my_user}**")
    if st.sidebar.button("🚪 ออกจากระบบ", type="secondary"):
        st.session_state["current_user"] = None
        st.rerun()

    # Active Friends Section
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🟢 เพื่อนที่ออนไลน์ขณะนี้")
    online_list = get_online_users()
    for user in online_list:
        status_label = "(คุณ)" if user == my_user else ""
        st.sidebar.markdown(f"• **{user}** <span style='color:green;'>●</span> {status_label}", unsafe_allow_html=True)

# --- MAIN CONTENT AREA ---
if st.session_state["current_user"] is None:
    st.title("🚀 ยินดีต้อนรับสู่ Trip Expense Splitter")
    st.info("กรุณาระบุชื่อผู้ใช้งานของคุณที่แถบด้านซ้ายเพื่อเริ่มต้นใช้งานระบบฟีดร่วมกับเพื่อนๆ")
    st.stop()

# Group Selection (เสมือนการเลือกกลุ่มท่องเที่ยว/Event บน Facebook)
with get_db_connection() as conn:
    all_groups = conn.execute("SELECT * FROM groups WHERE status = 0").fetchall()

st.markdown("<div class='fb-card'>", unsafe_allow_html=True)
c_grp1, c_grp2 = st.columns([2, 1])
with c_grp1:
    if all_groups:
        group_options = {f"⛺ {g['name']} ({g['date']})": g['id'] for g in all_groups}
        selected_group_name = st.selectbox("🗺️ เลือกกลุ่ม / ทริปของคุณ:", list(group_options.keys()))
        active_group_id = group_options[selected_group_name]
    else:
        st.warning("ยังไม่มีทริปเปิดอยู่ กรุณาสร้างทริปใหม่ที่ปุ่มขวามือ")
        active_group_id = None
with c_grp2:
    with st.expander("➕ สร้างกลุ่มทripใหม่"):
        with st.form("new_group_form"):
            g_name = st.text_input("ชื่อทริป:")
            g_date = st.date_input("วันที่:")
            if st.form_submit_button("สร้าง"):
                if g_name:
                    with get_db_connection() as conn:
                        conn.execute("INSERT INTO groups (name, date) VALUES (?, ?)", (g_name, str(g_date)))
                    st.success("สร้างทริปสำเร็จ")
                    st.rerun()
st.markdown("</div>", unsafe_allow_html=True)

if not active_group_id:
    st.stop()

# Manage Members in Group
with get_db_connection() as conn:
    current_members = [r['username'] for r in conn.execute("SELECT username FROM group_members WHERE group_id = ?", (active_group_id,)).fetchall()]
    all_system_users = [r['name'] for r in conn.execute("SELECT name FROM users").fetchall()]

# เพิ่มตัวเองเข้ากลุ่มอัตโนมัติหากยังไม่ได้เข้า
if my_user not in current_members:
    with get_db_connection() as conn:
        conn.execute("INSERT INTO group_members (group_id, username) VALUES (?,?)", (active_group_id, my_user))
    st.rerun()

# Layout แยกเป็น 2 ฝั่ง: Left (Feed และ การคำนวณ) | Right (Notification Center & Chat)
left_flow, right_sidebar = st.columns([2, 1])

with left_flow:
    tab_feed, tab_add, tab_calc = st.tabs(["📰 ข่าวสาร/ฟีดบิล (Feed)", "✍️ สร้างโพสต์บิลใหม่", "💰 สรุปยอดเคลียร์เงิน"])
    
    with tab_feed:
        # Facebook Sync Button แทนการสั่นหน้าจออัตโนมัติ ทุกๆ 1 วินาที
        if st.button("🔄 ดึงข้อมูลใหม่ (Sync Feed)", type="primary", use_container_width=True):
            st.rerun()

        with get_db_connection() as conn:
            feed_items = conn.execute("SELECT * FROM expenses WHERE group_id = ? ORDER BY created_at DESC", (active_group_id,)).fetchall()
        
        if not feed_items:
            st.info("ยังไม่มีโพสต์ค่าใช้จ่ายในทริปนี้ มาเริ่มสร้างโพสต์แรกกันเลย!")
        else:
            for item in feed_items:
                st.markdown(f"""
                <div class='fb-card'>
                    <span style='font-size:20px;'>👤</span> <b>{item['payer_name']}</b> ได้เพิ่มบิลใหม่ <br>
                    <small style='color:grey;'>📅 {item['created_at']}</small>
                    <hr style='margin: 10px 0;'>
                    <h4 style='color:#1c1e21;'>📝 รายการ: {item['description']}</h4>
                    <h3 style='color:#1877f2;'>💰 จำนวนเงิน: {item['amount']:,.2f} บาท</h3>
                    <p style='background:#f0f2f5; padding:8px; border-radius:5px; font-size:13px;'>
                        👥 <b>ผู้ร่วมหาร:</b> {item['split_members']}
                    </p>
                </div>
                """, unsafe_allow_html=True)

    with tab_add:
        st.subheader("📸 สร้างโพสต์บilt")
        with st.form("add_expense_form", clear_on_submit=True):
            exp_desc = st.text_input("พวกเราไปจ่ายค่าอะไรมา? (เช่น ค่าที่พัก, มื้อเย็น):")
            exp_amount = st.number_input("จำนวนเงินรวม (บาท):", min_value=0.0, step=100.0)
            exp_payer = st.selectbox("ใครเป็นคนสำรองจ่ายล่วงหน้าก่อน:", current_members)
            
            st.markdown("<b>เลือกเพื่อนร่วมชะตากรรม (หารเท่า):</b>", unsafe_allow_html=True)
            selected_shares = [m for m in current_members if st.checkbox(m, value=True, key=f"share_{m}")]
            
            if st.form_submit_button("🚀 โพสต์ลงฟีดทริป"):
                if exp_desc and exp_amount > 0 and selected_shares:
                    share_cost = exp_amount / len(selected_shares)
                    with get_db_connection() as conn:
                        conn.execute(
                            "INSERT INTO expenses (group_id, description, amount, payer_name, split_members) VALUES (?,?,?,?,?)",
                            (active_group_id, exp_desc, exp_amount, exp_payer, ", ".join(selected_shares))
                        )
                        # ระบบแจ้งเตือนอัตโนมัติ (Push Notification) ไปหาทุกคน
                        for member in selected_shares:
                            if member != exp_payer:
                                notif_text = f"คุณมีบิลหารค้างชำระจากค่า '{exp_desc}' ยอดของคุณคือ {share_cost:,.2f} บาท (จ่ายให้ {exp_payer})"
                                conn.execute(
                                    "INSERT INTO notifications (group_id, to_user, from_user, message) VALUES (?,?,?,?)",
                                    (active_group_id, member, "ระบบส่วนกลาง", notif_text)
                                )
                    st.success("บันทึกข้อมูลและส่งแจ้งเตือนเข้าแชทเพื่อนๆ เรียบร้อย!")
                    time.sleep(0.5)
                    st.rerun()

    with tab_calc:
        st.subheader("🧮 อัลกอริทึมหักลบกลบหนี้ส่วนกลาง")
        # โค้ดส่วนนี้ทำหน้าที่คำนวณเงินจากประวัติทั้งหมดในฐานข้อมูล
        with get_db_connection() as conn:
            all_exp = conn.execute("SELECT * FROM expenses WHERE group_id = ?", (active_group_id,)).fetchall()
        
        balances = {m: 0.0 for m in current_members}
        for e in all_exp:
            payer = e['payer_name']
            amt = e['amount']
            split_m = [x.strip() for x in e['split_members'].split(",") if x.strip() in balances]
            
            if split_m:
                share = amt / len(split_m)
                balances[payer] += amt
                for m in split_m:
                    balances[m] -= share

        st.markdown("### 📊 บัญชีดุลรวมของแต่ละคน")
        for name, bal in balances.items():
            if bal > 0:
                st.success(f"• **{name}** จะต้องได้รับเงินคืนทั้งหมด: `+{bal:,.2f}` บาท")
            elif bal < 0:
                st.error(f"• **{name}** ติดหนี้เพื่อนคนอื่นๆ รวมกัน: `{bal:,.2f}` บาท")
            else:
                st.info(f"• **{name}** เจ๊ากันพอดี ไม่ติดค้างใคร")

with right_sidebar:
    st.markdown("<h3 style='color:#1c1e21;'>🔔 ศูนย์การแจ้งเตือนและการติดต่อ</h3>", unsafe_allow_html=True)
    
    # แสดงกล่องจดหมายเข้าของผู้ใช้ปัจจุบัน
    with get_db_connection() as conn:
        my_notifs = conn.execute(
            "SELECT * FROM notifications WHERE group_id = ? AND to_user = ? ORDER BY id DESC", 
            (active_group_id, my_user)
        ).fetchall()
        unread_count = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE group_id = ? AND to_user = ? AND is_read = 0", 
            (active_group_id, my_user)
        ).fetchone()[0]

    if unread_count > 0:
        st.markdown(f"🔵 **คุณมีข้อความใหม่ที่ยังไม่ได้อ่าน `{unread_count}` รายการ**")
        if st.button("Mark all as read (อ่านแล้วทั้งหมด)"):
            with get_db_connection() as conn:
                conn.execute("UPDATE notifications SET is_read = 1 WHERE group_id = ? AND to_user = ?", (active_group_id, my_user))
            st.rerun()

    st.markdown("<div style='max-height: 400px; overflow-y: auto;'>", unsafe_allow_html=True)
    for nt in my_notifs:
        bg_color = "#e7f3ff" if nt['is_read'] == 0 else "#ffffff"
        st.markdown(f"""
        <div style='background-color: {bg_color}; padding: 10px; border-radius: 8px; margin-bottom: 5px; border: 1px solid #ddd;'>
            <small><b>จาก: {nt['from_user']}</b></small><br>
            <span style='font-size: 13px;'>{nt['message']}</span>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # เชิญชวนเพื่อนเข้ามาเพิ่มในกรุ๊ปทริป
    st.markdown("---")
    st.markdown("#### ➕ ชวนสมาชิกเพิ่มเข้าทริปนี้")
    available_to_invite = [u for u in all_system_users if u not in current_members]
    if available_to_invite:
        user_to_add = st.selectbox("เลือกรายชื่อสมาชิกในระบบ:", available_to_invite)
        if st.button("ดึงเพื่อนเข้ากลุ่ม"):
            with get_db_connection() as conn:
                conn.execute("INSERT INTO group_members (group_id, username) VALUES (?,?)", (active_group_id, user_to_add))
            st.toast(f"เพิ่ม {user_to_add} เข้ากลุ่มสำเร็จ")
            st.rerun()
    else:
        st.caption("ดึงผู้ใช้ทุกคนในระบบเข้าร่วมทริปนี้หมดเรียบร้อยแล้ว")
