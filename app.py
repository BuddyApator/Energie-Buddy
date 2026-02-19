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
    # DIAGNOSE: Was findet Streamlit in den Secrets?
    all_keys = list(st.secrets.keys())
    
    # Falls die Secrets unter [connections.gsheets] stehen, schieben wir sie nach oben
    if "connections" in st.secrets:
        s = st.secrets.connections.gsheets
    elif "private_key" in st.secrets:
        s = st.secrets
    else:
        st.error("🚨 KRITISCH: 'private_key' wurde nicht gefunden!")
        st.write("Verfügbare Schlüssel in deinen Secrets:", all_keys)
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

def register_user(email, password