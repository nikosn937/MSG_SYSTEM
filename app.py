import streamlit as st
import pyodbc
import pandas as pd
import requests

# --- 1. ΡΥΘΜΙΣΗ ΣΕΛΙΔΑΣ ---
st.set_page_config(
    page_title="Σχολικό Portal Μηνυμάτων",
    page_icon="💬",
    layout="wide"
)

# --- 2. ΣΥΝΔΕΣΗ ΜΕ ΒΑΣΗ ΔΕΔΟΜΕΝΩΝ ---
def get_db_connection():
    try:
        driver = st.secrets["DB_DRIVER"]
        server = st.secrets["DB_SERVER"]
        port = st.secrets.get("DB_PORT", "1433")
        database = st.secrets["DB_NAME"]
        user = st.secrets["DB_USER"]
        password = st.secrets["DB_PASSWORD"]
        
        # Connection string για Remote SQL Server με SQL Authentication
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server},{port};"
            f"DATABASE={database};"
            f"UID={user};"
            f"PWD={password};"
            f"Encrypt=yes;"                  # Ενεργοποίηση SSL/TLS encryption
            f"TrustServerCertificate=yes;"   # Για αποφυγή σφαλμάτων πιστοποιητικού
            f"Connection Timeout=30;"
        )
        
        conn = pyodbc.connect(conn_str)
        return conn
    except Exception as e:
        st.error(f"❌ Σφάλμα σύνδεσης με τον SQL Server: {e}")
        return None

# --- 3. ΑΠΟΣТОΛΗ ΜΗΝΥΜΑΤΟΣ SIGNAL ---
def send_signal_message(recipient, message_text):
    """Αποστολή μηνύματος κειμένου μέσω του local Signal REST API service"""
    api_url = st.secrets.get("SIGNAL_API_URL", "http://localhost:8080")
    sender = st.secrets.get("SIGNAL_SENDER", "")

    endpoint = f"{api_url}/v2/send"
    payload = {
        "message": message_text,
        "number": sender,
        "recipients": [recipient]
    }
    try:
        response = requests.post(endpoint, json=payload, timeout=5)
        return response.status_code in [200, 201]
    except Exception:
        return False

# --- 4. SESSION STATE ---
if "user_role" not in st.session_state:
    st.session_state["user_role"] = None
if "user_info" not in st.session_state:
    st.session_state["user_info"] = None

def logout():
    st.session_state["user_role"] = None
    st.session_state["user_info"] = None
    st.rerun()

# --- 5. ΟΘΟΝΗ ΣΥΝΔΕΣΗΣ (LOGIN) ---
if st.session_state["user_role"] is None:
    st.title("💬 Σχολικό Portal Μηνυμάτων & Ενημερώσεων")
    st.subheader("Σύνδεση στο Σύστημα")

    tab_admin, tab_parent = st.tabs(["👨‍🏫 Αποστολέας / Διαχειριστής", "👨‍👩‍👧 Γονέας / Κηδεμόνας"])

    # --- LOGIN ΑΠΟΣΤΟΛΕΑ / ADMIN ---
    with tab_admin:
        with st.form("admin_login_form"):
            username = st.text_input("Όνομα Χρήστη")
            password = st.text_input("Κωδικός Πρόσβασης", type="password")
            submit_admin = st.form_submit_button("Σύνδεση ως Αποστολέας")

            if submit_admin:
                if username == "admin" and password == "admin123":
                    st.session_state["user_role"] = "Admin"
                    st.session_state["user_info"] = {"name": "Διεύθυνση / Εκπαιδευτικός"}
                    st.success("Επιτυχής σύνδεση!")
                    st.rerun()
                else:
                    st.error("Λανθασμένα στοιχεία σύνδεσης.")

    # --- LOGIN ΓΟΝΕΑ ---
    with tab_parent:
        with st.form("parent_login_form"):
            phone = st.text_input("Αριθμός Τηλεφώνου", placeholder="+35799XXXXXX")
            password = st.text_input("Κωδικός Πρόσβασης", type="password")
            submit_parent = st.form_submit_button("Σύνδεση ως Γονέας")

            if submit_parent:
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    query = """
                        SELECT ParentID, FirstName, LastName 
                        FROM Parents 
                        WHERE Phone = ? AND PasswordHash = ? AND IsActive = 1
                    """
                    cursor.execute(query, (phone, password))
                    parent = cursor.fetchone()
                    conn.close()

                    if parent:
                        st.session_state["user_role"] = "Parent"
                        st.session_state["user_info"] = {
                            "id": parent[0],
                            "name": f"{parent[1]} {parent[2]}",
                            "phone": phone
                        }
                        st.success(f"Καλώς ήρθατε, {parent[1]}!")
                        st.rerun()
                    else:
                        st.error("Δεν βρέθηκε ενεργός λογαριασμός γονέα με αυτά τα στοιχεία.")

