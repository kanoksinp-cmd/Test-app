import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# 1. ตั้งค่าพื้นฐาน
st.set_page_config(page_title="Trip Splitter Pro", layout="wide")
st_autorefresh(interval=3000, limit=None, key="trip_app_refresh") # รีเฟรชทุก 3 วินาที

DB_FILE = "trip_database.db"

# 2. ฟังก์ชันจัดการฐานข้อมูล
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# [ส่วนการ Init DB และจัดการรูปภาพเหมือนเดิม...]
# (เพื่อความกระชับ ผมจะข้ามไปจุดที่ต้องแก้ Error และ Tab 3 เลยนะครับ)

# --- จุดที่แก้ไข Error (Line 558 เดิม) ---
# เปลี่ยนจาก rows=2 เป็น height=80 หรือไม่ต้องใส่ก็ได้
def draw_chat_input(partner, my_name, trip_id):
    with st.form(key=f"new_chat_form_{partner}", clear_on_submit=True):
        # แก้ไขตรงนี้: ลบ rows=2 ออก หรือเปลี่ยนเป็น height
        notif_msg = st.text_area("ข้อความ:", placeholder="ทักทายที่นี่...", key=f"input_{partner}", height=70)
        if st.form_submit_button("🚀 ส่ง", use_container_width=True):
            if notif_msg.strip():
                conn = get_db_connection()
                conn.execute(
                    "INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, ?, ?, 0, 0, datetime('now', 'localtime'))",
                    (trip_id, partner, my_name, notif_msg.strip())
                )
                conn.commit()
                conn.close()
                st.rerun()

# 💰 ====== TAB 3: ระบบคำนวณยอดเงินเคลียร์บิล (เพิ่มใหม่ให้สมบูรณ์) ======
with tab3:
    st.header("💰 สรุปยอดค้างชำระ")
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    members = [row["name"] for row in conn.execute("SELECT name FROM members WHERE trip_id = ?", (trip_id,)).fetchall()]
    conn.close()

    if not expenses:
        st.info("ยังไม่มีค่าใช้จ่ายเพื่อคำนวณ")
    else:
        # คำนวณยอดสุทธิของแต่ละคน (Net Balance)
        balances = {m: 0.0 for m in members}
        for exp in expenses:
            payer = exp['payer_name']
            amt = exp['amount']
            split_list = exp['split_members'].split(",")
            share = amt / len(split_list)
            
            # คนจ่ายได้เงินคืน
            if payer in balances:
                balances[payer] += amt
            
            # ทุกคนที่มีชื่อหารต้องเสียเงิน
            for m in split_list:
                if m in balances:
                    balances[m] -= share

        # แสดงตารางสรุปเบื้องต้น (ขนาดเล็กลงครึ่งหนึ่ง)
        st.subheader("📊 ยอดรวมรายบุคคล")
        summary_data = []
        for m, bal in balances.items():
            status = "🟢 ได้คืน" if bal > 0 else "🔴 ต้องจ่าย" if bal < 0 else "⚪ เจ๊า"
            summary_data.append({"สมาชิก": m, "ยอดสุทธิ": f"{bal:,.2f}", "สถานะ": status})
        st.table(pd.DataFrame(summary_data))

        st.divider()

        # คำนวณการโอนเงิน (ใครต้องโอนให้ใคร)
        st.subheader("💸 รายการที่ต้องโอน")
        debtors = [[m, bal] for m, bal in balances.items() if bal < 0]
        creditors = [[m, bal] for m, bal in balances.items() if bal > 0]

        debtors.sort(key=lambda x: x[1])
        creditors.sort(key=lambda x: x[1], reverse=True)

        settlements = []
        i, j = 0, 0
        while i < len(debtors) and j < len(creditors):
            d_name, d_bal = debtors[i]
            c_name, c_bal = creditors[j]
            
            amount = min(abs(d_bal), c_bal)
            if amount > 0.01:
                settlements.append((d_name, c_name, amount))
            
            debtors[i][1] += amount
            creditors[j][1] -= amount
            
            if abs(debtors[i][1]) < 0.01: i += 1
            if abs(creditors[j][1]) < 0.01: j += 1

        if not settlements:
            st.success("✅ เคลียร์ยอดครบถ้วนแล้ว!")
        else:
            for d, c, a in settlements:
                col1, col2 = st.columns([3, 1])
                col1.warning(f"🔸 **{d}** ต้องโอนให้ **{c}** เป็นเงิน **{a:,.2f}** บาท")
                if col2.button("แจ้งเตือน 🔔", key=f"notif_{d}_{c}_{a}"):
                    conn = get_db_connection()
                    msg = f"🔔 แจ้งเตือนจากระบบ: คุณมีค้างโอนให้ [{c}] จำนวน {a:,.2f} บาท ในทริป {current_trip} รบกวนตรวจสอบด้วยน้า 🙏"
                    conn.execute("INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto) VALUES (?, ?, 'ระบบสรุปยอด', ?, 1)",
                                 (trip_id, d, msg))
                    conn.commit(); conn.close()
                    st.toast(f"ส่งคำขอเก็บเงินไปที่ {d} แล้ว")
