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

# --- BITTE HIER DEINEN LINK EINTRAGEN ---
SPREADSHEET_URL = "DEIN_KOMPLETTER_GOOGLE_SHEETS_LINK_HIER"

# --- 2. VERBINDUNG ZU GOOGLE (DIAGNOSE-MODUS) ---
@st.cache_resource
def get_gspread_client():
    # Suche nach den Secrets
    s = None
    if "connections" in st.secrets and "gsheets" in st.secrets.connections:
        s = st.secrets.connections.gsheets
    elif "private_key" in st.secrets:
        s = st.secrets
    
    if not s:
        st.error("🚨 KRITISCH: 'private_key' wurde nicht gefunden!")
        st.write("Verfügbare Schlüssel in deinen Secrets:", list(st.secrets.keys()))
        st.info("Tipp: Lösche in den Secrets die Zeile [connections.gsheets] und rücke alles ganz nach links.")
        st.stop()

    try:
        credentials_info = {
            "type": s["type"],
            "project_id": s["project_id"],
            "private_key_id": s["private_key_id"],
            "private_key": s["private_key"],
            "client_email": s["client_email"],
            "client_id": s["client_id"],
            "auth_uri": s["auth_uri"],
            "token_uri": s["token_uri"],
            "auth_provider_x509_cert_url": s["auth_provider_x509_cert_url"],
            "client_x509_cert_url": s["client_x509_cert_url"]
        }
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(credentials_info, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Fehler beim Erstellen der Google-Anmeldung: {e}")
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
        st.subheader("Neues Konto")
        r_name = st.text_input("Vorname", key="reg_name")
        r_email = st.text_input("E-Mail", key="reg_email")
        r_pw = st.text_input("Passwort", type="password", key="reg_pw")
        if st.button("Konto erstellen"):
            if r_email and r_pw and r_name:
                res = register_user(r_email, r_pw, r_name)
                if res == True:
                    st.success("Konto erstellt! Bitte einloggen.")
                elif res == "exists":
                    st.error("E-Mail existiert bereits.")
            else:
                st.warning("Bitte alle Felder ausfüllen.")

    with t1:
        st.subheader("Willkommen zurück