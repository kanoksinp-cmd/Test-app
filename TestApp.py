# 🛠️ ลดสัดส่วนคอลัมน์การแสดงผลลง 50% ให้กระชับขึ้น
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.markdown(f"**💰 ยอด:** {row['amount']:,.2f} ฿")
                    st.markdown(f"**👤 คนจ่าย:** {row['payer_name']}")
                    st.caption(f"👥 คนหาร: {row['split_members']}")
                    
                    m_list = row['split_members'].split(",")
                    share = row['amount'] / len(m_list) if m_list else 0
                    st.caption(f"💸 ตกคนละ {share:,.2f} ฿")
                    
                with c2:
                    if row['image_blob']:
                        # 🖼️ ลดขนาดการแสดงผลรูปภาพสลิปลงครึ่งหนึ่ง (ใช้ฟังก์ชันคุม Width ใน Container ขนาดเล็ก)
                        with st.container(border=True):
                            st.image(row['image_blob'], caption="สลิปบิล", width=120)
                    else:
                        st.caption("ไม่มีสลิป")
                        
                    # 🗑️ ปรับปุ่มลบให้เป็นปุ่มเล็ก (Small)
                    if st.button("🗑️ ลบ", key=f"del_exp_{row['id']}", type="secondary", icon="🗑️"):
                        conn_del = get_db_connection()
                        conn_del.execute("DELETE FROM expenses WHERE id = ?", (row['id'],))
                        conn_del.commit()
                        conn_del.close()
                        st.toast("🗑️ ลบแล้ว")
                        time.sleep(0.2) # ⏱️ ลดเวลาดีเลย์ลงครึ่งหนึ่ง (0.5s -> 0.2s) เพื่อความไว
                        st.rerun()

with tab3:
    st.subheader("💰 สรุปยอดเคลียร์เงิน")
    
    conn = get_db_connection()
    all_expenses = conn.execute("SELECT * FROM expenses WHERE trip_id = ?", (trip_id,)).fetchall()
    user_profiles = {r['name']: {"promptpay": r['promptpay'], "bank_name": r['bank_name'], "bank_account": r['bank_account']} 
                     for r in conn.execute("SELECT * FROM all_users").fetchall()}
    conn.close()
    
    # 🧮 คำนวณหนี้สินสุทธิ
    balances = {m: 0.0 for m in existing_members}
    for row in all_expenses:
        payer = row['payer_name']
        split_m = row['split_members'].split(",")
        if not split_m: continue
        share = row['amount'] / len(split_m)
        if payer in balances: balances[payer] += row['amount']
        for m in split_m:
            if m in balances: balances[m] -= share

    # 📊 แสดงผลสถานะกระเป๋าเงินแบบขนาดมินิ
    st.write("**📊 ดุลเงินรายคน:**")
    b_cols = st.columns(len(existing_members))
    for idx, member in enumerate(existing_members):
        bal = balances[member]
        with b_cols[idx]:
            # 📉 ใช้ st.caption และข้อความปกติแทน st.metric ขนาดใหญ่เพื่อประหยัดพื้นที่ลง 50%
            if bal > 0:
                st.markdown(f"**{member}**\n<span style='color:green'>+{bal:,.2f} ฿</span>", unsafe_allow_html=True)
            elif bal < 0:
                st.markdown(f"**{member}**\n<span style='color:red'>{bal:,.2f} ฿</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"**{member}**\n<span style='color:gray'>0.00 ฿</span>", unsafe_allow_html=True)

    st.markdown("---")
    st.write("**🤝 รายการจับคู่โอนคืน (ย่อกระชับ):**")
    
    debtors = [[m, bal] for m, bal in balances.items() if bal < -0.01]
    creditors = [[m, bal] for m, bal in balances.items() if bal > 0.01]
    debtors.sort(key=lambda x: x[1])
    creditors.sort(key=lambda x: x[1], reverse=True)
    
    suggested_trans = []
    while debtors and creditors:
        d_name, d_bal = debtors[0]
        c_name, c_bal = creditors[0]
        amount_to_pay = min(abs(d_bal), c_bal)
        suggested_trans.append({"from": d_name, "to": c_name, "amount": amount_to_pay})
        debtors[0][1] += amount_to_pay
        creditors[0][1] -= amount_to_pay
        if abs(debtors[0][1]) < 0.01: debtors.pop(0)
        if abs(creditors[0][1]) < 0.01: creditors.pop(0)

    if not suggested_trans:
        st.success("🎉 เคลียร์ครบยอดหมดแล้ว!")
    else:
        for idx, trans in enumerate(suggested_trans):
            f_user = trans["from"]
            t_user = trans["to"]
            t_amt = trans["amount"]
            
            # 📦 ปรับเปลี่ยนโครงสร้าง Layout การโอนเงินให้เหลือพื้นที่แถวแคบลงครึ่งหนึ่ง
            with st.container():
                c1, c2 = st.columns([3, 2])
                with c1:
                    st.markdown(f"🔴 **{f_user}** โอนให้ 🟢 **{t_user}** = **{t_amt:,.2f} ฿**")
                    p_info = user_profiles.get(t_user, {})
                    pp_num = p_info.get("promptpay", "")
                    if pp_num:
                        st.caption(f"💳 พร้อมเพย์: {pp_num}")
                
                with c2:
                    sub_c1, sub_c2 = st.columns(2)
                    with sub_c1:
                        if pp_num:
                            qr_url = f"https://promptpay.io/{pp_num}/{t_amt:.2f}.png"
                            with st.popover("📱 QR", help="สแกนจ่าย"):
                                # 📱 จำกัดขนาดภาพ QR Code ลงเหลือ 150px
                                st.image(qr_url, width=150)
                    with sub_c2:
                        if st.button("🔔 เตือน", key=f"bz_{idx}", help="ยิงทวงเงิน"):
                            conn_buzz = get_db_connection()
                            buzz_msg = f"📢 ทวงยอดทริป '{current_trip}': โอนให้ {t_user} จำนวน {t_amt:,.2f} ฿ ด้วยนะชิ้น"
                            conn_buzz.execute(
                                "INSERT INTO notifications (trip_id, to_user, from_user, message, is_auto, is_read, timestamp) VALUES (?, ?, 'ระบบสรุปยอด', ?, 1, 0, datetime('now', 'localtime'))",
                                (trip_id, f_user, buzz_msg)
                            )
                            conn_buzz.commit()
                            conn_buzz.close()
                            st.toast("🚀 ส่งใบเตือนแล้ว")
            st.markdown("<div style='margin: 2px 0;'></div>", unsafe_allow_html=True)
