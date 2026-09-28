from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import pandas as pd
import pyodbc
import requests
import time
import streamlit as st
from streamlit_tree_select import tree_select

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


# --- 3. ΒΟΗΘΗΤΙΚΗ ΣΥΝΑΡΤΗΣΗ ΕΛΕΓΧΟΥ ΕΓΓΡΑΦΗΣ ONESIGNAL ---
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
    clean_phone = (
        str(phone).strip().replace("+357", "").replace(" ", "").replace("-", "")
    )
    url = f"https://onesignal.com/api/v1/apps/{app_id}/users/by/external_id/{clean_phone}"
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


# --- 4. ΑΠΟΣΤΟΛΗ PUSH NOTIFICATION ΜΕΣΩ ONESIGNAL API (PARALLEL) ---
def send_onesignal_notification(
    school_name, title, message_text, target_phones=None
):
  """Στέλνει Push Notifications παράλληλα για ταχύτητα και 100% λειτουργικό auto-login."""
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
  full_title = (
      f"[{school_name}] {title}" if school_name.strip() else f"{title}"
  )

  if target_phones and len(target_phones) > 0:
    unique_phones = list(
        set(
            str(p).strip().replace("+357", "").replace(" ", "").replace("-", "")
            for p in target_phones
            if p
        )
    )

    # Εσωτερική συνάρτηση για αποστολή σε 1 γονέα
    def send_single_push(phone):
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
        return res.status_code == 200
      except Exception:
        return False

    # Εκτέλεση των κλήσεων παράλληλα μέσω Threads
    with ThreadPoolExecutor(max_workers=20) as executor:
      results = list(executor.map(send_single_push, unique_phones))

    return any(results)
  else:
    st.warning("⚠️ Δεν βρέθηκαν τηλέφωνα παραληπτών για την αποστολή Push.")
    return False


# --- 5. SESSION STATE & AUTO-LOGIN VIA URL ---
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


# --- 6. ΟΘΟΝΗ ΣΥΝΔΕΣΗΣ (LOGIN) ---
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

