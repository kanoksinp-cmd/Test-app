import streamlit as st
import pandas as pd
import sqlite3
import io
from PIL import Image
import time
import urllib.parse
from datetime import datetime
from contextlib import contextmanager
from streamlit_autorefresh import st_autorefresh

# ──────────────────────────────────────────────
# 1. ตั้งค่าหน้าจอ
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Trip Expense Splitter",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS สวยงาม
st.markdown("""
<style>
    /* Main background */
    .stApp { background: #F8F9FA; }
    
    /* Sidebar */
    section[data-testid="stSidebar"] { background: #1E1E2E; }
    section[data-testid="stSidebar"] * { color: #CDD6F4 !important; }
    section[data-testid="stSidebar"] .stButton button {
        background: #313244; border: 1px solid #45475A;
        color: #CDD6F4 !important; border-radius: 8px; transition: all 0.2s;
    }
    section[data-testid="stSidebar"] .stButton button:hover {
        background: #45475A; border-color: #89B4FA;
    }
    section[data-testid="stSidebar"] hr { border-color: #313244; }

    /* Cards */
    .expense-card {
        background: white; border-radius: 12px; padding: 16px 20px;
        margin: 8px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.07);
        border-left: 4px solid #89B4FA;
    }
    .summary-card {
        background: white; border-radius: 12px; padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07); margin: 8px 0;
    }
    .transfer-row {
        background: #F0F4FF; border-radius: 10px; padding: 14px 18px;
        margin: 10px 0; border: 1px solid #D6E4FF;
        display: flex; align-items: center; gap: 10px;
    }
    .badge-green { background:#D1FAE5; color:#065F46; padding:2px 10px;
        border-radius:20px; font-size:13px; font-weight:600; }
    .badge-red { background:#FEE2E2; color:#991B1B; padding:2px 10px;
        border-radius:20px; font-size:13px; font-weight:600; }

    /* Tabs */
    .stTabs [data-baseweb="tab"] {
        font-size: 15px; font-weight: 600; padding: 10px 20px;
    }
    .stTabs [aria-selected="true"] { border-bottom: 3px solid #89B4FA; }

    /* Forms */
    .stTextInput input, .stNumberInput input, .stSelectbox select {
        border-radius: 8px !important;
    }
    .stForm { background: white; padding: 20px; border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
</style>
""", unsafe_allow_html=True)

# รีเฟรชอัตโนมัติทุก 5 วินาที (ลดจาก 1 วินาที เพื่อลด lag ขณะพิมพ์)
st_autorefresh(interval=5000, limit=None, key="trip_app_live_refresh")

DB_FILE = "trip_database.db"

BANK_LIST = [
    "-- เลือกธนาคาร --",
    "กสิกรไทย (KBank)", "ไทยพาณิชย์ (SCB)", "กรุงไทย (KTB)",
    "กรุงเทพ (BBL)", "กรุงศรีอยุธยา (BAY)", "ทหารไทยธนชาต (TTB)",
    "ออมสิน (GSB)", "ธ.ก.ส.", "ยูโอบี (UOB)"
]

