import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image

# 1. ตั้งค่าหน้าจอ
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# 2. รายชื่อธนาคารและ URL Scheme สำหรับเปิดแอปบนมือถือ
BANK_CONFIG = {
    "กสิกรไทย (KBank)": {"scheme": "kplus://"},
    "ไทยพาณิชย์ (SCB)": {"scheme": "scbeasy://"},
    "กรุงไทย (KTB)": {"scheme": "krungthaibanking://"},
    "กรุงเทพ (BBL)": {"scheme": "bualuangmbanking://"},
    "กรุงศรีอยุธยา (BAY)": {"scheme": "kma://"},
    "ทหารไทยธนชาต (TTB)": {"scheme": "ttbtouch://"},
    "ออมสิน (GSB)": {"scheme": "gsbmyamo://"},
    "ยูโอบี (UOB)": {"scheme": "uobmightyth://"}
}
BANK_LIST = ["-- เลือกธนาคาร --"] + list(BANK_CONFIG.keys()) + ["ธนาคารอื่นๆ"]

DB_FILE = "trip_database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, promptpay TEXT, bank_name TEXT, bank_account TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, status INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS settlements (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(trip_id) REFERENCES trips(id))')
    
    # ตรวจสอบการอัปเดตคอลัมน์ (Migration)
    cursor.execute("PRAGMA table_info(all_users)")
    cols = [row[1] for row in cursor.fetchall()]
    if 'promptpay' not in cols: cursor.execute("ALTER TABLE all_users ADD COLUMN promptpay TEXT")
    if 'bank_name' not in cols: cursor.execute("ALTER TABLE all_users ADD COLUMN bank_name TEXT")
    if 'bank_account' not in cols: cursor.execute("ALTER TABLE all_users ADD COLUMN bank_account TEXT")
    
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

init_db()

# --- 3. Sidebar ---
st.sidebar.header("👥 จัดการสมาชิก & บัญชี")

with st.sidebar.expander("👤 ลงทะเบียน / แก้ไขโปรไฟล์"):
    conn = get_db_connection()
    all_users_list = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
    conn.close()
    
    mode = st.radio("โหมด:", ["เพิ่มใหม่", "แก้ไขบัญชีเดิม"], horizontal=True)
    if mode == "เพิ่มใหม่":
        n_name = st.text_input("ชื่อ:").strip()
        n_pp = st.text_input("พร้อมเพย์:")
        n_bname = st.selectbox("ธนาคาร:", BANK_LIST, key="n_bank")
        n_bacc = st.text_input("เลขบัญชี:")
        if st.button("ลงทะเบียน"):
            if n_name:
                try:
                    conn = get_db_connection()
                    conn.execute("INSERT INTO all_users (name, promptpay, bank_name, bank_account) VALUES (?,?,?,?)", 
                                 (n_name, n_pp, (n_bname if n_bname != "-- เลือกธนาคาร --" else ""), n_bacc))
                    conn.commit(); conn.close(); st.rerun()
                except: st.error("ชื่อซ้ำ")
    else:
        if all_users_list:
            target = st.selectbox("เลือกสมาชิก:", all_users_list)
            conn = get_db_connection()
            u = conn.execute("SELECT * FROM all_users WHERE name = ?", (target,)).fetchone()
            conn.close()
            e_pp = st.text_input("พร้อมเพย์:", value=u['promptpay'] or "")
            e_bname = st.selectbox("ธนาคาร:", BANK_LIST, index=BANK_LIST.index(u['bank_name']) if u['bank_name'] in BANK_LIST else 0)
            e_bacc = st.text_input("เลขบัญชี:", value=u['bank_account'] or "")
            if st.button("บันทึกการแก้ไข"):
                conn = get_db_connection()
                conn.execute("UPDATE all_users SET promptpay=?, bank_name=?, bank_account=? WHERE name=?", 
                             (e_pp, (e_bname if e_bname != "-- เลือกธนาคาร --" else ""), e_bacc, target))
                conn.commit(); conn.close(); st.rerun()

st.sidebar.markdown("---")
new_trip = st.sidebar.text_input("➕ สร้างทริปใหม่:").strip()
if st.sidebar.button("บันทึกทริป"):
    if new_trip:
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO trips (name, status) VALUES (?, 0)", (new_trip,))
            conn.commit(); conn.close(); st.rerun()
        except: st.sidebar.error("ชื่อทริปซ้ำ")

# จัดการถังขยะ
conn = get_db_connection()
with st.sidebar.expander("🗑️ ถังขยะ"):
    d_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
    for dt in d_trips:
        c1, c2 = st.columns([2, 1])
        c1.write(dt['name'])
        if c2.button("กู้", key=f"r_{dt['id']}"):
            conn.execute("UPDATE trips SET status = 0 WHERE id = ?", (dt['id'],))
            conn.commit(); st.rerun()

active_trips = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)
if active_trips.empty:
    st.title("✈️ Trip Expense Splitter Pro")
    st.info("สร้างทริปใหม่ที่เมนูด้านซ้าย")
    st.stop()

st.sidebar.markdown("---")
cur_trip_name = st.sidebar.selectbox("🗺️ เลือกทริป:", active_trips["name"].tolist())
trip_id = conn.execute("SELECT id FROM trips WHERE name = ?", (cur_trip_name,)).fetchone()["id"]