# --- 7. ΠΟΡΤΑΛ ΑΠΟΣΤΟΛΕΑ (ADMIN / TEACHER) ---
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

  # TAB 1: ΑΠΟΣΤΟΛΗ ΜΗΝΥΜΑΤΩΝ
  with admin_tab1:
    st.header("📤 Σύνταξη & Αποστολή Νέου Μηνύματος")

    school_name = st.text_input(
        "Όνομα Σχολείου", placeholder="π.χ. 1ο Γυμνάσιο / Λύκειο..."
    )
    title = st.text_input(
        "Θέμα / Τίτλος Μηνύματος",
        placeholder="π.χ. Ενημέρωση για την Αυριανή Εκδρομή",
    )

    st.markdown("### 🎯 Επιλογή Παραληπτών")

    nodes = []

    conn = get_db_connection()
    if conn:
      query_tree = """
            SELECT DISTINCT S.StudentID, S.FirstName, S.LastName, C.ClassID, C.ClassName
            FROM Students S
            JOIN Classes C ON S.ClassID = C.ClassID
            ORDER BY C.ClassName, S.LastName, S.FirstName
        """
      df_students = pd.read_sql(query_tree, conn)
      conn.close()

      if not df_students.empty:
        df_students["Grade"] = df_students["ClassName"].apply(
            lambda x: str(x)[0].upper() if x else "Άλλο"
        )

        students_node = {
            "label": "🎓 Μαθητές (Όλοι)",
            "value": "ALL_STUDENTS",
            "children": [],
        }

        for grade, group_grade in df_students.groupby("Grade"):
          grade_node = {
              "label": f"Τάξη {grade}",
              "value": f"GRADE_{grade}",
              "children": [],
          }

          for class_name, group_class in group_grade.groupby("ClassName"):
            class_id = group_class["ClassID"].iloc[0]
            class_node = {
                "label": f"Τμήμα {class_name}",
                "value": f"CLASS_{class_id}",
                "children": [],
            }

            for _, row in group_class.iterrows():
              student_node = {
                  "label": (
                      f"{row['StudentID']} - {row['LastName']}"
                      f" {row['FirstName']}"
                  ),
                  "value": f"STUDENT_{row['StudentID']}",
              }
              class_node["children"].append(student_node)

            grade_node["children"].append(class_node)

          students_node["children"].append(grade_node)

        nodes.append(students_node)

    return_select = tree_select(
        nodes, checked=[], expand_on_click=True, no_cascade=False
    )
    selected_values = return_select.get("checked", [])

    content = st.text_area("Περιεχόμενο Μηνύματος", height=150)

    if st.button("🚀 Αποστολή Μηνύματος", use_container_width=True):
      if not title or not content:
        st.warning("Παρακαλώ συμπληρώστε τίτλο και περιεχόμενο.")
      elif not selected_values:
        st.warning(
            "Παρακαλώ επιλέξτε τουλάχιστον έναν παραλήπτη από το δέντρο."
        )
      else:
        selected_student_ids = []

        if "ALL_STUDENTS" in selected_values:
          target_audience = "ALL"
          db_class_id = None
        else:
          target_audience = "STUDENTS"
          db_class_id = None

          for val in selected_values:
            if str(val).startswith("STUDENT_"):
              st_id = int(str(val).replace("STUDENT_", ""))
              selected_student_ids.append(st_id)

        selected_student_ids = list(set(selected_student_ids))

        conn = get_db_connection()
        if conn:
          cursor = conn.cursor()

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

          cursor.execute("SELECT @@IDENTITY")
          announcement_id = cursor.fetchone()[0]

          target_phones = []

          if target_audience == "ALL":
            query_phones = """
                            SELECT DISTINCT LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(Phone, '+357', ''), ' ', ''), '-', '')))
                            FROM Parents WHERE IsActive = 1 OR IsActive IS NULL
                        """
            cursor.execute(query_phones)
            target_phones = [r[0] for r in cursor.fetchall() if r[0]]
          else:
            for st_id in selected_student_ids:
              cursor.execute(
                  "INSERT INTO AnnouncementStudents (AnnouncementID,"
                  " StudentID) VALUES (?, ?)",
                  (announcement_id, st_id),
              )

            if selected_student_ids:
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

          success = send_onesignal_notification(
              school_name, title, content, target_phones
          )
          if success:
            st.info("🔔 Η ειδοποίηση Push απεστάλη επιτυχώς στους γονείς!")
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

  # --- TAB 2: ΕΙΣΑΓΩΓΗ EXCEL (SMART SYNC) ---
  if st.session_state["user_role"] == "Admin":
    with admin_tab2:
      st.header("📊 Μαζική Εισαγωγή & Ενημέρωση Δεδομένων από Excel")
      uploaded_file = st.file_uploader(
          "Μεταφόρτωση Αρχείου Excel", type=["xlsx", "xls"]
      )

      if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)
        st.dataframe(df.head(), use_container_width=True)

        if st.button(
            "🔄 Συγχρονισμός Δεδομένων στη Βάση", use_container_width=True
        ):
          conn = get_db_connection()
          if conn:
            cursor = conn.cursor()
            new_students, existing_students, updated_parents, new_parents = (
                0,
                0,
                0,
                0,
            )

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
                    """
                                  SELECT StudentID FROM Students 
                                  WHERE FirstName = ? AND LastName = ? AND ClassID = ?
                              """,
                    (student_fn, student_ln, class_id),
                )
                student_row = cursor.fetchone()

                if student_row:
                  student_id = student_row[0]
                  existing_students += 1
                else:
                  cursor.execute(
                      "INSERT INTO Students (FirstName, LastName, ClassID)"
                      " VALUES (?, ?, ?)",
                      (student_fn, student_ln, class_id),
                  )
                  cursor.execute("SELECT @@IDENTITY")
                  student_id = cursor.fetchone()[0]
                  new_students += 1

                parents_data = [
                    (
                        row.get("Parent1_FirstName"),
                        row.get("Parent1_LastName"),
                        row.get("Parent1_Phone"),
                    ),
                    (
                        row.get("Parent2_FirstName"),
                        row.get("Parent2_LastName"),
                        row.get("Parent2_Phone"),
                    ),
                ]

                for p_fn, p_ln, raw_phone in parents_data:
                  if pd.notnull(raw_phone):
                    p_fn_str = str(p_fn).strip() if pd.notnull(p_fn) else ""
                    p_ln_str = str(p_ln).strip() if pd.notnull(p_ln) else ""

                    clean_phone = (
                        str(int(raw_phone)).strip()
                        if str(raw_phone).replace(".0", "").isdigit()
                        else str(raw_phone).strip()
                    )
                    clean_phone = (
                        clean_phone.replace("+357", "")
                        .replace(" ", "")
                        .replace("-", "")
                    )

                    if clean_phone and clean_phone.lower() != "nan":
                      cursor.execute(
                          """
                                              SELECT P.ParentID, P.Phone 
                                              FROM Parents P
                                              JOIN StudentParents SP ON P.ParentID = SP.ParentID
                                              WHERE SP.StudentID = ? AND P.FirstName = ? AND P.LastName = ?
                                          """,
                          (student_id, p_fn_str, p_ln_str),
                      )
                      parent_match = cursor.fetchone()

                      if parent_match:
                        parent_id, current_phone = (
                            parent_match[0],
                            parent_match[1],
                        )
                        if current_phone != clean_phone:
                          cursor.execute(
                              """
                                                      UPDATE Parents 
                                                      SET Phone = ?, PasswordHash = ? 
                                                      WHERE ParentID = ?
                                                  """,
                              (clean_phone, clean_phone, parent_id),
                          )
                          updated_parents += 1
                      else:
                        cursor.execute(
                            "SELECT ParentID FROM Parents WHERE Phone = ?",
                            (clean_phone,),
                        )
                        existing_phone_row = cursor.fetchone()

                        if existing_phone_row:
                          parent_id = existing_phone_row[0]
                        else:
                          cursor.execute(
                              """
                                                      INSERT INTO Parents (FirstName, LastName, Phone, PasswordHash) 
                                                      VALUES (?, ?, ?, ?)
                                                  """,
                              (
                                  p_fn_str,
                                  p_ln_str,
                                  clean_phone,
                                  clean_phone,
                              ),
                          )
                          cursor.execute("SELECT @@IDENTITY")
                          parent_id = cursor.fetchone()[0]
                          new_parents += 1

                        cursor.execute(
                            """
                                                  IF NOT EXISTS (SELECT 1 FROM StudentParents WHERE StudentID=? AND ParentID=?)
                                                  INSERT INTO StudentParents (StudentID, ParentID) VALUES (?, ?)
                                              """,
                            (student_id, parent_id, student_id, parent_id),
                        )

              conn.commit()
              st.success("🎉 Ο συγχρονισμός ολοκληρώθηκε με επιτυχία!")
            except Exception as e:
              conn.rollback()
              st.error(f"❌ Σφάλμα: {e}")
            finally:
              conn.close()

# --- 8. ΠΟΡΤΑΛ ΓΟΝΕΑ ---
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

  st.header("📥 Εισερχόμενα Μηνύματα")

  conn = get_db_connection()
  if conn:
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