# ──────────────────────────────────────────────
# 2. ฐานข้อมูล — ใช้ context manager ป้องกัน connection leak
# ──────────────────────────────────────────────
@contextmanager
def db_conn():
    """Context manager ที่รับประกันว่า connection จะถูกปิดเสมอ"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def safe_has_date(val) -> bool:
    """ตรวจสอบว่า trip_date มีค่าจริงหรือไม่ (ป้องกัน pd.isna crash)"""
    if val is None:
        return False
    s = str(val).strip()
    return bool(s) and s.lower() not in ("none", "nan", "nat", "")

def init_db():
    with db_conn() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS all_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, status INTEGER DEFAULT 0)')
        conn.execute('CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, name TEXT, FOREIGN KEY(trip_id) REFERENCES trips(id))')
        conn.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, description TEXT, amount REAL, payer_name TEXT, split_members TEXT, image_blob BLOB, FOREIGN KEY(trip_id) REFERENCES trips(id))')
        conn.execute('CREATE TABLE IF NOT EXISTS settlements (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER, debtor TEXT, creditor TEXT, amount REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(trip_id) REFERENCES trips(id))')
        conn.execute('CREATE TABLE IF NOT EXISTS online_status (name TEXT PRIMARY KEY, last_seen DATETIME)')
        conn.execute('''CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id INTEGER,
            to_user TEXT, from_user TEXT, message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_auto INTEGER DEFAULT 0, is_read INTEGER DEFAULT 0,
            FOREIGN KEY(trip_id) REFERENCES trips(id))''')

        # Migration: เพิ่มคอลัมน์ที่อาจยังไม่มีในฐานข้อมูลเก่า
        for col, definition in [
            ("all_users", [("promptpay", "TEXT"), ("bank_name", "TEXT"), ("bank_account", "TEXT")]),
            ("trips",     [("trip_date", "TEXT")]),
            ("notifications", [("is_auto", "INTEGER DEFAULT 0"), ("is_read", "INTEGER DEFAULT 0"),
                               ("timestamp", "DATETIME DEFAULT CURRENT_TIMESTAMP")]),
        ]:
            existing = [r[1] for r in conn.execute(f"PRAGMA table_info({col})").fetchall()]
            for col_name, col_def in definition:
                if col_name not in existing:
                    conn.execute(f"ALTER TABLE {col} ADD COLUMN {col_name} {col_def}")

def compress_image(uploaded_file):
    if uploaded_file is None:
        return None
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.thumbnail((800, 800))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()

def update_online_heartbeat(username: str):
    if not username:
        return
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO online_status (name, last_seen) VALUES (?, datetime('now','localtime')) "
            "ON CONFLICT(name) DO UPDATE SET last_seen = datetime('now','localtime')",
            (username,)
        )

def get_online_users() -> list:
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT name FROM online_status WHERE last_seen >= datetime('now','localtime','-30 seconds')"
        ).fetchall()
    return [r["name"] for r in rows]

# ──────────────────────────────────────────────
# 3. เริ่มต้นระบบ
# ──────────────────────────────────────────────
init_db()

if "current_online_user" not in st.session_state:
    st.session_state["current_online_user"] = None

current_user = st.session_state["current_online_user"]
if current_user:
    update_online_heartbeat(current_user)

# ──────────────────────────────────────────────
# 4. SIDEBAR — บัญชีผู้ใช้
# ──────────────────────────────────────────────
with db_conn() as _c:
    all_users_global = [r["name"] for r in _c.execute("SELECT name FROM all_users").fetchall()]

st.sidebar.markdown("## 👤 บัญชีผู้ใช้งาน")

if current_user is None:
    st.sidebar.warning("⚠️ ยังไม่ได้เข้าสู่ระบบ")
    login_mode = st.sidebar.radio("", ["เลือกโปรไฟล์ที่มีอยู่", "สร้างโปรไฟล์ใหม่"], horizontal=True, label_visibility="collapsed")

    if login_mode == "เลือกโปรไฟล์ที่มีอยู่":
        if all_users_global:
            sel = st.sidebar.selectbox("เลือกชื่อ:", all_users_global)
            if st.sidebar.button("▶ เข้าสู่ระบบ", type="primary", use_container_width=True):
                st.session_state["current_online_user"] = sel
                update_online_heartbeat(sel)
                st.toast(f"👋 ยินดีต้อนรับ, {sel}!")
                st.rerun()
        else:
            st.sidebar.caption("ยังไม่มีสมาชิก — กรุณาสร้างใหม่")
    else:
        new_name = st.sidebar.text_input("ชื่อของคุณ:").strip()
        if st.sidebar.button("✅ สร้างและเข้าสู่ระบบ", type="primary", use_container_width=True):
            if new_name:
                try:
                    with db_conn() as conn:
                        conn.execute("INSERT INTO all_users (name) VALUES (?)", (new_name,))
                    st.session_state["current_online_user"] = new_name
                    update_online_heartbeat(new_name)
                    st.toast(f"🎉 สร้างโปรไฟล์ '{new_name}' สำเร็จ!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.sidebar.error("❌ ชื่อนี้ถูกใช้แล้ว")
            else:
                st.sidebar.error("⚠️ กรุณากรอกชื่อ")
else:
    st.sidebar.success(f"🟢 **{current_user}**")

    with db_conn() as _c:
        my_data = _c.execute("SELECT * FROM all_users WHERE name = ?", (current_user,)).fetchone()

    with st.sidebar.expander("⚙️ แก้ไขข้อมูลส่วนตัว"):
        edit_pp       = st.text_input("เลขพร้อมเพย์:", value=my_data["promptpay"] or "")
        db_bank       = my_data["bank_name"] or "-- เลือกธนาคาร --"
        bank_idx      = BANK_LIST.index(db_bank) if db_bank in BANK_LIST else 0
        edit_bank     = st.selectbox("ธนาคาร:", BANK_LIST, index=bank_idx)
        edit_acc      = st.text_input("เลขบัญชี:", value=my_data["bank_account"] or "")
        if st.button("💾 บันทึกข้อมูลส่วนตัว", use_container_width=True):
            final_bank = edit_bank if edit_bank != "-- เลือกธนาคาร --" else ""
            with db_conn() as conn:
                conn.execute(
                    "UPDATE all_users SET promptpay=?, bank_name=?, bank_account=? WHERE name=?",
                    (edit_pp, final_bank, edit_acc, current_user)
                )
            st.toast("💾 บันทึกเรียบร้อย!")
            st.rerun()

    if st.sidebar.button("🚪 ออกจากระบบ", use_container_width=True):
        with db_conn() as conn:
            conn.execute("DELETE FROM online_status WHERE name=?", (current_user,))
        st.session_state["current_online_user"] = None
        st.rerun()

# ──────────────────────────────────────────────
# Online users
# ──────────────────────────────────────────────
online_users = get_online_users()
st.sidebar.markdown("---")
st.sidebar.markdown("**🌐 ออนไลน์ขณะนี้**")
if online_users:
    for u in online_users:
        tag = " *(คุณ)*" if u == current_user else ""
        st.sidebar.markdown(f"🟢 {u}{tag}")
else:
    st.sidebar.caption("ไม่มีผู้ใช้อื่นออนไลน์")

# ──────────────────────────────────────────────
# 5. SIDEBAR — จัดการ Event
# ──────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.markdown("## ✈️ Event")

with st.sidebar.expander("➕ สร้าง Event ใหม่"):
    new_trip_name = st.text_input("ชื่อ Event:").strip()
    new_trip_date = st.date_input("วันที่จัด:", value=datetime.today())
    if st.button("สร้าง Event", type="primary", use_container_width=True):
        if new_trip_name:
            try:
                with db_conn() as conn:
                    conn.execute(
                        "INSERT INTO trips (name, status, trip_date) VALUES (?,0,?)",
                        (new_trip_name, new_trip_date.strftime("%Y-%m-%d"))
                    )
                st.toast(f"✈️ สร้าง Event '{new_trip_name}' สำเร็จ!")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("❌ ชื่อ Event ซ้ำ")
        else:
            st.error("⚠️ กรุณากรอกชื่อ Event")

with st.sidebar.expander("🗑️ ถังขยะ"):
    with db_conn() as _c:
        deleted_trips = _c.execute("SELECT * FROM trips WHERE status=1").fetchall()
    if not deleted_trips:
        st.caption("ไม่มีรายการในถังขยะ")
    else:
        for dt in deleted_trips:
            label = f"{dt['name']} ({dt['trip_date']})" if safe_has_date(dt['trip_date']) else dt['name']
            st.write(f"📁 {label}")
            col_r, col_d = st.columns(2)
            if col_r.button("กู้คืน", key=f"res_{dt['id']}", use_container_width=True):
                with db_conn() as conn:
                    conn.execute("UPDATE trips SET status=0 WHERE id=?", (dt['id'],))
                st.toast(f"🔄 กู้คืน '{dt['name']}' แล้ว")
                st.rerun()
            if col_d.button("ลบถาวร", key=f"pdel_{dt['id']}", use_container_width=True):
                with db_conn() as conn:
                    conn.execute("DELETE FROM settlements WHERE trip_id=?", (dt['id'],))
                    conn.execute("DELETE FROM expenses WHERE trip_id=?", (dt['id'],))
                    conn.execute("DELETE FROM members WHERE trip_id=?", (dt['id'],))
                    conn.execute("DELETE FROM notifications WHERE trip_id=?", (dt['id'],))
                    conn.execute("DELETE FROM trips WHERE id=?", (dt['id'],))
                st.toast(f"💥 ลบ '{dt['name']}' ถาวรแล้ว")
                st.rerun()

# โหลดรายการ Event ทั้งหมดที่ active
with db_conn() as _c:
    active_trips_raw = _c.execute("SELECT * FROM trips WHERE status=0 ORDER BY id DESC").fetchall()

if not active_trips_raw:
    st.title("✈️ Trip Expense Splitter")
    st.info("กรุณาสร้าง Event ใหม่ที่แถบเมนูซ้าย เพื่อเริ่มบันทึกค่าใช้จ่าย")
    st.stop()

def trip_display(t):
    return f"{t['name']} 📅 ({t['trip_date']})" if safe_has_date(t['trip_date']) else t['name']

trip_labels   = [trip_display(t) for t in active_trips_raw]
trips_by_label = {trip_display(t): t for t in active_trips_raw}

st.sidebar.markdown("---")
selected_label = st.sidebar.selectbox("🗺️ เลือก Event:", trip_labels)
matched_trip   = trips_by_label[selected_label]
current_trip   = matched_trip["name"]
trip_id        = int(matched_trip["id"])
current_trip_date = matched_trip["trip_date"]
has_valid_date = safe_has_date(current_trip_date)

with st.sidebar.expander("✏️ แก้ไข Event ปัจจุบัน"):
    rename_input = st.text_input("ชื่อใหม่:", value=current_trip).strip()
    try:
        default_date = datetime.strptime(str(current_trip_date), "%Y-%m-%d") if has_valid_date else datetime.today()
    except ValueError:
        default_date = datetime.today()
    re_date = st.date_input("วันที่:", value=default_date)
    if st.button("💾 บันทึกการเปลี่ยนแปลง", use_container_width=True):
        if rename_input:
            try:
                with db_conn() as conn:
                    conn.execute(
                        "UPDATE trips SET name=?, trip_date=? WHERE id=?",
                        (rename_input, re_date.strftime("%Y-%m-%d"), trip_id)
                    )
                st.toast(f"✏️ อัปเดตเป็น '{rename_input}' แล้ว")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("❌ ชื่อซ้ำกับ Event อื่น")
        else:
            st.error("⚠️ กรุณากรอกชื่อ")

if st.sidebar.button("🗑️ ย้ายไปถังขยะ", use_container_width=True):
    with db_conn() as conn:
        conn.execute("UPDATE trips SET status=1 WHERE id=?", (trip_id,))
    st.toast(f"🗑️ ย้าย '{current_trip}' ไปถังขยะแล้ว")
    st.rerun()

# ──────────────────────────────────────────────
# 6. SIDEBAR — สมาชิก Event
# ──────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.markdown(f"**👥 สมาชิกใน Event**")

with db_conn() as _c:
    existing_members = [r["name"] for r in _c.execute("SELECT name FROM members WHERE trip_id=?", (trip_id,)).fetchall()]
    all_users_list   = [r["name"] for r in _c.execute("SELECT name FROM all_users").fetchall()]

available_users = [u for u in all_users_list if u not in existing_members]

for member in existing_members:
    is_me     = " *(คุณ)*" if member == current_user else ""
    dot       = "🟢" if member in online_users else "⚪"
    # badge แจ้งเตือน
    with db_conn() as _c:
        cnt = _c.execute(
            "SELECT COUNT(*) as c FROM notifications WHERE trip_id=? AND to_user=? AND is_read=0",
            (trip_id, member)
        ).fetchone()["c"]
    badge = f" 🔴{cnt}" if cnt > 0 else ""
    col_m, col_x = st.sidebar.columns([5, 1])
    col_m.caption(f"{dot} {member}{is_me}{badge}")
    if col_x.button("✕", key=f"rm_{member}", help=f"ถอด {member}"):
        with db_conn() as conn:
            conn.execute("DELETE FROM members WHERE trip_id=? AND name=?", (trip_id, member))
        st.toast(f"ถอด {member} ออกแล้ว")
        st.rerun()

sel_add = st.sidebar.selectbox("เพิ่มสมาชิก:", ["-- เลือก --"] + available_users)
if st.sidebar.button("➕ เพิ่มเข้ากลุ่ม", use_container_width=True):
    if sel_add != "-- เลือก --":
        with db_conn() as conn:
            conn.execute("INSERT INTO members (trip_id, name) VALUES (?,?)", (trip_id, sel_add))
        st.toast(f"➕ เพิ่ม {sel_add} เข้ากลุ่มแล้ว!")
        st.rerun()

# ──────────────────────────────────────────────
# 7. SIDEBAR — แชท / แจ้งเตือน
# ──────────────────────────────────────────────
st.sidebar.markdown("---")

if current_user:
    with db_conn() as _c:
        unread_total = _c.execute(
            "SELECT COUNT(*) as c FROM notifications WHERE trip_id=? AND to_user=? AND is_read=0",
            (trip_id, current_user)
        ).fetchone()["c"]

    badge_label = f" 🔴 ({unread_total})" if unread_total > 0 else ""
    st.sidebar.markdown(f"**💬 แชทและแจ้งเตือน{badge_label}**")

    with db_conn() as _c:
        all_notifs = _c.execute(
            """SELECT * FROM notifications
               WHERE trip_id=? AND (to_user=? OR from_user=?)
               ORDER BY timestamp ASC, id ASC""",
            (trip_id, current_user, current_user)
        ).fetchall()

    # จัดกลุ่มแชท
    chat_groups = {}
    unread_map  = {}
    for n in all_notifs:
        if n["is_auto"] == 1 or n["from_user"] == "ระบบสรุปยอด":
            partner = "ระบบสรุปยอด"
        else:
            partner = n["from_user"] if n["to_user"] == current_user else n["to_user"]
        chat_groups.setdefault(partner, []).append(n)
        unread_map.setdefault(partner, 0)
        if n["to_user"] == current_user and n["is_read"] == 0:
            unread_map[partner] += 1

    with st.sidebar.expander(f"📥 กล่องข้อความ ({len(chat_groups)})", expanded=False):
        if not chat_groups:
            st.caption("ไม่มีประวัติข้อความ")
        else:
            tab_labels = []
            for p in chat_groups:
                b = f" 🔴{unread_map[p]}" if unread_map[p] > 0 else ""
                tab_labels.append(f"{'🤖' if p == 'ระบบสรุปยอด' else '👤'} {p}{b}")
            chat_tabs = st.tabs(tab_labels)

            for idx, partner in enumerate(chat_groups):
                with chat_tabs[idx]:
                    # Mark as read
                    if unread_map[partner] > 0:
                        with db_conn() as conn:
                            if partner == "ระบบสรุปยอด":
                                conn.execute(
                                    "UPDATE notifications SET is_read=1 WHERE trip_id=? AND to_user=? AND is_auto=1 AND is_read=0",
                                    (trip_id, current_user)
                                )
                            else:
                                conn.execute(
                                    "UPDATE notifications SET is_read=1 WHERE trip_id=? AND to_user=? AND from_user=? AND is_read=0",
                                    (trip_id, current_user, partner)
                                )
                        st.rerun()

                    for notif in chat_groups[partner]:
                        try:
                            dt_obj   = datetime.strptime(str(notif["timestamp"]), "%Y-%m-%d %H:%M:%S")
                            time_str = dt_obj.strftime("%H:%M")
                        except Exception:
                            time_str = str(notif["timestamp"])[11:16] if notif["timestamp"] else ""

                        is_mine   = (notif["from_user"] == current_user and notif["is_auto"] == 0)
                        is_system = (notif["from_user"] == "ระบบสรุปยอด" or notif["is_auto"] == 1)

                        if is_mine:
                            bubble_html = f"""<div style="display:flex;justify-content:flex-end;margin:6px 0;">
                                <div>
                                <div style="background:#85E374;color:#000;padding:8px 12px;border-radius:15px 15px 2px 15px;max-width:220px;font-size:13px;word-wrap:break-word;">{notif['message']}</div>
                                <div style="text-align:right;font-size:10px;color:#AAA;margin-top:2px;">{time_str}</div></div></div>"""
                        elif is_system:
                            bubble_html = f"""<div style="margin:6px 0;">
                                <div style="font-size:11px;color:#4A90E2;font-weight:bold;">🤖 ระบบ</div>
                                <div style="background:#D6E4FF;color:#000;padding:8px 12px;border-radius:2px 15px 15px 15px;max-width:220px;font-size:13px;border-left:4px solid #4A90E2;word-wrap:break-word;">{notif['message']}</div>
                                <div style="font-size:10px;color:#AAA;margin-top:2px;">{time_str}</div></div>"""
                        else:
                            bubble_html = f"""<div style="margin:6px 0;">
                                <div style="font-size:11px;color:#888;">👤 {notif['from_user']}</div>
                                <div style="background:#EAEAEA;color:#000;padding:8px 12px;border-radius:2px 15px 15px 15px;max-width:220px;font-size:13px;word-wrap:break-word;">{notif['message']}</div>
                                <div style="font-size:10px;color:#AAA;margin-top:2px;">{time_str}</div></div>"""

                        st.markdown(bubble_html, unsafe_allow_html=True)
                        if st.button("🗑️", key=f"dn_{notif['id']}", help="ลบข้อความนี้"):
                            with db_conn() as conn:
                                conn.execute("DELETE FROM notifications WHERE id=?", (notif["id"],))
                            st.rerun()
                        st.markdown("<hr style='margin:4px 0;border-color:#EEE;'>", unsafe_allow_html=True)

                    if partner != "ระบบสรุปยอด":
                        with st.form(key=f"reply_{partner}", clear_on_submit=True):
                            reply_text = st.text_input("ตอบกลับ:", placeholder=f"คุยกับ {partner}…")
                            if st.form_submit_button("↩️ ส่ง", use_container_width=True, type="primary"):
                                if reply_text.strip():
                                    with db_conn() as conn:
                                        conn.execute(
                                            "INSERT INTO notifications (trip_id,to_user,from_user,message,is_auto,is_read,timestamp) VALUES (?,?,?,?,0,0,datetime('now','localtime'))",
                                            (trip_id, partner, current_user, reply_text.strip())
                                        )
                                    st.toast(f"✅ ส่งถึง {partner} แล้ว!")
                                    st.rerun()

    with st.sidebar.expander("📝 ส่งข้อความหาเพื่อน"):
        others = [m for m in existing_members if m != current_user]
        if not others:
            st.caption("ไม่มีสมาชิกคนอื่นในกลุ่ม")
        else:
            send_to = st.selectbox("ส่งหา:", others, key="new_chat_to")
            with st.form("new_chat_form", clear_on_submit=True):
                msg = st.text_area("ข้อความ:", placeholder="พิมพ์ที่นี่…")
                if st.form_submit_button("🚀 ส่ง", type="primary", use_container_width=True):
                    if msg.strip():
                        with db_conn() as conn:
                            conn.execute(
                                "INSERT INTO notifications (trip_id,to_user,from_user,message,is_auto,is_read,timestamp) VALUES (?,?,?,?,0,0,datetime('now','localtime'))",
                                (trip_id, send_to, current_user, msg.strip())
                            )
                        st.toast(f"🚀 ส่งถึง {send_to} แล้ว!")
                        st.rerun()
                    else:
                        st.error("⚠️ กรุณากรอกข้อความ")
else:
    st.sidebar.caption("กรุณาเข้าสู่ระบบเพื่อใช้แชท")

# ──────────────────────────────────────────────
# 8. MAIN AREA — ต้องล็อกอินและมีสมาชิกก่อน
# ──────────────────────────────────────────────
if current_user is None:
    st.title("✈️ Trip Expense Splitter")
    st.warning("👈 กรุณาเลือกโปรไฟล์ที่แถบเมนูซ้ายเพื่อเริ่มใช้งาน")
    st.stop()

if not existing_members:
    st.title(f"✈️ {current_trip}")
    st.warning("⚠️ ยังไม่มีสมาชิกในกลุ่มนี้ กรุณาเพิ่มสมาชิกที่เมนูซ้าย")
    st.stop()

# Header
col_title, col_info = st.columns([3, 1])
with col_title:
    st.title(f"✈️ {current_trip}")
    if has_valid_date:
        st.caption(f"📅 {current_trip_date}  |  👥 {len(existing_members)} คน")
with col_info:
    # สรุปยอดรวมเร็ว
    with db_conn() as _c:
        total_amt = _c.execute("SELECT COALESCE(SUM(amount),0) as t FROM expenses WHERE trip_id=?", (trip_id,)).fetchone()["t"]
    st.metric("💰 ยอดรวมทริป", f"{total_amt:,.0f} ฿")

st.markdown("---")

# ──────────────────────────────────────────────
# 9. TABS
# ──────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📝  สร้างบิลใหม่", "📊  ประวัติบิล", "💰  สรุปเคลียร์เงิน"])

# ═══════════════════════════════════
# TAB 1 — เพิ่มบิล
# ═══════════════════════════════════
with tab1:
    st.markdown("### ➕ เพิ่มรายการค่าใช้จ่าย")
    with st.form("add_bill", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            desc = st.text_input("📋 รายการ:", placeholder="เช่น ค่าอาหารเย็น, ค่าน้ำมัน…")
        with col_b:
            amt = st.number_input("💵 จำนวนเงิน (บาท):", min_value=0.0, step=1.0, format="%.2f")

        default_idx = existing_members.index(current_user) if current_user in existing_members else 0
        payer = st.selectbox("👤 คนสำรองจ่ายก่อน:", existing_members, index=default_idx)

        st.markdown("**👥 คนร่วมหารบิลนี้:**")
        cols = st.columns(min(len(existing_members), 4))
        split_to = []
        for i, m in enumerate(existing_members):
            if cols[i % 4].checkbox(m, value=True, key=f"add_{m}"):
                split_to.append(m)

        file = st.file_uploader("📎 แนบสลิป (ไม่บังคับ):", type=["jpg", "png", "jpeg"])

        submitted = st.form_submit_button("💾 บันทึกบิล", type="primary", use_container_width=True)
        if submitted:
            if desc and amt > 0 and split_to:
                blob = compress_image(file)
                with db_conn() as conn:
                    conn.execute(
                        "INSERT INTO expenses (trip_id,description,amount,payer_name,split_members,image_blob) VALUES (?,?,?,?,?,?)",
                        (trip_id, desc, amt, payer, ",".join(split_to), blob)
                    )
                    # แจ้งเตือนอัตโนมัติ
                    share_amt = amt / len(split_to)
                    for member in split_to:
                        if member != payer:
                            sys_msg = (f"📌 บิลใหม่: '{desc}'\n"
                                       f"💰 ยอดรวม {amt:,.2f} บาท\n"
                                       f"👤 คนจ่าย: {payer}\n"
                                       f"💸 ส่วนของคุณ: {share_amt:,.2f} บาท")
                            conn.execute(
                                "INSERT INTO notifications (trip_id,to_user,from_user,message,is_auto,is_read,timestamp) VALUES (?,?,?,?,1,0,datetime('now','localtime'))",
                                (trip_id, member, "ระบบสรุปยอด", sys_msg)
                            )
                st.success(f"✅ บันทึกบิล '{desc}' สำเร็จ!")
                time.sleep(0.8)
                st.rerun()
            else:
                st.error("⚠️ กรุณากรอกรายการ, จำนวนเงิน และเลือกผู้ร่วมหารอย่างน้อย 1 คน")

# ═══════════════════════════════════
# TAB 2 — ประวัติบิล
# ═══════════════════════════════════
with tab2:
    with db_conn() as _c:
        expenses = _c.execute("SELECT * FROM expenses WHERE trip_id=? ORDER BY id DESC", (trip_id,)).fetchall()

    if not expenses:
        st.info("📭 ยังไม่มีรายการบิล รายการจะอัปเดตอัตโนมัติเมื่อมีการบันทึก")
    else:
        st.markdown(f"### 📊 รายการทั้งหมด ({len(expenses)} รายการ)")
        for row in expenses:
            with st.expander(f"📌 **{row['description']}** — {row['amount']:,.2f} ฿  |  จ่ายโดย {row['payer_name']}"):
                c1, c2 = st.columns([1, 1.5])
                with c1:
                    if row["image_blob"]:
                        st.image(row["image_blob"], use_container_width=True, caption="สลิป")
                    else:
                        st.caption("ไม่มีสลิปแนบ")
                with c2:
                    with st.form(f"edit_{row['id']}"):
                        u_desc  = st.text_input("รายการ:", value=row["description"])
                        u_amt   = st.number_input("จำนวนเงิน:", value=float(row["amount"]), format="%.2f")
                        payer_opts = existing_members if row["payer_name"] in existing_members else existing_members + [row["payer_name"]]
                        u_payer = st.selectbox("คนจ่าย:", payer_opts, index=payer_opts.index(row["payer_name"]))
                        st.write("คนหาร:")
                        cur_split = row["split_members"].split(",") if row["split_members"] else []
                        u_split = [m for m in payer_opts if st.checkbox(m, value=(m in cur_split), key=f"ed_{row['id']}_{m}")]
                        u_file  = st.file_uploader("เปลี่ยนสลิป:", type=["jpg","png","jpeg"])
                        del_img = st.checkbox("🗑️ ลบรูปสลิปออก", key=f"di_{row['id']}")

                        if st.form_submit_button("💾 อัปเดต", type="primary"):
                            with db_conn() as conn:
                                if del_img:
                                    conn.execute(
                                        "UPDATE expenses SET description=?,amount=?,payer_name=?,split_members=?,image_blob=NULL WHERE id=?",
                                        (u_desc, u_amt, u_payer, ",".join(u_split), row["id"])
                                    )
                                elif u_file:
                                    conn.execute(
                                        "UPDATE expenses SET description=?,amount=?,payer_name=?,split_members=?,image_blob=? WHERE id=?",
                                        (u_desc, u_amt, u_payer, ",".join(u_split), compress_image(u_file), row["id"])
                                    )
                                else:
                                    conn.execute(
                                        "UPDATE expenses SET description=?,amount=?,payer_name=?,split_members=? WHERE id=?",
                                        (u_desc, u_amt, u_payer, ",".join(u_split), row["id"])
                                    )
                            st.success(f"✅ อัปเดต '{u_desc}' สำเร็จ!")
                            time.sleep(0.8)
                            st.rerun()

                if st.button("🗑️ ลบบิลนี้", key=f"delb_{row['id']}", type="secondary"):
                    with db_conn() as conn:
                        conn.execute("DELETE FROM expenses WHERE id=?", (row["id"],))
                    st.warning("🗑️ ลบรายการเรียบร้อย")
                    time.sleep(0.8)
                    st.rerun()

# ═══════════════════════════════════
# TAB 3 — สรุปเคลียร์เงิน
# ═══════════════════════════════════
with tab3:
    with db_conn() as _c:
        expenses_rows = _c.execute("SELECT * FROM expenses WHERE trip_id=?", (trip_id,)).fetchall()
        user_profiles = {
            r["name"]: {"promptpay": r["promptpay"], "bank_name": r["bank_name"], "bank_acc": r["bank_account"]}
            for r in _c.execute("SELECT name, promptpay, bank_name, bank_account FROM all_users").fetchall()
        }

    if not expenses_rows:
        st.info("📭 ยังไม่มีรายการบิลที่จะคำนวณ")
    else:
        # คำนวณยอดสุทธิ
        all_involved = set(existing_members)
        for r in expenses_rows:
            all_involved.add(r["payer_name"])
            all_involved.update(r["split_members"].split(",") if r["split_members"] else [])

        net = {m: 0.0 for m in all_involved}
        for r in expenses_rows:
            net[r["payer_name"]] += r["amount"]
            s_list = r["split_members"].split(",") if r["split_members"] else [r["payer_name"]]
            share  = r["amount"] / len(s_list)
            for m in s_list:
                net[m] -= share

        # แสดงยอดสุทธิ
        col_g, col_r = st.columns(2)
        with col_g:
            st.markdown("#### 🟢 ได้รับเงินคืน")
            has_green = False
            for m, b in net.items():
                if b > 0.01:
                    has_green = True
                    st.markdown(f'<div class="expense-card"><b>{m}</b><br>'
                                f'<span class="badge-green">+{b:,.2f} ฿</span></div>', unsafe_allow_html=True)
            if not has_green:
                st.caption("—")
        with col_r:
            st.markdown("#### 🔴 ต้องจ่ายออก")
            has_red = False
            for m, b in net.items():
                if b < -0.01:
                    has_red = True
                    st.markdown(f'<div class="expense-card" style="border-color:#FCA5A5"><b>{m}</b><br>'
                                f'<span class="badge-red">−{abs(b):,.2f} ฿</span></div>', unsafe_allow_html=True)
            if not has_red:
                st.caption("—")

        st.markdown("---")
        st.markdown("### 🚀 แผนการโอนเงิน")

        debtors   = [[m, b] for m, b in net.items() if b < -0.01]
        creditors = [[m, b] for m, b in net.items() if b > 0.01]
        final_tx  = []

        while debtors and creditors:
            amt_tx  = min(abs(debtors[0][1]), creditors[0][1])
            d_name  = debtors[0][0]
            c_name  = creditors[0][0]

            prof  = user_profiles.get(c_name, {})
            pp    = (prof.get("promptpay") or "").strip()
            b_name = (prof.get("bank_name") or "").strip()
            b_acc  = (prof.get("bank_acc") or "").strip()

            is_me_tag = " ⚠️ *(รายการของคุณ)*" if d_name == current_user else ""

            st.markdown(
                f'<div class="transfer-row">'
                f'💳 <b>{d_name}</b> &nbsp;→&nbsp; <b>{c_name}</b> &nbsp;&nbsp;'
                f'<span class="badge-red">{amt_tx:,.2f} ฿</span>{is_me_tag}</div>',
                unsafe_allow_html=True
            )

            if pp or b_acc:
                cp, cb = st.columns(2)
                with cp:
                    if pp:
                        st.caption(f"📱 พร้อมเพย์ {c_name}")
                        st.code(pp, language="text")
                with cb:
                    if b_acc:
                        label = f"🏦 {b_name}" if b_name else "🏦 เลขบัญชี"
                        st.caption(f"{label} ของ {c_name}")
                        st.code(b_acc, language="text")
            else:
                st.caption(f"⚠️ {c_name} ยังไม่ได้บันทึกข้อมูลบัญชี")

            final_tx.append((d_name, c_name, amt_tx))
            debtors[0][1]   += amt_tx
            creditors[0][1] -= amt_tx
            if abs(debtors[0][1])   < 0.01: debtors.pop(0)
            if abs(creditors[0][1]) < 0.01: creditors.pop(0)

        # ส่งเข้า LINE
        if final_tx:
            st.markdown("---")
            st.markdown("### 📲 ส่งสรุปยอดเข้า LINE")
            line_msg = f"📊 สรุปค่าใช้จ่ายทริป: {current_trip}\n"
            if has_valid_date:
                line_msg += f"📅 วันที่: {current_trip_date}\n"
            line_msg += "———————————————\n"
            for dn, cn, am in final_tx:
                line_msg += f"💳 {dn} → {cn} = {am:,.2f} บาท\n"
                pp2 = (user_profiles.get(cn, {}).get("promptpay") or "").strip()
                if pp2:
                    line_msg += f"   📱 พร้อมเพย์: {pp2}\n"
            line_msg += "———————————————"
            st.text_area("ข้อความสรุป:", value=line_msg, height=160, disabled=True)
            st.link_button(
                "🟢 แชร์เข้าแอป LINE",
                f"https://line.me/R/msg/text/?{urllib.parse.quote(line_msg)}",
                type="primary", use_container_width=True
            )
