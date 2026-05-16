import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time

# 1. ตั้งค่าหน้าจอ
st.set_page_config(page_title="Trip Expense Splitter Pro", layout="wide")

# 2. ฟังก์ชันจัดการฐานข้อมูล
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
    
    # อัปเดตโครงสร้างรองรับประเภทธนาคารเพิ่มเติม
    cursor.execute("PRAGMA table_info(all_users)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'promptpay' not in columns:
        cursor.execute("ALTER TABLE all_users ADD COLUMN promptpay TEXT")
    if 'bank_name' not in columns:
        cursor.execute("ALTER TABLE all_users ADD COLUMN bank_name TEXT")
    if 'bank_account' not in columns:
        cursor.execute("ALTER TABLE all_users ADD COLUMN bank_account TEXT")
        
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

with st.sidebar.expander("👤 ลงทะเบียน / แก้ไขข้อมูลสมาชิก"):
    conn = get_db_connection()
    existing_all_users = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
    conn.close()
    
    user_mode = st.radio("เลือกการทำงาน:", ["ลงทะเบียนใหม่", "อัปเดตข้อมูลบัญชีเดิม"], horizontal=True)
    
    if user_mode == "ลงทะเบียนใหม่":
        reg_name = st.text_input("ชื่อผู้ใช้งานใหม่:").strip()
        reg_pp = st.text_input("เลขพร้อมเพย์ (ไม่บังคับ):", key="reg_pp").strip()
        reg_bank_name = st.selectbox("เลือกธนาคาร:", BANK_LIST, key="reg_bank_name")
        reg_bank_acc = st.text_input("เลขบัญชีธนาคาร:", key="reg_bank_acc").strip()
        
        if st.button("เพิ่มสมาชิก"):
            if reg_name:
                try:
                    final_bank = reg_bank_name if reg_bank_name != "-- เลือกธนาคาร --" else ""
                    conn = get_db_connection()
                    conn.execute("INSERT INTO all_users (name, promptpay, bank_name, bank_account) VALUES (?, ?, ?, ?)", 
                                 (reg_name, reg_pp, final_bank, reg_bank_acc))
                    conn.commit(); conn.close()
                    st.success(f"🎉 ลงทะเบียนสมาชิก '{reg_name}' สำเร็จแล้ว!")
                    time.sleep(1)
                    st.rerun()
                except: st.sidebar.error("❌ ชื่อนี้มีในระบบแล้ว")
            else:
                st.error("⚠️ กรุณากรอกชื่อสมาชิก")
                
    else:
        if existing_all_users:
            target_user = st.selectbox("เลือกสมาชิกที่ต้องการอัปเดต:", existing_all_users)
            conn = get_db_connection()
            user_data = conn.execute("SELECT * FROM all_users WHERE name = ?", (target_user,)).fetchone()
            conn.close()
            
            edit_pp = st.text_input("แก้ไขเลขพร้อมเพย์:", value=user_data['promptpay'] if user_data['promptpay'] else "")
            db_bank = user_data['bank_name'] if user_data['bank_name'] else "-- เลือกธนาคาร --"
            bank_idx = BANK_LIST.index(db_bank) if db_bank in BANK_LIST else 0
            edit_bank_name = st.selectbox("แก้ไขธนาคาร:", BANK_LIST, index=bank_idx)
            edit_bank_acc = st.text_input("แก้ไขเลขบัญชีธนาคาร:", value=user_data['bank_account'] if user_data['bank_account'] else "")
            
            if st.button("อัปเดตข้อมูลบัญชี"):
                final_edit_bank = edit_bank_name if edit_bank_name != "-- เลือกธนาคาร --" else ""
                conn = get_db_connection()
                conn.execute("UPDATE all_users SET promptpay = ?, bank_name = ?, bank_account = ? WHERE name = ?", 
                             (edit_pp, final_edit_bank, edit_bank_acc, target_user))
                conn.commit(); conn.close()
                st.success(f"💾 อัปเดตข้อมูลบัญชีของ '{target_user}' เรียบร้อยแล้ว!")
                time.sleep(1)
                st.rerun()
        else:
            st.caption("ยังไม่มีสมาชิกในระบบ")

st.sidebar.markdown("---")
new_trip_name = st.sidebar.text_input("➕ สร้างทริปใหม่:").strip()
if st.sidebar.button("บันทึกทริป"):
    if new_trip_name:
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO trips (name, status) VALUES (?, 0)", (new_trip_name,))
            conn.commit(); conn.close()
            st.success(f"✈️ สร้างทริปใหม่ '{new_trip_name}' สำเร็จ!")
            time.sleep(1)
            st.rerun()
        except: st.sidebar.error("❌ ชื่อทริปซ้ำ")

# --- ส่วนถังขยะ ---
conn = get_db_connection()
with st.sidebar.expander("🗑️ ถังขยะ"):
    deleted_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
    if not deleted_trips:
        st.caption("ไม่มีรายการในถังขยะ")
    else:
        for dt in deleted_trips:
            c1, c2 = st.columns([1.5, 1.5])
            c1.write(dt['name'])
            sub_c1, sub_c2 = c2.columns(2)
            if sub_c1.button("กู้คืน", key=f"res_{dt['id']}"):
                conn.execute("UPDATE trips SET status = 0 WHERE id = ?", (dt['id'],))
                conn.commit()
                st.toast(f"🔄 กู้คืนทริป '{dt['name']}' เรียบร้อย!")
                time.sleep(1)
                st.rerun()
            if sub_c2.button("ลบ", key=f"pdel_{dt['id']}"):
                conn.execute("DELETE FROM settlements WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM expenses WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM members WHERE trip_id = ?", (dt['id'],))
                conn.execute("DELETE FROM trips WHERE id = ?", (dt['id'],))
                conn.commit()
                st.toast(f"💥 ลบทริป '{dt['name']}' ถาวรแล้ว!")
                time.sleep(1)
                st.rerun()

active_trips_df = pd.read_sql_query("SELECT * FROM trips WHERE status = 0", conn)
active_trip_list = active_trips_df["name"].tolist() if not active_trips_df.empty else []

if not active_trip_list:
    st.title("✈️ Trip Expense Splitter Pro")
    st.info("กรุณาสร้างทริปใหม่ หรือกู้คืนจากถังขยะที่เมนูซ้ายมือ")
    st.stop()

st.sidebar.markdown("---")
current_trip = st.sidebar.selectbox("🗺️ เลือกทริป:", active_trip_list)
trip_id = conn.execute("SELECT id FROM trips WHERE name = ? AND status = 0", (current_trip,)).fetchone()["id"]

# ====== ส่วนแก้ไขชื่อทริปปัจจุบัน ======
with st.sidebar.expander("✏️ แก้ไขชื่อทริปปัจจุบัน"):
    rename_input = st.text_input("เปลี่ยนชื่อทริปเป็น:", value=current_trip).strip()
    if st.button("💾 ยืนยันเปลี่ยนชื่อ"):
        if rename_input and rename_input != current_trip:
            try:
                conn_rename = get_db_connection()
                conn_rename.execute("UPDATE trips SET name = ? WHERE id = ?", (rename_input, trip_id))
                conn_rename.commit()
                conn_rename.close()
                st.success(f"✏️ เปลี่ยนชื่อทริปเป็น '{rename_input}' เรียบร้อย!")
                time.sleep(1)
                st.rerun()
            except:
                st.error("❌ ชื่อทริปนี้ซ้ำกับทริปอื่นที่มีอยู่")
        elif not rename_input:
            st.error("⚠️ กรุณากรอกชื่อทริป")

if st.sidebar.button("🗑️ ย้ายทริปลงถังขยะ"):
    conn.execute("UPDATE trips SET status = 1 WHERE id = ?", (trip_id,))
    conn.commit()
    st.toast(f"🗑️ ย้ายทริป '{current_trip}' ลงถังขยะแล้ว")
    time.sleep(1)
    st.rerun()

st.sidebar.subheader(f"👥 สมาชิก: {current_trip}")
all_users_list = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_users = [u for u in all_users_list if u not in existing_members]

selected_u = st.sidebar.selectbox("เพิ่มเพื่อน:", ["-- เลือก --"] + available_users)
if st.sidebar.button("ดึงเข้าทริป"):
    if selected_u != "-- เลือก --":
        conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
        conn.commit()
        st.toast(f"➕ ดึง {selected_u} เข้าสู่ทริปแล้ว!")
        time.sleep(1)
        st.rerun()
conn.close()

# --- 4. Main UI ---
if not existing_members:
    st.title(f"✈️ ข้อมูลทริป: {current_trip}")
    st.warning("กรุณาเลือกสมาชิกเข้าทริปก่อน")
    st.stop()

st.title(f"✈️ ข้อมูลทริป: {current_trip}")
tab1, tab2, tab3 = st.tabs(["📝 สร้างบิลใหม่", "📊 ประวัติบิล", "💰 สรุปเคลียร์เงินสมาชิก"])

with tab1:
    with st.form("add_bill", clear_on_submit=True):
        st.header("➕ เพิ่มบิลค่าใช้จ่าย")
        desc = st.text_input("รายการ:")
        amt = st.number_input("จำนวนเงิน:", min_value=0.0)
        payer = st.selectbox("คนสำรองจ่าย:", existing_members)
        st.write("คนหาร:")
        split_to = [m for m in existing_members if st.checkbox(m, value=True, key=f"add_{m}")]
        file = st.file_uploader("สลิป:", type=['jpg','png','jpeg'])
        if st.form_submit_button("💾 บันทึก", type="primary"):
            if desc and amt > 0 and split_to:
                blob = compress_image(file)
                conn = get_db_connection()
                conn.execute("INSERT INTO expenses (trip_id, description, amount, payer_name, split_members, image_blob) VALUES (?,?,?,?,?,?)",
                             (trip_id, desc, amt, payer, ",".join(split_to), blob))
                conn.commit(); conn.close()
                st.success(f"📝 บันทึกรายการบิล '{desc}' เรียบร้อยแล้ว!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("⚠️ กรุณากรอกข้อมูลรายการ จำนวนเงิน และคนหารให้ครบถ้วน")

with tab2:
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    conn.close()
    if not expenses: st.info("ยังไม่มีข้อมูล")
    else:
        for row in expenses:
            with st.expander(f"📌 {row['description']} | {row['amount']:,.2f} บาท"):
                c1, c2 = st.columns([1, 1.2])
                with c1:
                    if row['image_blob']: st.image(row['image_blob'], use_container_width=True)
                    else: st.caption("ไม่มีรูปสลิป")
                with c2:
                    with st.form(f"edit_{row['id']}"):
                        u_desc = st.text_input("รายการ:", value=row['description'])
                        u_amt = st.number_input("จำนวนเงิน:", value=row['amount'])
                        u_payer = st.selectbox("คนจ่าย:", existing_members, index=existing_members.index(row['payer_name']))
                        st.write("คนหาร:")
                        u_split_to = [m for m in existing_members if st.checkbox(m, value=(m in row['split_members'].split(",")), key=f"ed_{row['id']}_{m}")]
                        u_file = st.file_uploader("เปลี่ยนรูปสลิป:", type=['jpg','png','jpeg'])
                        delete_img = st.checkbox("🗑️ ลบรูปภาพสลิปออก", key=f"delimg_{row['id']}")
                        
                        if st.form_submit_button("💾 อัปเดต", type="primary"):
                            conn = get_db_connection()
                            if delete_img:
                                conn.execute("UPDATE expenses SET description=?, amount=?, payer_name=?, split_members=?, image_blob=NULL WHERE id=?", (u_desc, u_amt, u_payer, ",".join(u_split_to), row['id']))
                            elif u_file:
                                blob = compress_image(u_file)
                                conn.execute("UPDATE expenses SET description=?, amount=?, payer_name=?, split_members=?, image_blob=? WHERE id=?", (u_desc, u_amt, u_payer, ",".join(u_split_to), blob, row['id']))
                            else:
                                conn.execute("UPDATE expenses SET description=?, amount=?, payer_name=?, split_members=? WHERE id=?", (u_desc, u_amt, u_payer, ",".join(u_split_to), row['id']))
                            conn.commit(); conn.close()
                            st.success(f"🔄 อัปเดตข้อมูลบิล '{u_desc}' สำเร็จ!")
                            time.sleep(1)
                            st.rerun()
                    
                    if st.button("🗑️ ลบบิล", key=f"del_b_{row['id']}", type="secondary"):
                        conn = get_db_connection()
                        conn.execute("DELETE FROM expenses WHERE id=?", (row['id'],))
                        conn.commit(); conn.close()
                        st.warning(f"🗑️ ลบรายการบิลเรียบร้อยแล้ว!")
                        time.sleep(1)
                        st.rerun()

with tab3:
    st.header("🤝 สรุปยอด")
    conn = get_db_connection()
    expenses_rows = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    
    # ดึงข้อมูลบัญชีของสมาชิก
    user_profiles = {row['name']: {"promptpay": row['promptpay'], "bank_name": row['bank_name'], "bank_acc": row['bank_account']} 
                     for row in conn.execute("SELECT name, promptpay, bank_name, bank_account FROM all_users").fetchall()}
    conn.close()
    
    if not expenses_rows: 
        st.info("ยังไม่มีข้อมูล")
    else:
        net = {m: 0.0 for m in existing_members}
        for r in expenses_rows:
            net[r['payer_name']] += r['amount']
            s_list = r['split_members'].split(",")
            share = r['amount'] / len(s_list)
            for m in s_list: net[m] -= share
        
        c1, c2 = st.columns(2)
        c1.write("**🟢 คนที่ต้องได้รับคืน:**")
        for m, b in net.items():
            if b > 0.01: c1.success(f"{m}: {b:,.2f}")
        c2.write("**🔴 คนที่ต้องจ่าย:**")
        for m, b in net.items():
            if b < -0.01: c2.error(f"{m}: {abs(b):,.2f}")
        
        st.subheader("🚀 แผนการโอนเงิน (คลิกปุ่มขวาบนของเลขเพื่อคัดลอก)")
        debtors = [[m, b] for m, b in net.items() if b < -0.01]
        creditors = [[m, b] for m, b in net.items() if b > 0.01]
        final_tx = []
        
        while debtors and creditors:
            amt = min(abs(debtors[0][1]), creditors[0][1])
            debtor_name = debtors[0][0]
            creditor_name = creditors[0][0]
            
            # ดึงข้อมูลบัญชีผู้รับ (Creditor) ป้องกันกรณีค่าเป็น None ด้วยการใช้ or ""
            prof = user_profiles.get(creditor_name, {})
            pp = (prof.get("promptpay") or "").strip()
            b_name = (prof.get("bank_name") or "").strip()
            b_acc = (prof.get("bank_acc") or "").strip()
            
            # แสดงรายการนำทางผู้โอน
            st.markdown(f"💳 **{debtor_name}** โอนให้ 👉 **{creditor_name}** จำนวน **{amt:,.2f}** บาท")
            
            if pp or b_acc:
                col_pp, col_bank = st.columns(2)
                with col_pp:
                    if pp:
                        st.caption(f"📱 พร้อมเพย์ {creditor_name}")
                        st.code(pp, language="text")
                with col_bank:
                    if b_acc:
                        label = f"🏦 {b_name}" if b_name else "🏦 เลขบัญชี"
                        st.caption(f"{label} ของ {creditor_name}")
                        st.code(b_acc, language="text")
            else:
                st.warning(f"⚠️ {creditor_name} ยังไม่ได้บันทึกข้อมูลบัญชี")
            
            st.write("---")
            final_tx.append((debtor_name, creditor_name, amt))
            debtors[0][1] += amt; creditors[0][1] -= amt
            if abs(debtors[0][1]) < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)

        if st.button("🎯 บันทึกปิดทริป", type="primary"):
            conn = get_db_connection()
            conn.execute("DELETE FROM settlements WHERE trip_id = ?", (trip_id,))
            for t in final_tx: conn.execute("INSERT INTO settlements (trip_id, debtor, creditor, amount) VALUES (?,?,?,?)", (trip_id, t[0], t[1], t[2]))
            conn.commit(); conn.close()
            st.balloons()  # ใส่เอฟเฟกต์กระดาษโปรยเพื่อความฟินตอนปิดทริป
            st.success("🎯 บันทึกปิดทริปและเคลียร์ยอดเงินทั้งหมดสำเร็จเรียบร้อยแล้ว!")
            time.sleep(1.5)
            st.rerun()

        st.subheader("📋 ประวัติการเคลียร์")
        conn = get_db_connection()
        saved = pd.read_sql_query(f"SELECT debtor as 'จาก', creditor as 'ถึง', amount as 'จำนวน' FROM settlements WHERE trip_id = {trip_id}", conn)
        conn.close()
        if not saved.empty: st.table(saved)
