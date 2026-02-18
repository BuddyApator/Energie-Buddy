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
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Verbindung zu Google Sheets fehlgeschlagen. Prüfe deine Secrets!")
    st.stop()

# --- HELFER-FUNKTIONEN ---
def get_users():
    try:
        return conn.read(worksheet="users", ttl="1s")
    except:
        return pd.DataFrame(columns=["email", "password", "name"])

def get_energy_data():
    try:
        return conn.read(worksheet="daten", ttl="1s")
    except:
        return pd.DataFrame(columns=["username", "date", "reading"])

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

# --- OPTKOPPLER SCAN (Lokal) ---
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

# --- AUTHENTIFIZIERUNG ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("⚡ Energie-Buddy")
    tab1, tab2 = st.tabs(["Anmelden", "Konto erstellen"])

    with tab2:
        st.subheader("Neu hier? Registrieren")
        new_name = st.text_input("Dein Vorname", key="reg_name")
        new_email = st.text_input("E-Mail Adresse", key="reg_email")
        new_pw = st.text_input("Passwort wählen", type="password", key="reg_pw")
        if st.button("Konto erstellen"):
            if new_email and new_pw and new_name:
                if register_user(new_email, new_pw, new_name):
                    st.success("Konto erstellt! Du kannst dich jetzt anmelden.")
                else:
                    st.error("Diese E-Mail ist bereits registriert.")
            else:
                st.warning("Bitte alle Felder ausfüllen.")

    with tab1:
        st.subheader("Login")
        login_email = st.text_input("E-Mail", key="log_email")
        login_pw = st.text_input("Passwort", type="password", key="log_pw")
        if st.button("Anmelden"):
            users = get_users()
            if not users.empty:
                user_match = users[(users['email'] == login_email) & (users['password'] == login_pw)]
                if not user_match.empty:
                    st.session_state.authenticated = True
                    st.session_state.username = login_email
                    st.session_state.display_name = user_match.iloc[0]['name']
                    st.rerun()
                else:
                    st.error("E-Mail oder Passwort falsch.")
            else:
                st.error("Keine Benutzer gefunden. Bitte registriere dich zuerst.")

# --- HAUPT-APP ---
else:
    user_email = st.session_state.username
    display_name = st.session_state.display_name

    st.sidebar.title(f"Hallo {display_name}! 👋")
    menu = st.sidebar.radio("Menü", ["Dashboard", "Zählerstand eingeben"])
    
    if st.sidebar.button("Abmelden"):
        st.session_state.authenticated = False
        st.rerun()

    if menu == "Zählerstand eingeben":
        st.header("📝 Daten erfassen")
        mode = st.radio("Methode:", ["Manuell", "Optokoppler (lokal)"])

        if mode == "Manuell":
            with st.form("entry_form"):
                reading = st.number_input("Stand (kWh)", step=0.1)
                date = st.date_input("Datum", datetime.now())
                if st.form_submit_button("Speichern"):
                    save_reading(user_email, date.strftime("%Y-%m-%d"), reading)
                    st.success("Gespeichert!")
        else:
            if st.button("Nach Optokoppler suchen"):
                device_url = discover_tasmota_device()
                if device_url:
                    try:
                        res = requests.get(device_url, timeout=5).json()
                        stand = res['StatusSNS']['SML']['Total_in']
                        save_reading(user_email, datetime.now().strftime("%Y-%m-%d %H:%M"), stand)
                        st.metric("Live-Stand", f"{stand} kWh")
                        st.balloons()
                    except:
                        st.error("Fehler beim Abruf der Daten.")
                else:
                    st.warning("Kein Gerät im lokalen Netzwerk gefunden.")

    else:
        st.header(f"📊 Dashboard: {display_name}")
        all_data = get_energy_data()
        if not all_data.empty:
            user_df = all_data[all_data["username"] == user_email].copy()
            if not user_df.empty:
                user_df['date'] = pd.to_datetime(user_df['date'])
                user_df = user_df.sort_values("date")
                fig = px.area(user_df, x='date', y='reading', title="Stromverbrauch")
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(user_df.tail(10))
            else:
                st.info("Noch keine Daten vorhanden.")
        else:
            st.info("Datenbank ist leer.")