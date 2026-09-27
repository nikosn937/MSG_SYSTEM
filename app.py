import urllib.parse
import pandas as pd
import pyodbc
import requests
import streamlit as st

# --- 1. ΡΥΘΜΙΣΗ ΣΕΛΙΔΑΣ ---
st.set_page_config(
    page_title="Σχολικό Portal Μηνυμάτων", page_icon="💬", layout="wide"
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


# --- 3. ΑΠΟΣТОΛΗ PUSH NOTIFICATION ΜΕΣΩ ONESIGNAL API ---
def send_onesignal_notification(
    school_name, title, message_text, target_phones=None
):
  """Στέλνει εξατομικευμένο Push Notification ανά τηλέφωνο γονέα

  περιλαμβάνοντας το όνομα σχολείου στον τίτλο.
  """
  app_id = st.secrets.get("ONESIGNAL_APP_ID")
  rest_key = st.secrets.get("ONESIGNAL_REST_KEY")

  if not app_id or not rest_key:
    st.warning("⚠️ Λείπουν τα διαπιστευτήρια του OneSignal στα Secrets.")
    return False

  headers = {
      "Content-Type": "application/json; charset=utf-8",
      "Authorization": f"Basic {rest_key}",
  }

  base_url = "https://msgsys.streamlit.app"

  # Διαμόρφωση τίτλου με το όνομα σχολείου
  full_title = (
      f"[{school_name}] {title}" if school_name.strip() else f"{title}"
  )

  if target_phones and len(target_phones) > 0:
    success_count = 0
    for phone in target_phones:
      payload = {
          "app_id": app_id,
          "headings": {"el": full_title, "en": full_title},
          "contents": {"el": message_text, "en": message_text},
          "url": f"{base_url}/?auto_phone={phone}",
          "include_aliases": {"external_id": [phone]},
          "target_channel": "push",
      }
      try:
        res = requests.post(
            "https://onesignal.com/api/v1/notifications",
            headers=headers,
            json=payload,
            timeout=5,
        )
        if res.status_code == 200:
          success_count += 1
      except Exception:
        pass
    return success_count > 0
  else:
    st.warning("⚠️ Δεν βρέθηκαν τηλέφωνα παραληπτών για την αποστολή Push.")
    return False


# --- ΒΟΗΘΗΤΙΚΗ ΣΥΝΑΡΤΗΣΗ ΕΛΕΓΧΟΥ ΕΓΓΡΑΦΗΣ ONESIGNAL ---
def check_onesignal_registration(phone):
  """Ελέγχει αν το τηλέφωνο του γονέα έχει ΕΝΕΡΓΗ συνδρομή στο OneSignal."""
  app_id = st.secrets.get("ONESIGNAL_APP_ID")
  rest_key = st.secrets.get("ONESIGNAL_REST_KEY")

  if not app_id or not rest_key or not phone:
    return False

  headers = {
      "Content-Type": "application/json; charset=utf-8",
      "Authorization": f"Basic {rest_key}",
  }

  try:
    url = f"https://onesignal.com/api/v1/apps/{app_id}/users/by/external_id/{phone}"
    res = requests.get(url, headers=headers, timeout=3)
    if res.status_code == 200:
      data = res.json()
      subscriptions = data.get("subscriptions", [])

      for sub in subscriptions:
        if sub.get("enabled", False) is True and not sub.get("opted_out", False):
          return True
  except Exception:
    pass

  return False


# --- 4. SESSION STATE & AUTO-LOGIN VIA URL ---
if "user_role" not in st.session_state:
  st.session_state["user_role"] = None
if "user_info" not in st.session_state:
  st.session_state["user_info"] = None

query_params = st.query_params
if "auto_phone" in query_params and st.session_state["user_role"] is None:
  auto_phone = (
      str(query_params["auto_phone"])
      .strip()
      .replace("+357", "")
      .replace(" ", "")
      .replace("-", "")
  )

  conn = get_db_connection()
  if conn:
    cursor = conn.cursor()
    query = """
            SELECT ParentID, FirstName, LastName, Phone 
            FROM Parents 
            WHERE LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(Phone, '+357', ''), ' ', ''), '-', ''))) = ? 
              AND (IsActive = 1 OR IsActive IS NULL)
        """
    cursor.execute(query, (auto_phone,))
    parent = cursor.fetchone()
    conn.close()

    if parent:
      st.session_state["user_role"] = "Parent"
      st.session_state["user_info"] = {
          "id": parent[0],
          "name": f"{parent[1]} {parent[2]}",
          "phone": auto_phone,
      }
      st.rerun()


def logout():
  st.session_state["user_role"] = None
  st.session_state["user_info"] = None
  st.query_params.clear()
  st.rerun()


# --- 5. ΟΘΟΝΗ ΣΥΝΔΕΣΗΣ (LOGIN) ---
if st.session_state["user_role"] is None:
  st.title("💬 Portal Μηνυμάτων Σχολείου")
  st.subheader("Σύνδεση στο Σύστημα")

  tab_admin, tab_parent = st.tabs(
      ["👨‍🏫 Αποστολέας / Εκπαιδευτικός", "👨‍👩‍👧 Γονέας / Κηδεμόνας"]
  )

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
                "role": user[2],
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
        clean_phone = (
            phone.strip().replace("+357", "").replace(" ", "").replace("-", "")
        )
        clean_pass = (
            password.strip()
            .replace("+357", "")
            .replace(" ", "")
            .replace("-", "")
        )

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
                "phone": clean_phone,
            }
            st.success(f"Καλώς ήρθατε, {parent[1]}!")
            st.rerun()
          else:
            st.error(
                "❌ Δεν βρέθηκε ενεργός λογαριασμός γονέα με αυτά τα στοιχεία."
            )

