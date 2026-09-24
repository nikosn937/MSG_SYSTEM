import streamlit as st
import pyodbc
import pandas as pd
import requests
import streamlit.components.v1 as components

# --- 1. ΡΥΘΜΙΣΗ ΣΕΛΙΔΑΣ ---
st.set_page_config(
    page_title="Σχολικό Portal Μηνυμάτων",
    page_icon="💬",
    layout="wide"
)

# --- 2. ΣΥΝΔΕΣΗ ΜΕ ΑΠΟΜΑΚΡΥΣΜΕΝΟ SQL SERVER (FreeTDS) ---
def get_db_connection():
    try:
        server = st.secrets["DB_SERVER"]
        port = st.secrets.get("DB_PORT", "1433")
        database = st.secrets["DB_NAME"]
        user = st.secrets["DB_USER"]
        password = st.secrets["DB_PASSWORD"]
        
        conn_str = (
            "DRIVER={FreeTDS};"
            f"SERVER={server};"
            f"PORT={port};"
            f"DATABASE={database};"
            f"UID={user};"
            f"PWD={password};"
            "TDS_Version=7.4;"
        )
        
        conn = pyodbc.connect(conn_str)
        return conn
    except Exception as e:
        st.error(f"❌ Σφάλμα σύνδεσης με τον SQL Server: {e}")
        return None

