import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import requests
from zeroconf import Zeroconf, ServiceBrowser
import time
import gspread
from google.oauth2.service_account import Credentials

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="Energie-Buddy Cloud", page_icon="⚡", layout="centered")

# HIER DEINEN LINK EINTRAGEN:
SPREADSHEET_URL = "DEIN_KOMPLETTER_GOOGLE_SHEETS_LINK_HIER"

# --- 2. VERBINDUNG ZU GOOGLE (FLACHE STRUKTUR) ---
@st.cache_resource
def get_gspread_client():
    try:
        # Greift direkt auf die Secrets zu (ohne Unter-Kategorien)
        credentials_info = {
            "type": st.secrets["type"],
            "project_id": st.secrets["project_id"],
            "private_key_id": st.secrets["private_key_id"],
            "private_key": st.secrets["private_key"],
            "client_email": st.secrets["client_email"],
            "client_id": st.secrets["client_id"],
            "auth_uri": st.secrets["auth_uri"],
            "token_uri": st.secrets["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["client_x509_cert_url"]
        }
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(credentials_info, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Fehler beim Erstellen der Google-Anmeldung: {e}")
        st.info("Checke, ob deine Secrets im Streamlit Dashboard korrekt eingetragen sind.")
        st.stop()

def get_worksheet(name):
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    return sh.worksheet(name)

# --- 3. DATEN-FUNKTIONEN ---
def get_data_as_df(sheet_name):
    try:
        sheet = get_worksheet(sheet_name)
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Fehler beim Lesen von '{sheet_name}': {e}")
        return pd.DataFrame()

def register_user(email, password, name):
    df = get_data_as_df("users")
    if not df.empty and email in df['email'].values:
        return "exists"
    try:
        sheet = get_worksheet("users")
        sheet.append_row([email, str(password), name])
        return True
    except Exception as e:
        st.error(f"Fehler beim Registrieren: {e}")
        return False

def save_reading(username, date, reading):
    try:
        sheet = get_worksheet("daten")
        sheet.append_row([username, str(date), float(reading)])
        return True
    except Exception as e:
        st.error(f"Fehler beim Speichern: {e}")
        return False

# --- 4. OPTKOPPLER SCAN ---
class TasmotaDiscovery:
    def __init__(self): self.found_ip = None
    def add_service(self, zc, type_, name):
        info = zc.get_service_info(type_, name)
        if info: self.found_ip = info.parsed_addresses()[0]

def discover_tasmota():
    zc = Zeroconf(); listener = TasmotaDiscovery()
    ServiceBrowser(zc, "_http._tcp.local.", listener)
    time.sleep(2); zc.close()
    return f"http://{listener.found_ip}/cm?cmnd=Status%208" if listener.found_ip else None

# --- 5. LOGIN / REGISTRIERUNG ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("⚡ Energie-Buddy")
    t1, t2 = st.tabs(["Anmelden", "Registrieren"])

    with t2:
        r_name = st.text_input("Name")
        r_email = st.text_input("E-Mail")
        r_pw = st.text_input("Passwort", type="password")
        if st.button("Konto erstellen"):
            if r_email and r_pw:
                if register_user(r_email, r_pw, r_name) == True:
                    st.success("Konto erstellt! Bitte jetzt einloggen.")
                else:
                    st.error("Registrierung fehlgeschlagen oder E-Mail existiert schon.")

    with t1:
        l_email = st.text_input("E-Mail", key="l_e")
        l_pw = st.text_input("Passwort", type="password", key="l_p")
        if st.button("Anmelden"):
            users = get_data_as_df("users")
            if not users.empty:
                match = users[(users['email'] == l_email) & (users['password'].astype(str) == str(l_pw))]
                if not match.empty:
                    st.session_state.authenticated = True
                    st.session_state.username = l_email
                    st.session_state.display_name = match.iloc[0]['name']
                    st.rerun()
                else:
                    st.error("Login-Daten nicht korrekt.")

# --- 6. HAUPT-APP ---
else:
    st.sidebar.title(f"Hallo {st.session_state.display_name}!")
    menu = st.sidebar.radio("Navigation", ["Dashboard", "Zählerstand"])
    
    if st.sidebar.button("Abmelden"):
        st.session_state.authenticated = False
        st.rerun()

    if menu == "Zählerstand":
        st.header("Zählerstand erfassen")
        val = st.number_input("Aktueller Stand (kWh)", step=0.1)
        if st.button("💾 Speichern"):
            if save_reading(st.session_state.username, datetime.now().date(), val):
                st.success("In die Cloud gespeichert!")

    else:
        st.header("📈 Deine Verbrauchsdaten")
        df = get_data_as_df("daten")
        if not df.empty:
            user_df = df[df["username"] == st.session_state.username].copy()
            if not user_df.empty:
                user_df['date'] = pd.to_datetime(user_df['date'])
                user_df = user_df.sort_values("date")
                fig = px.line(user_df, x="date", y="reading", markers=True)
                st.plotly_chart(fig)
                st.table(user_df.tail())
            else:
                st.info("Noch keine Einträge vorhanden.")