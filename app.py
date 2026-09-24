import streamlit as st
import pandas as pd
import os

# --- 1. ΡΥΘΜΙΣΗ ΣΕΛΙΔΑΣ ---
st.set_page_config(
    page_title="Admin Portal",
    page_icon="⚙️",
    layout="wide"
)

EXCEL_FILE = "data.xlsx"

# --- 2. ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ ΔΙΑΧΕΙΡΙΣΗΣ ΔΕΔΟΜΕΝΩΝ ---
def load_data():
    """Φόρτωση δεδομένων από το Excel. Αν δεν υπάρχει, δημιουργία δείγματος."""
    if not os.path.exists(EXCEL_FILE):
        df_sample = pd.DataFrame({
            "ID": [101, 102, 103],
            "Όνομα": ["Γιάννης Παπαδόπουλος", "Μαρία Κωνσταντίνου", "Νίκος Αλεξίου"],
            "Κατηγορία": ["Εκπαιδευτικός", "Διοικητικός", "Εκπαιδευτικός"],
            "Κατάσταση": ["Ενεργός", "Ενεργός", "Σε άδεια"],
            "Ημερομηνία": ["2026-09-01", "2026-09-10", "2026-09-15"]
        })
        df_sample.to_excel(EXCEL_FILE, index=False)
        return df_sample
    return pd.read_excel(EXCEL_FILE)

def save_data(df):
    """Αποθήκευση του DataFrame στο αρχείο Excel."""
    df.to_excel(EXCEL_FILE, index=False)

# Φόρτωση δεδομένων στην μνήμη της εφαρμογής
df = load_data()

# --- 3. ΠΛΑΪΝΗ ΜΠΑΡΑ (SIDEBAR) & ΠΛΟΗΓΗΣΗ ---
st.sidebar.title("⚙️ Admin Portal")
st.sidebar.write("Διαχείριση Δεδομένων & Συστήματος")

menu_option = st.sidebar.radio(
    "Επιλέξτε Ενότητα:",
    ["📊 Dashboard", "📝 Διαχείριση Εγγραφών", "📥 Εισαγωγή / Εξαγωγή Excel"]
)

st.sidebar.markdown("---")
st.sidebar.info(f"📁 Αρχείο Δεδομένων: `{EXCEL_FILE}`")

# --- 4. ΕΝΟΤΗΤΕΣ ΕΦΑΡΜΟΓΗΣ ---

# === A. DASHBOARD ===
if menu_option == "📊 Dashboard":
    st.header("📊 Πίνακας Ελέγχου Διαχειριστή")
    st.caption("Επισκόπηση και βασικά στατιστικά στοιχεία")
    
    # Μετρικά στοιχεία
    col1, col2, col3 = st.columns(3)
    col1.metric("Συνολικές Εγγραφές", len(df))
    
    active_count = len(df[df["Κατάσταση"] == "Ενεργός"]) if "Κατάσταση" in df.columns else 0
    col2.metric("Ενεργές Εγγραφές", active_count)
    
    categories_count = df["Κατηγορία"].nunique() if "Κατηγορία" in df.columns else 0
    col3.metric("Κατηγορίες", categories_count)
    
    st.markdown("---")
    
    # Πρόσφατες Εγγραφές
    st.subheader("📋 Πρόσφατες Καταχωρίσεις")
    st.dataframe(df.tail(5), use_container_width=True)


