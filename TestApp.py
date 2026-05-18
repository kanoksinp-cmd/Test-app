import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os

# --- การตั้งค่าฐานข้อมูล ---
def init_db():
    conn = sqlite3.connect('expense_tracker.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            type TEXT,
            category TEXT,
            amount REAL,
            description TEXT,
            image_path TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_transaction(date, t_type, category, amount, description, image_path):
    conn = sqlite3.connect('expense_tracker.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO transactions (date, type, category, amount, description, image_path)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (date, t_type, category, amount, description, image_path))
    conn.commit()
    conn.close()

# --- ส่วนหน้าจอหลัก (UI) ---
def main():
    st.set_page_config(page_title="Expense Tracker Studio", layout="wide")
    init_db()

    st.title("📊 Expense Tracker & Document Management")
    
    # Sidebar สำหรับเมนูควบคุม
    menu = ["Dashboard", "Add Transaction", "Settings"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Add Transaction":
        st.subheader("เพิ่มรายการใหม่")
        
        col1, col2 = st.columns(2)
        with col1:
            date = st.date_input("วันที่", datetime.now())
            t_type = st.selectbox("ประเภท", ["รายรับ", "รายจ่าย"])
            category = st.text_input("หมวดหมู่ (เช่น อาหาร, เดินทาง, อุปกรณ์)")
        
        with col2:
            amount = st.number_input("จำนวนเงิน", min_value=0.0, format="%.2f")
            description = st.text_area("หมายเหตุ")
            uploaded_file = st.file_uploader("อัปโหลดใบเสร็จ (ถ้ามี)", type=['jpg', 'png', 'jpeg'])

        if st.button("บันทึกข้อมูล"):
            image_path = None
            if uploaded_file:
                # บันทึกไฟล์ภาพลงเครื่อง
                if not os.path.exists("uploads"):
                    os.makedirs("uploads")
                image_path = os.path.join("uploads", uploaded_file.name)
                with open(image_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
            
            add_transaction(date.strftime("%Y-%m-%d"), t_type, category, amount, description, image_path)
            st.success("บันทึกรายการเรียบร้อยแล้ว!")

    elif choice == "Dashboard":
        st.subheader("ภาพรวมข้อมูล")
        
        conn = sqlite3.connect('expense_tracker.db')
        df = pd.read_sql_query("SELECT * FROM transactions", conn)
        conn.close()

        if not df.empty:
            # สรุปยอด
            total_income = df[df['type'] == 'รายรับ']['amount'].sum()
            total_expense = df[df['type'] == 'รายจ่าย']['amount'].sum()
            balance = total_income - total_expense

            m1, m2, m3 = st.columns(3)
            m1.metric("รายรับทั้งหมด", f"{total_income:,.2f}")
            m2.metric("รายจ่ายทั้งหมด", f"{total_expense:,.2f}")
            m3.metric("คงเหลือ", f"{balance:,.2f}")

            st.divider()
            st.dataframe(df.sort_values(by='date', ascending=False), use_container_width=True)
            
            # กราฟแสดงผลเบื้องต้น
            st.bar_chart(df.groupby('category')['amount'].sum())
        else:
            st.info("ยังไม่มีข้อมูลบันทึกในระบบ")

if __name__ == '__main__':
    main()