if st.sidebar.button("🗑️ ย้ายทริปลงถังขยะ"):
    conn.execute("UPDATE trips SET status = 1 WHERE id = ?", (trip_id,))
    conn.commit(); st.rerun()

# จัดการสมาชิกในทริป
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
all_u = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
avail = [u for u in all_u if u not in existing_members]
sel_u = st.sidebar.selectbox("เพิ่มเพื่อนเข้าทริป:", ["-- เลือก --"] + avail)
if st.sidebar.button("ดึงเข้าทริป") and sel_u != "-- เลือก --":
    conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, sel_u))
    conn.commit(); st.rerun()
conn.close()

# --- 4. Main UI ---
st.title(f"✈️ ทริป: {cur_trip_name}")
if not existing_members:
    st.warning("เพิ่มสมาชิกเข้าทริปก่อนเริ่มใช้งาน")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📝 สร้างบิล", "📊 ประวัติ", "💰 สรุปเคลียร์เงิน"])

with tab1:
    with st.form("add_bill", clear_on_submit=True):
        st.subheader("➕ เพิ่มรายการใหม่")
        d = st.text_input("รายการ:")
        a = st.number_input("เงิน:", min_value=0.0)
        p = st.selectbox("คนจ่าย:", existing_members)
        st.write("คนหาร:")
        s_to = [m for m in existing_members if st.checkbox(m, value=True, key=f"b_{m}")]
        f = st.file_uploader("สลิป:", type=['jpg','png','jpeg'])
        if st.form_submit_button("บันทึก"):
            if d and a > 0 and s_to:
                blob = compress_image(f)
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, d, a, p, ",".join(s_to), blob))
                conn.commit(); conn.close(); st.rerun()

with tab2:
    conn = get_db_connection()
    exps = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    for row in exps:
        with st.expander(f"📌 {row['description']} | {row['amount']:,.2f}"):
            c1, c2 = st.columns([1, 1.2])
            if row['image_blob']: c1.image(row['image_blob'], use_container_width=True)
            if c2.button("🗑️ ลบบิลนี้", key=f"del_{row['id']}"):
                conn = get_db_connection()
                conn.execute("DELETE FROM expenses WHERE id=?", (row['id'],))
                conn.commit(); conn.close(); st.rerun()

with tab3:
    st.header("🤝 สรุปยอดเคลียร์เงิน")
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    profiles = {r['name']: r for r in conn.execute("SELECT * FROM all_users").fetchall()}
    conn.close()
    
    if not rows: st.info("ยังไม่มีข้อมูลค่าใช้จ่าย")
    else:
        net = {m: 0.0 for m in existing_members}
        for r in rows:
            net[r['payer_name']] += r['amount']
            shares = r['split_members'].split(",")
            for m in shares: net[m] -= (r['amount'] / len(shares))
        
        # แผนการโอน
        debtors = [[m, b] for m, b in net.items() if b < -0.01]
        creditors = [[m, b] for m, b in net.items() if b > 0.01]
        final_tx = []
        
        while debtors and creditors:
            amt = min(abs(debtors[0][1]), creditors[0][1])
            d_name, c_name = debtors[0][0], creditors[0][0]
            
            # ดึงข้อมูลบัญชีผู้รับ
            p = profiles.get(c_name, {})
            acc_str = f"📱 PP: {p['promptpay'] or '-'}"
            if p['bank_name']: acc_str += f" | 🏦 {p['bank_name']}: {p['bank_account']}"
            
            st.info(f"💳 **{d_name}** ➔ **{c_name}** | **{amt:,.2f} บาท**\n\n{acc_str}")
            
            # ปุ่ม Deep Link
            b_name = p.get('bank_name')
            if b_name in BANK_CONFIG:
                url = BANK_CONFIG[b_name]["scheme"]
                st.markdown(f'<a href="{url}" target="_blank" style="text-decoration:none;"><div style="display:inline-block;padding:8px 16px;background-color:#2e7d32;color:white;border-radius:4px;font-weight:bold;margin-bottom:15px;">📲 เปิดแอป {b_name}</div></a>', unsafe_allow_html=True)
            elif p.get('promptpay'):
                st.markdown('<a href="kplus://" target="_blank" style="text-decoration:none;"><div style="display:inline-block;padding:8px 16px;background-color:#1976d2;color:white;border-radius:4px;font-weight:bold;margin-bottom:15px;">📱 เปิด K PLUS (โอนพร้อมเพย์)</div></a>', unsafe_allow_html=True)
            
            final_tx.append((d_name, c_name, amt))
            debtors[0][1] += amt; creditors[0][1] -= amt
            if abs(debtors[0][1]) < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)

        if st.button("🎯 บันทึกปิดทริป", type="primary"):
            conn = get_db_connection()
            conn.execute("DELETE FROM settlements WHERE trip_id = ?", (trip_id,))
            for t in final_tx: conn.execute("INSERT INTO settlements (trip_id, debtor, creditor, amount) VALUES (?,?,?,?)", (trip_id, t[0], t[1], t[2]))
            conn.commit(); conn.close(); st.success("บันทึกสำเร็จ!")