# === B. ΔΙΑΧΕΙΡΙΣΗ ΕΓΓΡΑΦΩΝ (CRUD) ===
elif menu_option == "📝 Διαχείριση Εγγραφών":
    st.header("📝 Διαχείριση & Επεξεργασία Δεδομένων")
    
    tab_view, tab_add, tab_edit_delete = st.tabs([
        "🔍 Προβολή & Αναζήτηση", 
        "➕ Προσθήκη Νέας Εγγραφής", 
        "✏️ Επεξεργασία / Διαγραφή"
    ])
    
    # --- Tab 1: Προβολή & Φιλτράρισμα ---
    with tab_view:
        st.subheader("Προβολή Δεδομένων")
        search_term = st.text_input("🔎 Αναζήτηση (π.χ. Όνομα, Κατηγορία):")
        
        filtered_df = df.copy()
        if search_term:
            filtered_df = df[df.astype(str).apply(lambda row: row.str.contains(search_term, case=False).any(), axis=1)]
        
        st.dataframe(filtered_df, use_container_width=True)
        st.caption(f"Εμφανίζονται {len(filtered_df)} από {len(df)} εγγραφές.")

    # --- Tab 2: Προσθήκη Εγγραφής ---
    with tab_add:
        st.subheader("Καταχώριση Νέου Στοιχείου")
        
        with st.form("add_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            
            new_id = col_a.number_input("ID", min_value=1, value=int(df["ID"].max() + 1) if not df.empty else 101)
            new_name = col_b.text_input("Όνομα / Περιγραφή")
            
            new_cat = col_a.selectbox("Κατηγορία", ["Εκπαιδευτικός", "Διοικητικός", "Άλλο"])
            new_status = col_b.selectbox("Κατάσταση", ["Ενεργός", "Σε άδεια", "Ανενεργός"])
            new_date = st.date_input("Ημερομηνία")
            
            submit_button = st.form_submit_button("💾 Αποθήκευση Εγγραφής")
            
            if submit_button:
                if not new_name:
                    st.error("Παρακαλώ συμπληρώστε το πεδίο 'Όνομα'.")
                else:
                    new_row = {
                        "ID": new_id,
                        "Όνομα": new_name,
                        "Κατηγορία": new_cat,
                        "Κατάσταση": new_status,
                        "Ημερομηνία": str(new_date)
                    }
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=False)
                    save_data(df)
                    st.success(f"Η εγγραφή '{new_name}' προστέθηκε με επιτυχία!")
                    st.rerun()

    # --- Tab 3: Επεξεργασία & Διαγραφή ---
    with tab_edit_delete:
        st.subheader("Τροποποίηση ή Αφαίρεση Εγγραφής")
        
        if df.empty:
            st.warning("Δεν υπάρχουν διαθέσιμες εγγραφές.")
        else:
            selected_id = st.selectbox("Επιλέξτε ID Εγγραφής:", df["ID"].unique())
            selected_row = df[df["ID"] == selected_id].iloc[0]
            
            col_edit, col_del = st.columns([2, 1])
            
            with col_edit:
                st.markdown("**Επεξεργασία:**")
                edit_name = st.text_input("Όνομα", value=selected_row["Όνομα"])
                edit_cat = st.selectbox("Κατηγορία", ["Εκπαιδευτικός", "Διοικητικός", "Άλλο"], index=0)
                edit_status = st.selectbox("Κατάσταση", ["Ενεργός", "Σε άδεια", "Ανενεργός"], index=0)
                
                if st.button("🔄 Ενημέρωση Εγγραφής"):
                    df.loc[df["ID"] == selected_id, ["Όνομα", "Κατηγορία", "Κατάσταση"]] = [edit_name, edit_cat, edit_status]
                    save_data(df)
                    st.success("Οι αλλαγές αποθηκεύτηκαν!")
                    st.rerun()
            
            with col_del:
                st.markdown("**Διαγραφή:**")
                st.write("Προσοχή: Η ενέργεια αυτή είναι μόνιμη.")
                if st.button("🗑️ Διαγραφή Εγγραφής", type="primary"):
                    df = df[df["ID"] != selected_id]
                    save_data(df)
                    st.success("Η εγγραφή διαγράφηκε!")
                    st.rerun()


# === C. ΕΙΣΑΓΩΓΗ / ΕΞΑΓΩΓΗ EXCEL ===
elif menu_option == "📥 Εισαγωγή / Εξαγωγή Excel":
    st.header("📥 Μαζική Διαχείριση Αρχείων Excel")
    
    col_exp, col_imp = st.columns(2)
    
    with col_exp:
        st.subheader("📤 Εξαγωγή Δεδομένων")
        st.write("Κατεβάστε τα τρέχοντα δεδομένα σε μορφή Excel.")
        
        # Μετατροπή DataFrame σε Excel buffer για κατέβασμα
        import io
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Data')
        
        st.download_button(
            label="⬇️ Κατέβασμα Excel (.xlsx)",
            data=buffer.getvalue(),
            file_name="export_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    with col_imp:
        st.subheader("📥 Μαζική Εισαγωγή (Upload)")
        st.write("Ανεβάστε νέο αρχείο Excel για αντικατάσταση ή ενημέρωση των δεδομένων.")
        
        uploaded_file = st.file_uploader("Επιλέξτε αρχείο Excel (.xlsx)", type=["xlsx"])
        
        if uploaded_file is not None:
            uploaded_df = pd.read_excel(uploaded_file)
            st.write("Προεπισκόπηση Νέων Δεδομένων:")
            st.dataframe(uploaded_df.head(3))
            
            if st.button("⚠️ Αντικατάσταση Όλων των Δεδομένων"):
                save_data(uploaded_df)
                st.success("Τα δεδομένα ενημερώθηκαν επιτυχώς από το νέο αρχείο!")
                st.rerun()