# --- 6. ΠΟΡΤΑΛ ΑΠΟΣТОΛΕΑ (ADMIN / TEACHER) ---
elif st.session_state["user_role"] in ["Admin", "Teacher"]:
  st.sidebar.title("⚙️ Διαχείριση Αποστολών")
  st.sidebar.write(f"👤 Σύνδεση: **{st.session_state['user_info']['name']}**")
  st.sidebar.write(f"🔰 Ρόλος: **{st.session_state['user_info']['role']}**")
  if st.sidebar.button("🚪 Αποσύνδεση"):
    logout()

  if st.session_state["user_role"] == "Admin":
    admin_tab1, admin_tab2 = st.tabs([
        "📤 Αποστολή Μηνύματος",
        "📁 Εισαγωγή Δεδομένων Excel (Admin Only)",
    ])
  else:
    admin_tab1 = st.container()

  # TAB 1: ΑΠΟΣТОΛΗ ΜΗΝΥΜΑΤΩΝ
  with admin_tab1:
    st.header("📤 Σύνταξη & Αποστολή Νέου Μηνύματος")

    # Ανάκτηση τμημάτων και μαθητών για τα φίλτρα
    classes_dict = {}
    students_list = []

    conn = get_db_connection()
    if conn:
      cursor = conn.cursor()
      cursor.execute("SELECT ClassID, ClassName FROM Classes ORDER BY ClassName")
      for cid, cname in cursor.fetchall():
        classes_dict[cname] = cid

      cursor.execute("""
                SELECT S.StudentID, S.FirstName, S.LastName, C.ClassName 
                FROM Students S 
                LEFT JOIN Classes C ON S.ClassID = C.ClassID 
                ORDER BY C.ClassName, S.LastName, S.FirstName
            """)
      students_list = cursor.fetchall()
      conn.close()

    # 1. Πεδίο: Όνομα Σχολείου
    school_name = st.text_input(
        "Όνομα Σχολείου", placeholder="π.χ. 1ο Γυμνάσιο / Λύκειο..."
    )

    # 2. Πεδίο: Θέμα / Τίτλος
    title = st.text_input(
        "Θέμα / Τίτλος Μηνύματος",
        placeholder="π.χ. Ενημέρωση για την Αυριανή Εκδρομή",
    )

    # 🎯 3. Επιλογή Τύπου Παραληπτών
    recipient_type = st.radio(
        "🎯 Επιλογή Παραληπτών:",
        [
            "🌐 Όλο το Σχολείο (ALL)",
            "🎓 Ανά Τάξη (π.χ. Α' Τάξη)",
            "🏫 Ανά Τμήμα (π.χ. Α1)",
            "👤 Συγκεκριμένοι Μαθητές",
        ],
        horizontal=True,
    )

    selected_class_id = None
    selected_grade_prefix = None
    selected_student_ids = []

    if recipient_type == "🎓 Ανά Τάξη (π.χ. Α' Τάξη)":
      selected_grade_prefix = st.selectbox(
          "Επιλέξτε Τάξη:",
          ["Α", "Β", "Γ", "Δ", "Ε", "ΣΤ"],
          format_func=lambda x: f"Τάξη {x}",
      )
    elif recipient_type == "🏫 Ανά Τμήμα (π.χ. Α1)":
      selected_class_name = st.selectbox(
          "Επιλέξτε Τμήμα:", list(classes_dict.keys())
      )
      selected_class_id = classes_dict.get(selected_class_name)
    elif recipient_type == "👤 Συγκεκριμένοι Μαθητές":
      student_options = {
          f"{s[3]} - {s[2]} {s[1]} (ID: {s[0]})": s[0] for s in students_list
      }
      selected_student_names = st.multiselect(
          "Επιλέξτε Μαθητή/ές:", list(student_options.keys())
      )
      selected_student_ids = [
          student_options[name] for name in selected_student_names
      ]

    content = st.text_area("Περιεχόμενο Μηνύματος", height=150)
    send_push = st.checkbox(
        "🔔 Αποστολή και ως Push Notification (OneSignal)", value=True
    )

    if st.button("🚀 Αποστολή Μηνύματος", use_container_width=True):
      if not title or not content:
        st.warning("Παρακαλώ συμπληρώστε τίτλο και περιεχόμενο.")
      elif (
          recipient_type == "👤 Συγκεκριμένοι Μαθητές"
          and not selected_student_ids
      ):
        st.warning("Παρακαλώ επιλέξτε τουλάχιστον έναν μαθητή.")
      else:
        # Υπολογισμός TargetAudience & ClassID για τη Βάση
        if recipient_type == "🌐 Όλο το Σχολείο (ALL)":
          target_audience = "ALL"
          db_class_id = None
        elif recipient_type == "🎓 Ανά Τάξη (π.χ. Α' Τάξη)":
          target_audience = f"GRADE_{selected_grade_prefix}"
          db_class_id = None
        elif recipient_type == "🏫 Ανά Τμήμα (π.χ. Α1)":
          target_audience = "CLASS"
          db_class_id = selected_class_id
        else:
          target_audience = "STUDENTS"
          db_class_id = None

        conn = get_db_connection()
        if conn:
          cursor = conn.cursor()
          # 1. Αποθήκευση Ανακοίνωσης
          insert_query = """
                        INSERT INTO Announcements (Title, Content, TargetAudience, ClassID, SentBy, CreatedAt)
                        VALUES (?, ?, ?, ?, ?, GETDATE());
                    """
          cursor.execute(
              insert_query,
              (
                  title,
                  content,
                  target_audience,
                  db_class_id,
                  st.session_state["user_info"]["name"],
              ),
          )
          conn.commit()

          # Ανάκτηση ID της νέας ανακοίνωσης
          cursor.execute("SELECT @@IDENTITY")
          announcement_id = cursor.fetchone()[0]

          # 2. Εύρεση τηλεφώνων γονέων ανάλογα με την επιλογή
          target_phones = []

          if target_audience == "ALL":
            query_phones = """
                            SELECT DISTINCT LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(Phone, '+357', ''), ' ', ''), '-', '')))
                            FROM Parents WHERE IsActive = 1 OR IsActive IS NULL
                        """
            cursor.execute(query_phones)
            target_phones = [r[0] for r in cursor.fetchall() if r[0]]

          elif target_audience.startswith("GRADE_"):
            prefix = selected_grade_prefix + "%"
            query_phones = """
                            SELECT DISTINCT LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(P.Phone, '+357', ''), ' ', ''), '-', '')))
                            FROM Parents P
                            JOIN StudentParents SP ON P.ParentID = SP.ParentID
                            JOIN Students S ON SP.StudentID = S.StudentID
                            JOIN Classes C ON S.ClassID = C.ClassID
                            WHERE C.ClassName LIKE ?
                        """
            cursor.execute(query_phones, (prefix,))
            target_phones = [r[0] for r in cursor.fetchall() if r[0]]

          elif target_audience == "CLASS":
            query_phones = """
                            SELECT DISTINCT LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(P.Phone, '+357', ''), ' ', ''), '-', '')))
                            FROM Parents P
                            JOIN StudentParents SP ON P.ParentID = SP.ParentID
                            JOIN Students S ON SP.StudentID = S.StudentID
                            WHERE S.ClassID = ?
                        """
            cursor.execute(query_phones, (db_class_id,))
            target_phones = [r[0] for r in cursor.fetchall() if r[0]]

          elif target_audience == "STUDENTS":
            for st_id in selected_student_ids:
              cursor.execute(
                  "INSERT INTO AnnouncementStudents (AnnouncementID, StudentID)"
                  " VALUES (?, ?)",
                  (announcement_id, st_id),
              )

            placeholders = ",".join(["?"] * len(selected_student_ids))
            query_phones = f"""
                            SELECT DISTINCT LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(P.Phone, '+357', ''), ' ', ''), '-', '')))
                            FROM Parents P
                            JOIN StudentParents SP ON P.ParentID = SP.ParentID
                            WHERE SP.StudentID IN ({placeholders})
                        """
            cursor.execute(query_phones, selected_student_ids)
            target_phones = [r[0] for r in cursor.fetchall() if r[0]]

            conn.commit()

          conn.close()
          st.success("✅ Το μήνυμα καταχωρήθηκε επιτυχώς στη βάση!")

          if send_push:
            success = send_onesignal_notification(
                school_name, title, content, target_phones
            )
            if success:
              st.info(
                  "🔔 Η ειδοποίηση Push απεστάλη επιτυχώς στους γονείς μέσω"
                  " OneSignal!"
              )
            else:
              st.error("❌ Αποτυχία αποστολής Push Notification.")

    st.markdown("---")
    st.subheader("📜 Ιστορικό Απεσταλμένων Μηνύμάτων")
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
      uploaded_file = st.file_uploader(
          "Μεταφόρτωση Αρχείου Excel", type=["xlsx", "xls"]
      )

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
                class_name = str(row["ClassName"]).strip()
                student_fn = str(row["StudentFirstName"]).strip()
                student_ln = str(row["StudentLastName"]).strip()

                cursor.execute(
                    "SELECT ClassID FROM Classes WHERE ClassName = ?",
                    (class_name,),
                )
                class_row = cursor.fetchone()
                if class_row:
                  class_id = class_row[0]
                else:
                  cursor.execute(
                      "INSERT INTO Classes (ClassName, AcademicYear) VALUES (?,"
                      " '2025-2026')",
                      (class_name,),
                  )
                  cursor.execute("SELECT @@IDENTITY")
                  class_id = cursor.fetchone()[0]

                cursor.execute(
                    "INSERT INTO Students (FirstName, LastName, ClassID) VALUES"
                    " (?, ?, ?)",
                    (student_fn, student_ln, class_id),
                )
                cursor.execute("SELECT @@IDENTITY")
                student_id = cursor.fetchone()[0]
                imported_students += 1

                p1_fn = str(row.get("Parent1_FirstName", "")).strip()
                p1_ln = str(row.get("Parent1_LastName", "")).strip()
                raw_p1 = row.get("Parent1_Phone", "")
                p1_phone = (
                    str(int(raw_p1)).strip()
                    if pd.notnull(raw_p1)
                    and str(raw_p1).replace(".0", "").isdigit()
                    else str(raw_p1).strip()
                )

                if p1_phone and p1_phone.lower() != "nan":
                  cursor.execute(
                      "SELECT ParentID FROM Parents WHERE Phone = ?",
                      (p1_phone,),
                  )
                  p1_row = cursor.fetchone()
                  if p1_row:
                    p1_id = p1_row[0]
                  else:
                    cursor.execute(
                        "INSERT INTO Parents (FirstName, LastName, Phone,"
                        " PasswordHash) VALUES (?, ?, ?, ?)",
                        (p1_fn, p1_ln, p1_phone, p1_phone),
                    )
                    cursor.execute("SELECT @@IDENTITY")
                    p1_id = cursor.fetchone()[0]
                    imported_parents += 1

                  cursor.execute(
                      "IF NOT EXISTS (SELECT 1 FROM StudentParents WHERE"
                      " StudentID=? AND ParentID=?) INSERT INTO StudentParents"
                      " (StudentID, ParentID) VALUES (?, ?)",
                      (student_id, p1_id, student_id, p1_id),
                  )

                p2_fn = str(row.get("Parent2_FirstName", "")).strip()
                p2_ln = str(row.get("Parent2_LastName", "")).strip()
                raw_p2 = row.get("Parent2_Phone", "")
                p2_phone = (
                    str(int(raw_p2)).strip()
                    if pd.notnull(raw_p2)
                    and str(raw_p2).replace(".0", "").isdigit()
                    else str(raw_p2).strip()
                )

                if p2_phone and p2_phone.lower() != "nan":
                  cursor.execute(
                      "SELECT ParentID FROM Parents WHERE Phone = ?",
                      (p2_phone,),
                  )
                  p2_row = cursor.fetchone()
                  if p2_row:
                    p2_id = p2_row[0]
                  else:
                    cursor.execute(
                        "INSERT INTO Parents (FirstName, LastName, Phone,"
                        " PasswordHash) VALUES (?, ?, ?, ?)",
                        (p2_fn, p2_ln, p2_phone, p2_phone),
                    )
                    cursor.execute("SELECT @@IDENTITY")
                    p2_id = cursor.fetchone()[0]
                    imported_parents += 1

                  cursor.execute(
                      "IF NOT EXISTS (SELECT 1 FROM StudentParents WHERE"
                      " StudentID=? AND ParentID=?) INSERT INTO StudentParents"
                      " (StudentID, ParentID) VALUES (?, ?)",
                      (student_id, p2_id, student_id, p2_id),
                  )

              conn.commit()
              st.success(
                  f"🎉 Επιτυχής εισαγωγή! Προστέθηκαν {imported_students}"
                  f" μαθητές και {imported_parents} νέοι γονείς."
              )
            except Exception as e:
              conn.rollback()
              st.error(f"❌ Σφάλμα κατά την εισαγωγή: {e}")
            finally:
              conn.close()

