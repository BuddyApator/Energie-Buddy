import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import requests
from zeroconf import Zeroconf, ServiceBrowser
import time

# --- SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Energie-Buddy Cloud", page_icon="⚡", layout="centered")

# --- VERBINDUNG ZU GOOGLE SHEETS ---
# Erfordert 'st-gsheets-connection' in der requirements.txt
# Und die URL in den Streamlit Secrets (Settings -> Secrets)
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Verbindung zu Google Sheets fehlgeschlagen. Prüfe deine Secrets!")
    st.stop()

# --- HELFER-FUNKTIONEN ---
def get_users():
    return conn.read(worksheet="users", ttl="1s")

def get_energy_data():
    return conn.read(worksheet="daten", ttl="1s")

def register_user(email, password, name):
    users = get_users()
    if not users.empty and email in users['email'].values:
        return False
    new_user = pd.DataFrame([{"email": email, "password": password, "name": name}])
    updated_users = pd.concat([users, new_user], ignore_index=True)
    conn.update(worksheet="users", data=updated_users)
    return True

def save_reading(username, date, reading):
    data = get_energy_data()
    new_entry = pd.DataFrame([{"username": username, "date": date, "reading": reading}])
    updated_data = pd.concat([data, new_entry], ignore_index=True)
    conn.update(worksheet="daten", data=updated_data)

# --- OPTKOPPLER SCAN (Nur für lokalen Gebrauch) ---
class TasmotaDiscovery:
    def __init__(self):
        self.found_ip = None
    def add_service(self, zc, type_, name):
        info = zc.get_service_info(type_, name)
        if info:
            self.found_ip = info.parsed_addresses()[0]

def discover_tasmota_device():
    zeroconf = Zeroconf()
    listener = TasmotaDiscovery()
    ServiceBrowser(zeroconf, "_http._tcp.local.", listener)
    time.sleep(2)
    zeroconf.close()
    return f"http://{listener.found_ip}/cm?cmnd=Status%208" if listener.found_ip else None

# --- AUTHENTIFIZIERUNG / LOGIN-BEREICH ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("⚡ Willkommen beim Energie-Buddy")
    tab1, tab2 = st.tabs(["Anmelden", "Konto erstellen"])

    with tab2:
        st.subheader("Neu hier? Registrieren")
        new_name = st.text_input("Dein Vor