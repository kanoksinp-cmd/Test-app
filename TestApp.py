import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
from datetime import datetime

# 1. Page Configuration (Facebook Clean Theme)
st.set_page_config(
    page_title="TripSplit Pro - Facebook Style", 
    page_icon="👥", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS ตกแต่งหน้าตาแอปพลิเคชันให้ดูสะอาด สไตล์ Facebook (Card-Based UI)
st.markdown("""
<style>
    .stApp { background-color: #f0f2f5; }
    .fb-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
        margin-bottom: 15px;
    }
    .fb-header {
        color: #1877f2;
        font-weight: bold;
    }
    .online-dot {
        color: #31a24c;
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)

DB_FILE = "trip_facebook_style.db"

# 2. Database Layer (สร้างตารางรองรับระบบเครือข่ายสมาชิก)
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        # ระบบสมาชิกและการเชื่อมโยงกลุ่ม
        conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, promptpay TEXT, bank_name TEXT, bank_account TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, date TEXT, status INTEGER DEFAULT 0)')
        conn.execute('CREATE TABLE IF NOT EXISTS group_members (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER, username TEXT, UNIQUE(group_id, username), FOREIGN KEY(group_id) REFERENCES groups(id))')
        
        # ระบบกระดานข่าวสารและบิลค่าใช้จ่าย
        conn.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)')
        
        # ระบบสัญญานชีพออนไลน์ และระบบแจ้งเตือน (Notification Center)
        conn.execute('CREATE TABLE IF NOT EXISTS presence (username TEXT PRIMARY KEY, last_seen DATETIME)')
        conn.execute('CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER, to_user TEXT, from_user TEXT, message TEXT, is_read INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)')
        conn.commit()

init_db()

# ตรวจสอบเซสชันผู้ใช้งานปัจจุบัน
if "current_user" not in st.session_state:
    st.session_state["current_user"] = None

# ฟังก์ชันจัดการสถานะออนไลน์ (Facebook Presence Engine)
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

# --- SIDEBAR: จัดการโปรไฟล์และการแสดงผลเพื่อนพ้อง ---
st.sidebar.markdown("<h2 class='fb-header'>👥 Facebook TripSplit</h2>", unsafe_allow_html=True)

if st.session_state["current_user"] is None:
    st.sidebar.subheader("🔐 ระบุโปรไฟล์เพื่อเชื่อมต่อเพื่อน")
    with st.sidebar.form("login_form"):
        username_input = st.text_input("พิมพ์ชื่อเล่น/ชื่อของคุณ:").strip()
        submit_login = st.form_submit_button("เข้าสู่ระบบ (Log In)")
        if submit_login and username_input:
            with get_db_connection() as conn:
                try:
                    conn.execute("INSERT INTO users (name) VALUES (?)", (username_input,))
                except sqlite3.IntegrityError:
                    pass  # ชื่อซ้ำในระบบส่วนกลางไม่เป็นไร ใช้ล็อกอินต่อได้เลย
            st.session_state["current_user"] = username_input
            st.rerun()
else:
    my_user = st.session_state["current_user"]
    st.sidebar.success(f"🟢 โปรไฟล์ของคุณ: **{my_user}**")
    if st.sidebar.button("🚪 ออกจากระบบ", type="secondary"):
        st.session_state["current_user"] = None
        st.rerun()

    # แสดงรายชื่อคนออนไลน์ในระบบฐานข้อมูลเดียวกันปัจจุบัน
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🟢 สมาชิกที่ออนไลน์ในระบบ")
    online_list = get_online_users()
    if online_list:
        for user in online_list:
            status_label = "*(คุณ)*" if user == my_user else ""
            st.sidebar.markdown(f"• **{user}** <span class='online-dot'>●</span> {status_label}", unsafe_allow_html=True)
    else:
        st.sidebar.caption("ไม่มีผู้ใช้คนอื่นออนไลน์")

# --- MAIN WORKSPACE ---
if st.session_state["current_user"] is None:
    st.title("🚀 ยินดีต้อนรับสู่ระบบหารเงินทริปสไตล์ Facebook")
    st.info("💡 เพื่อให้เจอเพื่อนๆ กรุณากรอกชื่อของคุณที่เมนูด้านซ้ายมือก่อนเริ่มต้นใช้งาน")
    st.stop()

# เลือกรวมกลุ่ม (Facebook Group Setup)
with get_db_connection() as conn:
    all_groups = conn.execute("SELECT * FROM groups WHERE status = 0").fetchall()

st.markdown("<div class='fb-card'>", unsafe_allow_html=True)
c_grp1, c_grp2 = st.columns([2, 1])
with c_grp1:
    if all_groups:
        group_options = {f"⛺ {g['name']} 📅 ({g['date']})": g['id'] for g in all_groups}
        selected_group_name = st.selectbox("🗺️ เลือกกลุ่มทริปที่คุณต้องการเข้าใช้งานร่วมกัน:", list(group_options.keys()))
        active_group_id = group_options[selected_group_name]
    else:
        st.warning("⚠️ ยังไม่มีกลุ่มทริปถูกสร้างขึ้นในฐานข้อมูลส่วนกลาง")
        active_group_id = None
with c_grp2:
    with st.expander("➕ สร้างกลุ่มทริปอันใหม่"):
        with st.form("new_group_form"):
            g_name = st.text_input("ระบุชื่อทริป/กิจกรรม:").strip()
            g_date = st.date_input("วันที่จัดกิจกรรม:")
            if st.form_submit_button("สร้างอีเวนต์กลุ่ม"):
                if g_name:
                    try:
                        with get_db_connection() as conn:
                            conn.execute("INSERT INTO groups (name, date) VALUES (?, ?)", (g_name, str(g_date)))
                        st.success(f"สร้างทริป '{g_name}' สำเร็จแล้ว!")
                        time.sleep(0.5)
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("ชื่อทริปนี้มีอยู่แล้ว ลองเปลี่ยนชื่อเล็กน้อยครับ")

if not active_group_id:
    st.info("กรุณาสร้างกลุ่มทริปใหม่ที่เมนูด้านขวาบน เพื่อเริ่มต้นการแชร์ข้อมูลบิลร่วมกัน")
    st.stop()

# 🛡️ ระบบแก้ปัญหา "ไม่เจอกัน" (Auto-Join Engine)
# ค้นหาผู้ใช้ทุกคนในตารางระบบ แล้วจับยัดเข้าตารางทริปปัจจุบันทันทีโดยอัตโนมัติ
with get_db_connection() as conn:
    all_users = [r['name'] for r in conn.execute("SELECT name FROM users").fetchall()]
    current_members = [r['username'] for r in conn.execute("SELECT username FROM group_members WHERE group_id = ?", (active_group_id,)).fetchall()]

with get_db_connection() as conn:
    for user in all_users:
        if user not in current_members:
            # เพิ่มสมาชิกใหม่เข้ากลุ่มอัตโนมัติ (เสมือนการ Sync ทุกคนให้มารวมกันในทริปนี้)
            conn.execute("INSERT OR IGNORE INTO group_members (group_id, username) VALUES (?,?)", (active_group_id, user))
            current_members.append(user)

# แบ่งหน้าจอเป็นฝั่งซ้าย (ฟีด-คำนวณ) และ ฝั่งขวา (กระดานแจ้งเตือนส่วนตัว)
left_flow, right_sidebar = st.columns([2, 1])

with left_flow:
    tab_feed, tab_add, tab_calc = st.tabs(["📰 ข่าวสาร/ฟีดบิล (Feed)", "✍️ โพสต์บิลค่าใช้จ่ายใหม่", "💰 สรุปหักลบยอดเงิน"])
    
    with tab_feed:
        # ปุ่มซิงค์ข้อมูลแบบไม่ต้องบังคับสั่นจอทุกวินาที
        if st.button("🔄 ดึงฟีดข้อมูลล่าสุด (Sync Feed)", type="primary", use_container_width=True):
            st.rerun()

        with get_db_connection() as conn:
            feed_items = conn.execute("SELECT * FROM expenses WHERE group_id = ? ORDER BY created_at DESC", (active_group_id,)).fetchall()
        
        if not feed_items:
            st.info("💭 ยังไม่มีความเคลื่อนไหวหรือโพสต์บิลในกลุ่มทริปนี้เลย มาร่วมสร้างบิลแรกกัน")
        else:
            for item in feed_items:
                st.markdown(f"""
                <div class='fb-card'>
                    <span style='font-size:22px;'>👤</span> <b>{item['payer_name']}</b> ได้แชร์บิลค่าใช้จ่ายใหม่ลงในกลุ่ม <br>
                    <small style='color:grey;'>⏱️ เมื่อ: {item['created_at']}</small>
                    <hr style='margin: 10px 0; border: 0.5px solid #e5e5e5;'>
                    <h4 style='color:#1c1e21; margin: 0 0 5px 0;'>📝 รายการ: {item['description']}</h4>
                    <h3 style='color:#1877f2; margin: 0 0 10px 0;'>💰 ยอดเงินรวม: {item['amount']:,.2f} บาท</h3>
                    <p style='background-color:#f0f2f5; padding:10px; border-radius:8px; font-size:13px; margin:0;'>
                        👥 <b>คนที่ร่วมแชร์ค่าใช้จ่ายนี้:</b> {item['split_members']}
                    </p>
                </div>
                """, unsafe_allow_html=True)

    with tab_add:
        st.subheader("📸 สร้างโพสต์บิลแชร์ค่าใช้จ่าย")
        with st.form("add_expense_form", clear_on_submit=True):
            exp_desc = st.text_input("จ่ายค่าอะไรไป? (เช่น ค่าทางด่วน, มื้อค่ำ, บุฟเฟต์):").strip()
            exp_amount = st.number_input("จำนวนเงินทั้งหมดตามใบเสร็จ (บาท):", min_value=0.0, step=50.0)
            exp_payer = st.selectbox("เลือกคนที่ออกเงินสำรองจ่ายไปก่อน:", current_members, index=current_members.index(my_user) if my_user in current_members else 0)
            
            st.markdown("<b>ติ๊กเลือกเพื่อนในกลุ่มร่วมหาร (หารเท่ากันทุกคนที่ติ๊ก):</b>", unsafe_allow_html=True)
            selected_shares = [m for m in current_members if st.checkbox(m, value=True, key=f"share_{m}")]
            
            if st.form_submit_button("🚀 แชร์โพสต์ลงฟีดกลุ่มทริป"):
                if exp_desc and exp_amount > 0 and selected_shares:
                    share_cost = exp_amount / len(selected_shares)
                    with get_db_connection() as conn:
                        conn.execute(
                            "INSERT INTO expenses (group_id, description, amount, payer_name, split_members) VALUES (?,?,?,?,?)",
                            (active_group_id, exp_desc, exp_amount, exp_payer, ", ".join(selected_shares))
                        )
                        # ส่งระบบแจ้งเตือนเข้ากล่อง Inbox ส่วนตัวของทุกคนที่โดนหารเงิน
                        for member in selected_shares:
                            if member != exp_payer:
                                notif_text = f"📌 บิลใหม่ถูกโพสต์: ยอดหารค่า '{exp_desc}' ส่วนของคุณคือ {share_cost:,.2f} บาท (โปรดโอนคืนให้ {exp_payer})"
                                conn.execute(
                                    "INSERT INTO notifications (group_id, to_user, from_user, message) VALUES (?,?,?,?)",
                                    (active_group_id, member, "ระบบส่วนกลาง", notif_text)
                                )
                    st.success("🎉 โพสต์บิลลงฟีดสำเร็จ และส่ง Notification เตือนเพื่อนๆ แล้ว!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("⚠️ ข้อมูลไม่ครบถ้วน กรุณากรอกรายการ ยอดเงิน และเลือกคนร่วมหารด้วยครับ")

    with tab_calc:
        st.subheader("🧮 การสรุปเคลียร์บัญชีหักลบกลบหนี้")
        
        with get_db_connection() as conn:
            all_exp = conn.execute("SELECT * FROM expenses WHERE group_id = ?", (active_group_id,)).fetchall()
        
        balances = {m: 0.0 for m in current_members}
        for e in all_exp:
            payer = e['payer_name']
            amt = e['amount']
            split_m = [x.strip() for x in e['split_members'].split(",") if x.strip() in balances]
            
            if split_m:
                share = amt / len(split_m)
                if payer in balances:
                    balances[payer] += amt
                for m in split_m:
                    balances[m] -= share

        st.markdown("### 📊 บัญชีดุลรวมสุทธิในทริปปัจจุบัน")
        for name, bal in balances.items():
            if bal > 0:
                st.success(f"• 🟩 **{name}** จะต้องได้รับเงินโอนคืนจากเพื่อนๆ รวม: `+{bal:,.2f}` บาท")
            elif bal < 0:
                st.error(f"• 🟥 **{name}** มียอดติดหนี้คนอื่นรวม: `{bal:,.2f}` บาท")
            else:
                st.info(f"• 🟦 **{name}** ยอดสมดุลเป็นศูนย์พอดี (จ่ายและหารเท่าเพื่อนแล้ว)")

# ฝั่งขวา: ศูนย์รวมกระดานแจ้งเตือนเฉพาะของตัวเอง (Facebook Notification Center)
with right_sidebar:
    st.markdown("<h3 style='color:#1c1e21;'>🔔 การแจ้งเตือนของคุณ</h3>", unsafe_allow_html=True)
    
    with get_db_connection() as conn:
        my_notifs = conn.execute("SELECT * FROM notifications WHERE group_id = ? AND to_user = ? ORDER BY id DESC", (active_group_id, my_user)).fetchall()
        unread_count = conn.execute("SELECT COUNT(*) FROM notifications WHERE group_id = ? AND to_user = ? AND is_read = 0", (active_group_id, my_user)).fetchone()[0]

    if unread_count > 0:
        st.markdown(f"🔵 **คุณมีข้อความใหม่แจ้งเตือนการหารเงินค้างอยู่ `{unread_count}` รายการ**")
        if st.button("👁️ ทำเครื่องหมายว่าอ่านแล้วทั้งหมด"):
            with get_db_connection() as conn:
                conn.execute("UPDATE notifications SET is_read = 1 WHERE group_id = ? AND to_user = ?", (active_group_id, my_user))
            st.rerun()

    # แสดงผลกล่องข้อความเตือนภัยต่างๆ
    st.markdown("<div style='max-height: 450px; overflow-y: auto;'>", unsafe_allow_html=True)
    if not my_notifs:
        st.caption("ไม่มีรายการแจ้งเตือนค้างอยู่")
    else:
        for nt in my_notifs:
            bg_color = "#e7f3ff" if nt['is_read'] == 0 else "#ffffff"
            st.markdown(f"""
            <div style='background-color: {bg_color}; padding: 12px; border-radius: 8px; margin-bottom: 8px; border: 1px solid #ddd; box-shadow: 0 1px 1px rgba(0,0,0,0.05);'>
                <small style='color:#1877f2;'><b>📢 จาก: {nt['from_user']}</b></small><br>
                <span style='font-size: 13px; color:#333;'>{nt['message']}</span><br>
                <small style='color:grey; font-size:10px;'>⏱️ {nt['created_at']}</small>
            </div>
            """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
