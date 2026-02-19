import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import requests
from zeroconf import Zeroconf, ServiceBrowser
import time
import gspread
from google.oauth2.service_account import Credentials

# --- KONFIGURATION ---
st.set_page_config(page_title="Energie-Buddy Pro", page_icon="⚡", layout="centered")

# DEIN TABELLEN-LINK (Bitte hier anpassen!)
SPREADSHEET_URL = "DEIN_KOMPLETTER_GOOGLE_SHEETS_LINK_HIER"

# --- VERBINDUNGSMETHODE (GSPREAD) ---
@st.cache_resource
def get_gspread_client():
    # Holt die Daten aus den Streamlit Secrets [connections.gsheets]
    s = st.secrets["connections"]["gsheets"]
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

def get_worksheet(name):
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    return sh.worksheet(name)

# --- DATEN-FUNKTIONEN ---

def get_data_as_df(sheet_name):
    sheet = get_worksheet(sheet_name)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def register_user(email, password, name):
    df = get_data_as_df("users")
    if not df.empty and email in df['email'].values:
        return "exists"
    
    sheet = get_worksheet("users")
    sheet.append_row([email, password, name])
    return True

def save_reading(username, date, reading):
    sheet = get_worksheet("daten")
    sheet.append_row([username, str(date), float(reading)])
    return True

# --- OPTKOPPLER (identisch) ---
class TasmotaDiscovery:
    def __init__(self): self.found_ip = None
    def add_service(self, zc, type_, name):
        info = zc.get_service_info(type_, name); 
        if info: self.found_ip = info.parsed_addresses()[0]

def discover_tasmota():
    zc = Zeroconf(); listener = TasmotaDiscovery()
    ServiceBrowser(zc, "_http._tcp.local.", listener)
    time.sleep(2); zc.close()
    return f"http://{listener.found_ip}/cm?cmnd=Status%208" if listener.found_ip else None

# --- UI LOGIK ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("⚡ Energie-Buddy Login")
    t1, t2 = st.tabs(["Login", "Registrieren"])

    with t2:
        r_name = st.text_input("Name")
        r_email = st.text_input("E-Mail")
        r_pw = st.text_input("Passwort", type="password")
        if st.button("Konto erstellen"):
            if r_email and r_pw:
                res = register_user(r_email, r_pw, r_name)
                if res == True: st.success("Registriert! Bitte einloggen.")
                elif res == "exists": st.error("E-Mail existiert bereits.")
            else: st.warning("Felder ausfüllen!")

    with t1:
        l_email = st.text_input("E-Mail", key="l_e")
        l_pw = st.text_input("Passwort", type="password", key="l_p")
        if st.button("Anmelden"):
            users = get_data_as_df("users")
            match = users[(users['email'] == l_email) & (users['password'] == str(l_pw))]
            if not match.empty:
                st.session_state.authenticated = True
                st.session_state.username = l_email
                st.session_state.display_name = match.iloc[0]['name']
                st.rerun()
            else:
                st.error("Login fehlgeschlagen.")
else:
    # --- DASHBOARD ---
    st.sidebar.title(f"Hallo {st.session_state.display_name}!")
    if st.sidebar.button("Abmelden"):
        st.session_state.authenticated = False
        st.rerun()

    menu = st.sidebar.radio("Menü", ["Dashboard", "Zählerstand"])

    if menu == "Zählerstand":
        st.header("Zählerstand eintragen")
        val = st.number_input("Stand (kWh)", step=0.1)
        if st.button("Speichern"):
            save_reading(st.session_state.username, datetime.now().date(), val)
            st.success("Gespeichert!")
    else:
        st.header("Dein Verbrauch")
        df = get_data_as_df("daten")
        if not df.empty:
            user_df = df[df["username"] == st.session_state.username].copy()
            if not user_df.empty:
                user_df['date'] = pd.to_datetime(user_df['date'])
                fig = px.area(user_df.sort_values("date"), x="date", y="reading")
                st.plotly_chart(fig)
                st.table(user_df.tail())
            else:
                st.info("Noch keine Daten.")