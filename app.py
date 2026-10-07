from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import pandas as pd
import pymssql
import requests
import time
import streamlit as st
import streamlit.components.v1 as components
from streamlit_tree_select import tree_select


# --- 1. ΡΥΘΜΙΣΗ ΣΕΛΙΔΑΣ ---
st.set_page_config(
    page_title="Σχολικό Portal Μηνυμάτων", page_icon="💬", layout="wide"
)


# --- 2. ΣΥΝΔΕΣΗ ΜΕ ΑΠΟΜΑΚΡΥΣΜΕΝΟ SQL SERVER (FreeTDS) ---
def get_db_connection():
    try:
        server = st.secrets["DB_SERVER"]
        port = int(st.secrets.get("DB_PORT", 1433))
        database = st.secrets["DB_NAME"]
        user = st.secrets["DB_USER"]
        password = st.secrets["DB_PASSWORD"]

        conn = pymssql.connect(
            server=server,
            port=port,
            user=user,
            password=password,
            database=database,
            as_dict=True
        )
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
def send_onesignal_notification(school_name, title, message_text, target_phones=None):
    """Στέλνει Push Notifications παράλληλα με μοναδικό web_push_topic για στοίβαξη ειδοποιήσεων."""
    app_id = st.secrets.get("ONESIGNAL_APP_ID")
    rest_key = st.secrets.get("ONESIGNAL_REST_KEY")

    if not app_id or not rest_key:
        st.warning("⚠️ Λείπουν τα διαπιστευτήρια του OneSignal στα Secrets.")
        return False

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Basic {rest_key}"
    }

    base_url = "https://msgsys.streamlit.app"
    full_title = f"[{school_name}] {title}" if school_name.strip() else f"{title}"

    if target_phones and len(target_phones) > 0:
        unique_phones = list(set(
            str(p).strip().replace("+357", "").replace(" ", "").replace("-", "") 
            for p in target_phones if p
        ))

        def send_single_push(phone):
            unique_tag = f"msg_{int(time.time_ns())}"
            unique_url = f"{base_url}/?auto_phone={phone}&_ts={int(time.time()*1000)}"

            payload = {
                "app_id": app_id,
                "headings": {"el": full_title, "en": full_title},
                "contents": {"el": message_text, "en": message_text},
                "url": unique_url,
                "include_aliases": {"external_id": [phone]},
                "target_channel": "push",
                "web_push_topic": unique_tag
            }
            try:
                res = requests.post(
                    "https://onesignal.com/api/v1/notifications", 
                    headers=headers, 
                    json=payload, 
                    timeout=5
                )
                return res.status_code == 200
            except Exception:
                return False

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
            WHERE LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(Phone, '+357', ''), ' ', ''), '-', ''))) = %s 
              AND (IsActive = 1 OR IsActive IS NULL)
        """
        cursor.execute(query, (auto_phone,))
        parent = cursor.fetchone()
        conn.close()

        if parent:
            st.session_state["user_role"] = "Parent"
            st.session_state["user_info"] = {
                "id": parent["ParentID"] if isinstance(parent, dict) else parent[0],
                "name": f"{parent['FirstName'] if isinstance(parent, dict) else parent[1]} {parent['LastName'] if isinstance(parent, dict) else parent[2]}",
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
                        WHERE Username = %s AND PasswordHash = %s AND IsActive = 1
                    """
                    cursor.execute(query, (username, password))
                    user = cursor.fetchone()
                    conn.close()

                    if user:
                        u_id = user["UserID"] if isinstance(user, dict) else user[0]
                        u_name = user["FullName"] if isinstance(user, dict) else user[1]
                        u_role = user["Role"] if isinstance(user, dict) else user[2]

                        st.session_state["user_role"] = u_role
                        st.session_state["user_info"] = {
                            "id": u_id,
                            "name": u_name,
                            "role": u_role,
                        }
                        st.success(f"Καλώς ήρθατε, {u_name}!")
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
                        WHERE LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(Phone, '+357', ''), ' ', ''), '-', ''))) = %s 
                          AND LTRIM(RTRIM(REPLACE(REPLACE(REPLACE(PasswordHash, '+357', ''), ' ', ''), '-', ''))) = %s
                          AND (IsActive = 1 OR IsActive IS NULL)
                    """
                    cursor.execute(query, (clean_phone, clean_pass))
                    parent = cursor.fetchone()
                    conn.close()

                    if parent:
                        p_id = parent["ParentID"] if isinstance(parent, dict) else parent[0]
                        p_fn = parent["FirstName"] if isinstance(parent, dict) else parent[1]

                        st.session_state["user_role"] = "Parent"
                        st.session_state["user_info"] = {
                            "id": p_id,
                            "name": f"{p_fn} {parent['LastName'] if isinstance(parent, dict) else parent[2]}",
                            "phone": clean_phone,
                        }
                        st.success(f"Καλώς ήρθατε, {p_fn}!")
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
                df_students = df_students.drop_duplicates(subset=['ClassID', 'StudentID'])

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