# --- 7. ΠΟΡΤΑΛ ΓΟΝΕΑ ---
elif st.session_state["user_role"] == "Parent":
  parent_id = st.session_state["user_info"]["id"]
  parent_name = st.session_state["user_info"]["name"]
  parent_phone = st.session_state["user_info"].get("phone", "")

  st.sidebar.title("💬 Portal Μηνυμάτων")
  st.sidebar.write(f"👤 Γονέας: **{parent_name}**")

  vercel_bridge_url = f"https://msg1-system.vercel.app/?phone={urllib.parse.quote(parent_phone)}"
  is_subscribed = check_onesignal_registration(parent_phone)

  if not is_subscribed:
    st.info(
        "🔔 **Ενεργοποίηση Ειδοποιήσεων:** Για να λαμβάνετε άμεσες"
        " ειδοποιήσεις στο κινητό σας όταν στέλνει το σχολείο νέα μήνυματα,"
        " πατήστε το παρακάτω κουμπί:"
    )
    st.link_button(
        "📲 Ενεργοποίηση Ειδοποιήσεων στο Κινητό",
        vercel_bridge_url,
        use_container_width=True,
    )
    st.markdown("---")

  st.sidebar.markdown("---")
  st.sidebar.caption("🔔 **Ειδοποιήσεις**")
  st.sidebar.link_button(
      "📲 Ρυθμίσεις Ειδοποιήσεων", vercel_bridge_url, use_container_width=True
  )

  st.sidebar.markdown("---")
  if st.sidebar.button("🚪 Αποσύνδεση"):
    logout()

  # --- ΚΥΡΙΩΣ ΟΘΟΝΗ: ΕΙΣΕΡΧΟΜΕΝΑ ΜΗΝΥΜΑΤΑ ---
  st.header("📥 Εισερχόμενα Μηνύματα")

  conn = get_db_connection()
  if conn:
    # 1. ΑΥΤΟΜΑΤΗ ΣΗΜΑΝΣΗ ΟΛΩΝ ΤΩΝ ΝΕΩΝ ΜΗΝΥΜΑΤΩΝ ΩΣ ΑΝΑΓΝΩΣΜΕΝΑ
    auto_read_query = """
            INSERT INTO ReadReceipts (AnnouncementID, ParentID, ReadAt)
            SELECT A.AnnouncementID, ?, GETDATE()
            FROM Announcements A
            WHERE (
                A.TargetAudience = 'ALL' 
                OR (A.TargetAudience LIKE 'GRADE_%' AND A.TargetAudience = (
                    SELECT 'GRADE_' + SUBSTRING(C.ClassName, 1, 1) 
                    FROM Students S JOIN Classes C ON S.ClassID = C.ClassID 
                    JOIN StudentParents SP ON S.StudentID = SP.StudentID WHERE SP.ParentID = ?
                ))
                OR A.ClassID IN (
                    SELECT S.ClassID FROM Students S JOIN StudentParents SP ON S.StudentID = SP.StudentID WHERE SP.ParentID = ?
                )
                OR A.AnnouncementID IN (
                    SELECT ANS.AnnouncementID FROM AnnouncementStudents ANS 
                    JOIN StudentParents SP ON ANS.StudentID = SP.StudentID WHERE SP.ParentID = ?
                )
            )
            AND NOT EXISTS (
                SELECT 1 FROM ReadReceipts R WHERE R.AnnouncementID = A.AnnouncementID AND R.ParentID = ?
            )
        """
    try:
      cur = conn.cursor()
      cur.execute(
          auto_read_query,
          (parent_id, parent_id, parent_id, parent_id, parent_id),
      )
      conn.commit()
    except Exception:
      pass

    # 2. ΑΝΑΚΤΗΣΗ ΜΗΝΥΜΑΤΩΝ ΠΟΥ ΑΦΟΡΟΥΝ ΤΟΝ ΓΟΝΕΑ
    query_messages = """
            SELECT DISTINCT A.AnnouncementID, A.Title, A.Content, A.SentBy, A.CreatedAt, C.ClassName, R.ReadAt
            FROM Announcements A
            LEFT JOIN Classes C ON A.ClassID = C.ClassID
            LEFT JOIN ReadReceipts R ON A.AnnouncementID = R.AnnouncementID AND R.ParentID = ?
            WHERE A.TargetAudience = 'ALL' 
               OR (A.TargetAudience LIKE 'GRADE_%' AND A.TargetAudience IN (
                   SELECT 'GRADE_' + LEFT(C2.ClassName, 1)
                   FROM Students S2 
                   JOIN Classes C2 ON S2.ClassID = C2.ClassID
                   JOIN StudentParents SP2 ON S2.StudentID = SP2.StudentID
                   WHERE SP2.ParentID = ?
               ))
               OR A.ClassID IN (
                   SELECT S.ClassID 
                   FROM Students S
                   JOIN StudentParents SP ON S.StudentID = SP.StudentID
                   WHERE SP.ParentID = ?
               )
               OR A.AnnouncementID IN (
                   SELECT ANS.AnnouncementID 
                   FROM AnnouncementStudents ANS
                   JOIN StudentParents SP ON ANS.StudentID = SP.StudentID
                   WHERE SP.ParentID = ?
               )
            ORDER BY A.CreatedAt DESC
        """
    df_msgs = pd.read_sql(
        query_messages,
        conn,
        params=[parent_id, parent_id, parent_id, parent_id],
    )
    conn.close()

    if not df_msgs.empty:
      for idx, row in df_msgs.iterrows():
        is_latest = idx == 0
        with st.expander(
            f"📩 {row['Title']} ({row['CreatedAt']})", expanded=is_latest
        ):
          st.write(row["Content"])
          st.caption(
              f"Αποστολέας: {row['SentBy']} | Προορισμός:"
              f" {row['ClassName'] if row['ClassName'] else 'Στοχευμένο/Γενικό'}"
          )
    else:
      st.info("Δεν υπάρχουν εισερχόμενα μηνύματα.")
