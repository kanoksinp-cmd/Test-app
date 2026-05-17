import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
import urllib.parse
from datetime import datetime

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
    
    # อัปเดตโครงสร้างตารางหลัก (all_users)
    cursor.execute("PRAGMA table_info(all_users)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'promptpay' not in columns:
        cursor.execute("ALTER TABLE all_users ADD COLUMN promptpay TEXT")
    if 'bank_name' not in columns:
        cursor.execute("ALTER TABLE all_users ADD COLUMN bank_name TEXT")
    if 'bank_account' not in columns:
        cursor.execute("ALTER TABLE all_users ADD COLUMN bank_account TEXT")
        
    # อัปเดตโครงสร้างตารางรองรับวันที่ (trips)
    cursor.execute("PRAGMA table_info(trips)")
    trip_columns = [row[1] for row in cursor.fetchall()]
    if 'trip_date' not in trip_columns:
        cursor.execute("ALTER TABLE trips ADD COLUMN trip_date TEXT")
        
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
            
            edit_name = st.text_input("แก้ไขชื่อสมาชิก:", value=user_data['name']).strip()
            edit_pp = st.text_input("แก้ไขเลขพร้อมเพย์:", value=user_data['promptpay'] if user_data['promptpay'] else "")
            db_bank = user_data['bank_name'] if user_data['bank_name'] else "-- เลือกธนาคาร --"
            bank_idx = BANK_LIST.index(db_bank) if db_bank in BANK_LIST else 0
            edit_bank_name = st.selectbox("แก้ไขธนาคาร:", BANK_LIST, index=bank_idx)
            edit_bank_acc = st.text_input("แก้ไขเลขบัญชีธนาคาร:", value=user_data['bank_account'] if user_data['bank_account'] else "")
            
            if st.button("อัปเดตข้อมูลบัญชี"):
                if not edit_name:
                    st.error("⚠️ ชื่อสมาชิกต้องไม่เป็นค่าว่าง")
                else:
                    try:
                        final_edit_bank = edit_bank_name if edit_bank_name != "-- เลือกธนาคาร --" else ""
                        conn = get_db_connection()
                        conn.execute("UPDATE all_users SET name = ?, promptpay = ?, bank_name = ?, bank_account = ? WHERE name = ?", 
                                     (edit_name, edit_pp, final_edit_bank, edit_bank_acc, target_user))
                        
                        if edit_name != target_user:
                            conn.execute("UPDATE members SET name = ? WHERE name = ?", (edit_name, target_user))
                            conn.execute("UPDATE expenses SET payer_name = ? WHERE payer_name = ?", (edit_name, target_user))
                            conn.execute("UPDATE settlements SET debtor = ? WHERE debtor = ?", (edit_name, target_user))
                            conn.execute("UPDATE settlements SET creditor = ? WHERE creditor = ?", (edit_name, target_user))
                            
                        conn.commit(); conn.close()
                        st.success(f"💾 อัปเดตข้อมูลบัญชีของ '{edit_name}' เรียบร้อยแล้ว!")
                        time.sleep(1)
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("❌ ชื่อนี้ซ้ำกับสมาชิกท่านอื่นในระบบ")
        else:
            st.caption("ยังไม่มีสมาชิกในระบบ")

st.sidebar.markdown("---")
# ====== อัปเดตส่วนสร้าง Event ให้มีปฏิทินเลือกวันที่ ======
st.sidebar.subheader("➕ สร้าง Event ใหม่")
new_trip_name = st.sidebar.text_input("ชื่อ Event:").strip()
new_trip_date = st.sidebar.date_input("วันที่จัด Event:", value=datetime.today())

if st.sidebar.button("สร้าง Event ใหม่"):
    if new_trip_name:
        try:
            conn = get_db_connection()
            # แปลงวันที่เป็น String format YYYY-MM-DD เพื่อบันทึกลง SQLite
            date_str = new_trip_date.strftime("%Y-%m-%d")
            conn.execute("INSERT INTO trips (name, status, trip_date) VALUES (?, 0, ?)", (new_trip_name, date_str))
            conn.commit(); conn.close()
            st.success(f"✈️ สร้าง Event ใหม่ '{new_trip_name}' สำเร็จ!")
            time.sleep(1)
            st.rerun()
        except: st.sidebar.error("❌ ชื่อ Event ซ้ำ")
    else:
        st.sidebar.error("⚠️ กรุณากรอกชื่อ Event")

# --- ส่วนถังขยะ ---
conn = get_db_connection()
with st.sidebar.expander("🗑️ ถังขยะ"):
    deleted_trips = conn.execute("SELECT * FROM trips WHERE status = 1").fetchall()
    if not deleted_trips:
        st.caption("ไม่มีรายการในถังขยะ")
    else:
        for dt in deleted_trips:
            c1, c2 = st.columns([1.5, 1.5])
            display_deleted_name = f"{dt['name']} ({dt['trip_date']})" if dt['trip_date'] else dt['name']
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

# กำหนดสไตล์ชื่อทริปตอนให้เลือกใน dropdown ให้โชว์วันที่ด้วยเพื่อความง่าย
if not active_trips_df.empty:
    active_trips_df['display_name'] = active_trips_df.apply(
        lambda r: f"{r['name']} 📅 ({r['trip_date']})" if r['trip_date'] else r['name'], axis=1
    )
    active_trip_display_list = active_trips_df["display_name"].tolist()
else:
    active_trip_display_list = []

if not active_trip_display_list:
    st.title("✈️ Trip Expense Splitter Pro")
    st.info("กรุณาสร้างEventใหม่ หรือกู้คืนจากถังขยะที่เมนูซ้ายมือ")
    st.stop()

st.sidebar.markdown("---")
selected_display_trip = st.sidebar.selectbox("🗺️ เลือกEvent:", active_trip_display_list)

# ค้นหาชื่อทริปและ ID ตัวจริงจากตารางอ้างอิงของชื่อที่เลือกใน Dropdown
matched_trip = active_trips_df[active_trips_df['display_name'] == selected_display_trip].iloc[0]
current_trip = matched_trip['name']
trip_id = int(matched_trip['id'])
current_trip_date = matched_trip['trip_date']

# ====== ส่วนแก้ไขชื่อและวันที่ Event ปัจจุบัน ======
with st.sidebar.expander("✏️ แก้ไขข้อมูล Event ปัจจุบัน"):
    rename_input = st.text_input("เปลี่ยนชื่อ Event เป็น:", value=current_trip).strip()
    
    # ดึงวันดั้งเดิมมาใส่ในตัวแปร Default
    default_date = datetime.strptime(current_trip_date, "%Y-%m-%d") if current_trip_date else datetime.today()
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

st.sidebar.subheader(f"👥 สมาชิก: {current_trip}")
all_users_list = [row["name"] for row in conn.execute("SELECT name FROM all_users").fetchall()]
existing_members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
available_users = [u for u in all_users_list if u not in existing_members]

if existing_members:
    for member in existing_members:
        m_col1, m_col2 = st.sidebar.columns([4, 1])
        m_col1.caption(f"• {member}")
        if m_col2.button("❌", key=f"remove_mem_{member}", help=f"ถอด {member} ออกจาก Event นี้"):
            conn.execute("DELETE FROM members WHERE trip_id = ? AND name = ?", (trip_id, member))
            conn.commit()
            st.toast(f"🗑️ ถอด {member} ออกจาก Event เรียบร้อย")
            time.sleep(1)
            st.rerun()

selected_u = st.sidebar.selectbox("เพิ่มเพื่อน:", ["-- เลือก --"] + available_users)
if st.sidebar.button("ดึงเข้าEvent"):
    if selected_u != "-- เลือก --":
        conn.execute("INSERT INTO members (trip_id, name) VALUES (?, ?)", (trip_id, selected_u))
        conn.commit()
        st.toast(f"➕ ดึง {selected_u} เข้าสู่ Event แล้ว!")
        time.sleep(1)
        st.rerun()
conn.close()

# --- 4. Main UI ---
if not existing_members:
    st.title(f"✈️ Event: {current_trip}")
    if current_trip_date:
        st.caption(f"📅 วันที่จัดทริป: {current_trip_date}")
    st.warning("กรุณาเลือกสมาชิกเข้า Event ก่อน")
    st.stop()

st.title(f"✈️ ข้อมูล Event: {current_trip}")
if current_trip_date:
    st.subheader(f"📅 วันที่จัด: {current_trip_date}")

tab1, tab2, tab3 = st.tabs(["📝 สร้างบิลใหม่", "📊 ประวัติบันทึกบิล", "💰 สรุปเคลียร์เงินสมาชิก"])

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
                        current_payer = row['payer_name']
                        payer_options = existing_members if current_payer in existing_members else existing_members + [current_payer]
                        u_payer = st.selectbox("คนจ่าย:", payer_options, index=payer_options.index(current_payer))
                        
                        st.write("คนหาร:")
                        u_split_to = [m for m in payer_options if st.checkbox(m, value=(m in row['split_members'].split(",")), key=f"ed_{row['id']}_{m}")]
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
    
    user_profiles = {row['name']: {"promptpay": row['promptpay'], "bank_name": row['bank_name'], "bank_acc": row['bank_account']} 
                     for row in conn.execute("SELECT name, promptpay, bank_name, bank_account FROM all_users").fetchall()}
    conn.close()
    
    if not expenses_rows: 
        st.info("ยังไม่มีข้อมูล")
    else:
        all_involved_members = set(existing_members)
        for r in expenses_rows:
            all_involved_members.add(r['payer_name'])
            all_involved_members.update(r['split_members'].split(","))
            
        net = {m: 0.0 for m in all_involved_members}
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
            
            prof = user_profiles.get(creditor_name, {})
            pp = (prof.get("promptpay") or "").strip()
            b_name = (prof.get("bank_name") or "").strip()
            b_acc = (prof.get("bank_acc") or "").strip()
            
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

        # ================= ส่วนระบบส่งข้อมูลเข้า LINE =================
        st.subheader("📲 ส่งสรุปยอดเข้า LINE")
        
        line_msg = f"📊 สรุปยอดค่าใช้จ่ายทริป: {current_trip}\n"
        if current_trip_date:
            line_msg += f"📅 วันที่: {current_trip_date}\n"
        line_msg += "-------------------------------\n"
        for d_n, c_n, a_m in final_tx:
            line_msg += f"💳 {d_n} โอนให้ 👉 {c_n} = {a_m:,.2f} บาท\n"
            prof = user_profiles.get(c_n, {})
            pp = (prof.get("promptpay") or "").strip()
            b_name = (prof.get("bank_name") or "").strip()
            b_acc = (prof.get("bank_acc") or "").strip()
            if pp: line_msg += f"   • พร้อมเพย์: {pp}\n"
            if b_acc: line_msg += f"   • ธนาคาร: {b_name} ({b_acc})\n"
            line_msg += "\n"
        line_msg += "-------------------------------\n"
        line_msg += "ฝากเคลียร์เงินกันด้วยน้าาา ✈️🥳"

        encoded_msg = urllib.parse.quote(line_msg)
        line_share_url = f"https://line.me/R/msg/text/?{encoded_msg}"

        st.markdown(
            f'''
            <a href="{line_share_url}" target="_blank" style="text-decoration: none;">
                <button style="
                    background-color: #06C755; 
                    color: white; 
                    border: none; 
                    padding: 12px 20px; 
                    font-size: 16px; 
                    font-weight: bold;
                    border-radius: 8px; 
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    width: 100%;
                    justify-content: center;
                    box-shadow: 0px 4px 6px rgba(0,0,0,0.1);
                ">
                    💬 ส่งแผนการโอนเงินไปที่แอป LINE
                </button>
            </a>
            ''', 
            unsafe_allow_html=True
        )
        st.write("---")
        # ============================================================

        if st.button("🎯 บันทึกปิด Event", type="primary"):
            conn = get_db_connection()
            conn.execute("DELETE FROM settlements WHERE trip_id = ?", (trip_id,))
            for t in final_tx: conn.execute("INSERT INTO settlements (trip_id, debtor, creditor, amount) VALUES (?,?,?,?)", (trip_id, t[0], t[1], t[2]))
            conn.commit(); conn.close()
            st.balloons()
            st.success("🎯 บันทึกปิดEventและเคลียร์ยอดเงินทั้งหมดสำเร็จเรียบร้อยแล้ว!")
            time.sleep(1.5)
            st.rerun()

        st.subheader("📋 ประวัติการเคลียร์")
        conn = get_db_connection()
        saved = pd.read_sql_query(f"SELECT debtor as 'จาก', creditor as 'ถึง', amount as 'จำนวน' FROM settlements WHERE trip_id = {trip_id}", conn)
        conn.close()
        if not saved.empty: st.table(saved)