# --- 6. ΠΟΡΤΑΛ ΑΠΟΣΤΟΛΕΑ (ADMIN) ---
elif st.session_state["user_role"] == "Admin":
    st.sidebar.title("⚙️ Διαχείριση Αποστολών")
    st.sidebar.write(f"👤 Σύνδεση: **{st.session_state['user_info']['name']}**")
    if st.sidebar.button("🚪 Αποσύνδεση"):
        logout()

    st.header("📤 Σύνταξη & Αποστολή Νέου Μηνύματος")

    # Ανάκτηση τμημάτων από τη βάση
    conn = get_db_connection()
    classes_dict = {"Όλα τα τμήματα (ALL)": None}
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ClassID, ClassName FROM Classes ORDER BY ClassName")
        for cid, cname in cursor.fetchall():
            classes_dict[cname] = cid
        conn.close()

    with st.form("send_announcement_form"):
        title = st.text_input("Θέμα / Τίτλος Μηνύματος")
        selected_class_label = st.selectbox("Παραλήπτες (Τμήμα)", list(classes_dict.keys()))
        content = st.text_area("Περιεχόμενο Μηνύματος", height=150)
        
        send_signal = st.checkbox("📲 Αποστολή και ως Signal SMS στους παραλήπτες", value=True)
        
        submit = st.form_submit_button("🚀 Αποστολή Μηνύματος")

        if submit:
            if not title or not content:
                st.warning("Παρακαλώ συμπληρώστε τίτλο και περιεχόμενο.")
            else:
                target_audience = "ALL" if selected_class_label == "Όλα τα τμήματα (ALL)" else "CLASS"
                class_id = classes_dict[selected_class_label]

                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    
                    # 1. Καταχώρηση στον πίνακα Announcements
                    insert_query = """
                        INSERT INTO Announcements (Title, Content, TargetAudience, ClassID, SentBy, CreatedAt)
                        VALUES (?, ?, ?, ?, ?, GETDATE())
                    """
                    cursor.execute(insert_query, (title, content, target_audience, class_id, st.session_state['user_info']['name']))
                    conn.commit()
                    st.success("✅ Το μήνυμα καταχωρήθηκε στη βάση!")

                    # 2. Αποστολή Signal SMS στους γονείς του στοχευμένου τμήματος/όλων
                    if send_signal:
                        if target_audience == "ALL":
                            phone_query = "SELECT DISTINCT Phone FROM Parents WHERE IsActive = 1 AND Phone IS NOT NULL"
                            cursor.execute(phone_query)
                        else:
                            phone_query = """
                                SELECT DISTINCT P.Phone 
                                FROM Parents P
                                JOIN StudentParents SP ON P.ParentID = SP.ParentID
                                JOIN Students S ON SP.StudentID = S.StudentID
                                WHERE S.ClassID = ? AND P.IsActive = 1 AND P.Phone IS NOT NULL
                            """
                            cursor.execute(phone_query, (class_id,))
                        
                        phones = [row[0] for row in cursor.fetchall()]
                        conn.close()

                        sent_count = 0
                        signal_text = f"📩 *{title}*\n\n{content}"
                        for phone_num in phones:
                            if send_signal_message(phone_num, signal_text):
                                sent_count += 1
                        
                        st.info(f"📲 Το μήνυμα στάλθηκε επιτυχώς μέσω Signal σε {sent_count} παραλήπτες.")

    st.markdown("---")
    st.subheader("📜 Ιστορικό Απεσταλμένων Μηνυμάτων")
    conn = get_db_connection()
    if conn:
        query_history = """
            SELECT A.AnnouncementID, A.Title, A.TargetAudience, C.ClassName, A.SentBy, A.CreatedAt
            FROM Announcements A
            LEFT JOIN Classes C ON A.ClassID = C.ClassID
            ORDER BY A.CreatedAt DESC
        """
        df_history = pd.read_sql(query_history, conn)
        conn.close()
        st.dataframe(df_history, use_container_width=True)

