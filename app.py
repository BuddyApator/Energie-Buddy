import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import requests
from zeroconf import Zeroconf, ServiceBrowser
import time

# --- KONFIGURATION ---
st.set_page_config(page_title="Energie-Buddy Cloud", page_icon="⚡", layout="centered")

# HIER DEINEN LINK EINTRAGEN:
SPREADSHEET_URL = "DEIN_KOMPLETTER_GOOGLE_SHEETS_LINK_HIER"

# --- VERBINDUNG ZU GOOGLE SHEETS ---
try:
    # Nutzt die Service-Account-Daten aus den Secrets
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Verbindung zu Google Sheets fehlgeschlagen: {e}")
    st.stop()

# --- HELFER-FUNKTIONEN ---

def get_users():
    try:
        # Liest das Blatt "users"
        return conn.read(spreadsheet=SPREADSHEET_URL, worksheet="users", ttl="1s")
    except:
        return pd.DataFrame(columns=["email", "password", "name"])

def get_energy_data():
    try:
        # Liest das Blatt "daten"
        return conn.read(spreadsheet=SPREADSHEET_URL, worksheet="daten", ttl="1s")
    except:
        return pd.DataFrame(columns=["username", "date", "reading"])

def register_user(email, password, name):
    try:
        users = get_users()
        # Prüfen, ob Email schon existiert
        if not users.empty and email in users['email'].values:
            return "exists"
        
        new_user = pd.DataFrame([{"email": email, "password": password, "name": name}])
        updated_users = pd.concat([users, new_user], ignore_index=True)
        
        # Speichern mit expliziter URL-Angabe für Schreibrechte
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet="users", data=updated_users)
        return True
    except Exception as e:
        st.error(f"Fehler beim Speichern: {e}")
        return False

def save_reading(username, date, reading):
    try:
        data = get_energy_data()
        new_entry = pd.DataFrame([{"username": username, "date": date, "reading": reading}])
        updated_data = pd.concat([data, new_entry], ignore_index=True)
        
        # Spe