# --- 3. ONESIGNAL PROMPT SCRIPT (ΓΙΑ ΤΟΥΣ ΓΟΝΕΙΣ) ---
def inject_onesignal_script():
    app_id = st.secrets.get("ONESIGNAL_APP_ID", "")
    if app_id:
        onesignal_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <style>
            * {{ box-sizing: border-box; }}
            body {{ 
              margin: 0; 
              padding: 0; 
              font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
              background: transparent; 
            }}
            .card {{
              background-color: #f0f7ff;
              border: 1px solid #b3d8ff;
              border-radius: 8px;
              padding: 10px 15px;
              display: flex;
              align-items: center;
              justify-content: space-between;
              gap: 10px;
            }}
            .card-text {{
              color: #1e3a8a;
              font-size: 14px;
              font-weight: 500;
            }}
            .btn {{
              background-color: #1d4ed8;
              color: #ffffff;
              border: none;
              padding: 8px 16px;
              font-size: 13px;
              font-weight: 600;
              border-radius: 6px;
              cursor: pointer;
              white-space: nowrap;
            }}
            .btn:hover {{
              background-color: #1e40af;
            }}
          </style>
          <script>
            function openPrompt() {{
              // Ανοίγουμε νέο παράθυρο για να ξεπεράσουμε το iframe restriction του Streamlit
              const w = 450;
              const h = 350;
              const left = (screen.width - w) / 2;
              const top = (screen.height - h) / 2;
              
              const popup = window.open("", "OneSignalPrompt", `width=${{w}},height=${{h}},top=${{top}},left=${{left}}`);
              
              if (popup) {{
                popup.document.write(`
                  <!DOCTYPE html>
                  <html>
                  <head>
                    <title>Ενεργοποίηση Ειδοποιήσεων</title>
                    <script src="https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.js" defer></script>
                    <script>
                      window.OneSignalDeferred = window.OneSignalDeferred || [];
                      OneSignalDeferred.push(async function(OneSignal) {{
                        await OneSignal.init({{
                          appId: "{app_id}",
                        }});
                      }});

                      async function requestPermission() {{
                        window.OneSignalDeferred.push(async function(OneSignal) {{
                          try {{
                            await OneSignal.Notifications.requestPermission();
                            alert("Οι ειδοποιήσεις ενεργοποιήθηκαν επιτυχώς!");
                            window.close();
                          }} catch (err) {{
                            alert("Παρακαλούμε επιτρέψτε τις ειδοποιήσεις στις ρυθμίσεις του browser σας.");
                          }}
                        }});
                      }}
                    </script>
                    <style>
                      body {{ font-family: system-ui, sans-serif; text-align: center; padding: 40px 20px; background: #f8fafc; color: #0f172a; }}
                      .btn-popup {{ background: #2563eb; color: white; border: none; padding: 12px 24px; font-size: 15px; font-weight: 600; border-radius: 8px; cursor: pointer; margin-top: 20px; }}
                      .btn-popup:hover {{ background: #1d4ed8; }}
                    </style>
                  </head>
                  <body>
                    <h3>🔔 Ενεργοποίηση Ειδοποιήσεων</h3>
                    <p>Πατήστε το κουμπί παρακάτω για να επιτρέψετε τις ειδοποιήσεις από το σχολείο.</p>
                    <button class="btn-popup" onclick="requestPermission()">Επιτροπεί Ειδοποιήσεων</button>
                  </body>
                  </html>
                `);
              }} else {{
                alert("Παρακαλώ επιτρέψτε τα αναδυόμενα παράθυρα (Pop-ups) στον browser σας.");
              }}
            }}
          </script>
        </head>
        <body>
          <div class="card">
            <span class="card-text">🔔 <b>Ειδοποιήσεις Σχολείου:</b> Ενεργοποιήστε τις ειδοποιήσεις για να λαμβάνετε ανακοινώσεις.</span>
            <button class="btn" onclick="openPrompt()">🔔 Ενεργοποίηση</button>
          </div>
        </body>
        </html>
        """
        components.html(onesignal_html, height=65)
# --- 4. ΑΠΟΣТОΛΗ PUSH NOTIFICATION ΜΕΣΩ ONESIGNAL API ---
def send_onesignal_notification(title, message_text):
    app_id = st.secrets.get("ONESIGNAL_APP_ID")
    rest_key = st.secrets.get("ONESIGNAL_REST_KEY")

    if not app_id or not rest_key:
        st.warning("⚠️ Λείπουν τα διαπιστευτήρια του OneSignal στα Secrets.")
        return False

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Basic {rest_key}"
    }

    payload = {
        "app_id": app_id,
        "included_segments": ["Subscribed Users"],  # Στέλνει σε όλους τους συνδεδεμένους χρήστες
        "headings": {"el": title, "en": title},
        "contents": {"el": message_text, "en": message_text}
    }

    try:
        response = requests.post(
            "https://onesignal.com/api/v1/notifications",
            headers=headers,
            json=payload,
            timeout=5
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Σφάλμα αποστολής Push: {e}")
        return False

# --- 5. SESSION STATE ---
if "user_role" not in st.session_state:
    st.session_state["user_role"] = None
if "user_info" not in st.session_state:
    st.session_state["user_info"] = None

def logout():
    st.session_state["user_role"] = None
    st.session_state["user_info"] = None
    st.rerun()

# --- 6. ΟΘΟΝΗ ΣΥΝΔΕΣΗΣ (LOGIN) ---
if st.session_state["user_role"] is None:
    st.title("💬 Σχολικό Portal Μηνυμάτων & Ενημερώσεων")
    st.subheader("Σύνδεση στο Σύστημα")

    tab_admin, tab_parent = st.tabs(["👨‍🏫 Αποστολέας / Εκπαιδευτικός", "👨‍👩‍👧 Γονέας / Κηδεμόνας"])

    with tab_admin:
        with st.form("admin_login_form"):
            username = st.text_input("Όνομα Χρήστη (Username)")
            password = st.text_input("Κωδικός Πρόσβασης", type="password")
            submit_admin = st.form_submit_button("Σύνδεση")

            if submit_admin:
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    query = """
                        SELECT UserID, FullName, Role 
                        FROM Users 
                        WHERE Username = ? AND PasswordHash = ? AND IsActive = 1
                    """
                    cursor.execute(query, (username, password))
                    user = cursor.fetchone()
                    conn.close()

                    if user:
                        st.session_state["user_role"] = user[2]
                        st.session_state["user_info"] = {
                            "id": user[0],
                            "name": user[1],
                            "role": user[2]
                        }
                        st.success(f"Καλώς ήρθατε, {user[1]}!")
                        st.rerun()
                    else:
                        st.error("Λανθασμένα στοιχεία σύνδεσης.")

    with tab_parent:
        with st.form("parent_login_form"):
            phone = st.text_input("Αριθμός Τηλεφώνου", placeholder="99XXXXXX")
            password = st.text_input("Κωδικός Πρόσβασης", type="password")
            submit_parent = st.form_submit_button("Σύνδεση ως Γονέας")

            if submit_parent:
                clean_phone = phone.strip().replace("+357", "").replace(" ", "").replace("-", "")
                clean_pass = password.strip().replace("+357", "").replace(" ", "").replace("-", "")

                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    query = """
                        SELECT ParentID, FirstName, LastName, Phone 
                        FROM Parents 
                        WHERE LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(Phone, '+357', ''), ' ', ''), '-', ''))) = ? 
                          AND LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(PasswordHash, '+357', ''), ' ', ''), '-', ''))) = ?
                          AND (IsActive = 1 OR IsActive IS NULL)
                    """
                    cursor.execute(query, (clean_phone, clean_pass))
                    parent = cursor.fetchone()
                    conn.close()

                    if parent:
                        st.session_state["user_role"] = "Parent"
                        st.session_state["user_info"] = {
                            "id": parent[0],
                            "name": f"{parent[1]} {parent[2]}",
                            "phone": parent[3]
                        }
                        st.success(f"Καλώς ήρθατε, {parent[1]}!")
                        st.rerun()
                    else:
                        st.error("❌ Δεν βρέθηκε ενεργός λογαριασμός γονέα με αυτά τα στοιχεία.")

# --- 7. ΠΟΡΤΑΛ ΑΠΟΣТОΛΕΑ (ADMIN / TEACHER) ---
elif st.session_state["user_role"] in ["Admin", "Teacher"]:
    st.sidebar.title("⚙️ Διαχείριση Αποστολών")
    st.sidebar.write(f"👤 Σύνδεση: **{st.session_state['user_info']['name']}**")
    st.sidebar.write(f"🔰 Ρόλος: **{st.session_state['user_info']['role']}**")
    if st.sidebar.button("🚪 Αποσύνδεση"):
        logout()

    if st.session_state["user_role"] == "Admin":
        admin_tab1, admin_tab2 = st.tabs(["📤 Αποστολή Μηνύματος", "📁 Εισαγωγή Δεδομένων Excel (Admin Only)"])
    else:
        admin_tab1 = st.container()

    # TAB 1: ΑΠΟΣТОΛΗ ΜΗΝΥΜΑΤΩΝ
    with admin_tab1:
        st.header("📤 Σύνταξη & Αποστολή Νέου Μηνύματος")

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
            
            send_push = st.checkbox("🔔 Αποστολή και ως Push Notification (OneSignal)", value=True)
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
                        insert_query = """
                            INSERT INTO Announcements (Title, Content, TargetAudience, ClassID, SentBy, CreatedAt)
                            VALUES (?, ?, ?, ?, ?, GETDATE())
                        """
                        cursor.execute(insert_query, (title, content, target_audience, class_id, st.session_state['user_info']['name']))
                        conn.commit()
                        conn.close()
                        st.success("✅ Το μήνυμα καταχωρήθηκε στη βάση!")

                        if send_push:
                            if send_onesignal_notification(title, content):
                                st.info("🔔 Η ειδοποίηση Push απεστάλη επιτυχώς μέσω OneSignal!")
                            else:
                                st.error("❌ Αποτυχία αποστολής Push Notification.")

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

    # TAB 2: ΕΙΣΑΓΩΓΗ EXCEL (ΜΟΝΟ ΓΙΑ ADMIN)
    if st.session_state["user_role"] == "Admin":
        with admin_tab2:
            st.header("📊 Μαζική Εισαγωγή Μαθητών & Γονέων από Excel")
            uploaded_file = st.file_uploader("Μεταφόρτωση Αρχείου Excel", type=["xlsx", "xls"])

            if uploaded_file is not None:
                df = pd.read_excel(uploaded_file)
                st.subheader("Προεπισκόπηση Δεδομένων")
                st.dataframe(df.head(), use_container_width=True)

                if st.button("📥 Εισαγωγή στη Βάση Δεδομένων"):
                    conn = get_db_connection()
                    if conn:
                        cursor = conn.cursor()
                        imported_students = 0
                        imported_parents = 0

                        try:
                            for idx, row in df.iterrows():
                                class_name = str(row['ClassName']).strip()
                                student_fn = str(row['StudentFirstName']).strip()
                                student_ln = str(row['StudentLastName']).strip()

                                # 1. Τμήμα
                                cursor.execute("SELECT ClassID FROM Classes WHERE ClassName = ?", (class_name,))
                                class_row = cursor.fetchone()
                                if class_row:
                                    class_id = class_row[0]
                                else:
                                    cursor.execute("INSERT INTO Classes (ClassName, AcademicYear) VALUES (?, '2025-2026')", (class_name,))
                                    cursor.execute("SELECT @@IDENTITY")
                                    class_id = cursor.fetchone()[0]

                                # 2. Μαθητής
                                cursor.execute(
                                    "INSERT INTO Students (FirstName, LastName, ClassID) VALUES (?, ?, ?)",
                                    (student_fn, student_ln, class_id)
                                )
                                cursor.execute("SELECT @@IDENTITY")
                                student_id = cursor.fetchone()[0]
                                imported_students += 1

                                # 3. Γονέας 1
                                p1_fn = str(row.get('Parent1_FirstName', '')).strip()
                                p1_ln = str(row.get('Parent1_LastName', '')).strip()
                                raw_p1 = row.get('Parent1_Phone', '')
                                p1_phone = str(int(raw_p1)).strip() if pd.notnull(raw_p1) and str(raw_p1).replace('.0','').isdigit() else str(raw_p1).strip()

                                if p1_phone and p1_phone.lower() != 'nan':
                                    cursor.execute("SELECT ParentID FROM Parents WHERE Phone = ?", (p1_phone,))
                                    p1_row = cursor.fetchone()
                                    if p1_row:
                                        p1_id = p1_row[0]
                                    else:
                                        cursor.execute(
                                            "INSERT INTO Parents (FirstName, LastName, Phone, PasswordHash) VALUES (?, ?, ?, ?)",
                                            (p1_fn, p1_ln, p1_phone, p1_phone)
                                        )
                                        cursor.execute("SELECT @@IDENTITY")
                                        p1_id = cursor.fetchone()[0]
                                        imported_parents += 1

                                    cursor.execute(
                                        "IF NOT EXISTS (SELECT 1 FROM StudentParents WHERE StudentID=? AND ParentID=?) INSERT INTO StudentParents (StudentID, ParentID) VALUES (?, ?)",
                                        (student_id, p1_id, student_id, p1_id)
                                    )

                                # 4. Γονέας 2
                                p2_fn = str(row.get('Parent2_FirstName', '')).strip()
                                p2_ln = str(row.get('Parent2_LastName', '')).strip()
                                raw_p2 = row.get('Parent2_Phone', '')
                                p2_phone = str(int(raw_p2)).strip() if pd.notnull(raw_p2) and str(raw_p2).replace('.0','').isdigit() else str(raw_p2).strip()

                                if p2_phone and p2_phone.lower() != 'nan':
                                    cursor.execute("SELECT ParentID FROM Parents WHERE Phone = ?", (p2_phone,))
                                    p2_row = cursor.fetchone()
                                    if p2_row:
                                        p2_id = p2_row[0]
                                    else:
                                        cursor.execute(
                                            "INSERT INTO Parents (FirstName, LastName, Phone, PasswordHash) VALUES (?, ?, ?, ?)",
                                            (p2_fn, p2_ln, p2_phone, p2_phone)
                                        )
                                        cursor.execute("SELECT @@IDENTITY")
                                        p2_id = cursor.fetchone()[0]
                                        imported_parents += 1

                                    cursor.execute(
                                        "IF NOT EXISTS (SELECT 1 FROM StudentParents WHERE StudentID=? AND ParentID=?) INSERT INTO StudentParents (StudentID, ParentID) VALUES (?, ?)",
                                        (student_id, p2_id, student_id, p2_id)
                                    )

                            conn.commit()
                            st.success(f"🎉 Επιτυχής εισαγωγή! Προστέθηκαν {imported_students} μαθητές και {imported_parents} νέοι γονείς.")
                        except Exception as e:
                            conn.rollback()
                            st.error(f"❌ Σφάλμα κατά την εισαγωγή: {e}")
                        finally:
                            conn.close()

# --- 8. ΠΟΡΤΑΛ ΓΟΝΕΑ ---
elif st.session_state["user_role"] == "Parent":
    parent_id = st.session_state["user_info"]["id"]
    parent_name = st.session_state["user_info"]["name"]

    # Ενεργοποίηση διαλόγου ειδοποιήσεων OneSignal
    inject_onesignal_script()

    st.sidebar.title("💬 Portal Μηνυμάτων")
    st.sidebar.write(f"👤 Γονέας: **{parent_name}**")
    if st.sidebar.button("🚪 Αποσύνδεση"):
        logout()

    st.header("📥 Εισερχόμενα Μηνύματα")

    conn = get_db_connection()
    if conn:
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