# --- 7. ΠΟΡΤΑΛ ΓΟΝΕΑ (RECEIVE & READ RECEIPTS) ---
elif st.session_state["user_role"] == "Parent":
    parent_id = st.session_state["user_info"]["id"]
    parent_name = st.session_state["user_info"]["name"]

    st.sidebar.title("💬 Portal Μηνυμάτων")
    st.sidebar.write(f"👤 Γονέας: **{parent_name}**")
    if st.sidebar.button("🚪 Αποσύνδεση"):
        logout()

    st.header("📥 Εισερχόμενα Μηνύματα")

    conn = get_db_connection()
    if conn:
        # Ανάκτηση μηνυμάτων που αφορούν τα τμήματα των παιδιών του γονέα ή όλο το σχολείο (ALL)
        query_messages = """
            SELECT DISTINCT A.AnnouncementID, A.Title, A.Content, A.SentBy, A.CreatedAt, C.ClassName,
                   R.ReadAt
            FROM Announcements A
            LEFT JOIN Classes C ON A.ClassID = C.ClassID
            LEFT JOIN ReadReceipts R ON A.AnnouncementID = R.AnnouncementID AND R.ParentID = ?
            WHERE A.TargetAudience = 'ALL' 
               OR A.ClassID IN (
                   SELECT S.ClassID 
                   FROM Students S
                   JOIN StudentParents SP ON S.StudentID = SP.StudentID
                   WHERE SP.ParentID = ?
               )
            ORDER BY A.CreatedAt DESC
        """
        df_msgs = pd.read_sql(query_messages, conn, params=[parent_id, parent_id])
        conn.close()

        if not df_msgs.empty:
            for _, row in df_msgs.iterrows():
                ann_id = row["AnnouncementID"]
                is_read = pd.notnull(row["ReadAt"])
                badge = "✅ Αναγνώστηκε" if is_read else "🔴 Νέο!"
                
                with st.expander(f"📩 {row['Title']} ({row['CreatedAt']}) — {badge}"):
                    st.write(row['Content'])
                    st.caption(f"Αποστολέας: {row['SentBy']} | Τμήμα: {row['ClassName'] if row['ClassName'] else 'Όλα'}")

                    # Επιβεβαίωση Ανάγνωσης (Read Receipt)
                    if not is_read:
                        if st.button("👁️ Σήμανση ως Αναγνωσμένο", key=f"read_{ann_id}"):
                            conn_receipt = get_db_connection()
                            if conn_receipt:
                                cur = conn_receipt.cursor()
                                try:
                                    cur.execute(
                                        "INSERT INTO ReadReceipts (AnnouncementID, ParentID, ReadAt) VALUES (?, ?, GETDATE())",
                                        (ann_id, parent_id)
                                    )
                                    conn_receipt.commit()
                                    st.success("Επιβεβαιώθηκε η ανάγνωση!")
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"Σφάλμα καταγραφής ανάγνωσης: {ex}")
                                finally:
                                    conn_receipt.close()
        else:
            st.info("Δεν υπάρχουν εισερχόμενα μηνύματα.")
