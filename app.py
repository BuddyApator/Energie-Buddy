import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import datetime
import requests
from zeroconf import Zeroconf, ServiceBrowser
import time

# --- 1. DATENBANK-LOGIK (MIT NUTZER-TRENNUNG) ---
def init_db():
    conn = sqlite3.connect("energy_history.db", check_same_thread=False)
    c = conn.cursor()
    # Wir fügen die Spalte 'username' hinzu, um Daten zu trennen
    c.execute('''CREATE TABLE IF NOT EXISTS energy (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT,
                 date TEXT, 
                 reading REAL)''')
    conn.commit()
    return conn

def save_reading(username, date, reading):
    conn = sqlite3.connect("energy_history.db")
    c = conn.cursor()
    c.execute("INSERT INTO energy (username, date, reading) VALUES (?, ?, ?)", (username, date, reading))
    conn.commit()
    conn.close()

# --- 2. LOGIN SYSTEM ---
def check_password():
    """Gibt True zurück, wenn der Benutzer korrekt eingeloggt ist."""
    def login_form():
        with st.form("Login"):
            st.subheader("🔒 Energie-Buddy Login")
            user = st.text_input("Benutzername")
            pw = st.text_input("Passwort", type="password")
            submit = st.form_submit_button("Anmelden")
            
            if submit:
                # Hier kannst du Kunden-Logins festlegen
                credentials = {
                    "admin": "buddy2024",
                    "kunde1": "sonne123",
                    "gast": "start123"
                }
                
                if user in credentials and credentials[user] == pw:
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = user
                    st.rerun()
                else:
                    st.error("❌ Nutzername oder Passwort falsch")

    if "authenticated" not in st.session_state:
        login_form()
        return False
    return True

# --- 3. OPTKOPPLER SUCHE (WIE GEHABT) ---
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
    browser = ServiceBrowser(zeroconf, "_http._tcp.local.", listener)
    time.sleep(2)
    zeroconf.close()
    if listener.found_ip:
        return f"http://{listener.found_ip}/cm?cmnd=Status%208"
    return None

# --- HAUPTPROGRAMM ---
st.set_page_config(page_title="Energie-Buddy Pro", page_icon="⚡")

if check_password():
    # Alles unter dieser Zeile wird erst nach dem Login angezeigt
    user = st.session_state["username"]
    
    st.sidebar.title(f"Hallo, {user.capitalize()}! 👋")
    if st.sidebar.button("Abmelden"):
        del st.session_state["authenticated"]
        st.rerun()

    st.title("⚡ Dein Energie-Buddy")
    init_db()

    # Auswahl des Modus
    mode = st.sidebar.radio("Modus:", ["Dashboard & Grafik", "Daten eingeben"])

    if mode == "Daten eingeben":
        st.header("📝 Neuen Zählerstand erfassen")
        
        tab1, tab2 = st.tabs(["✍️ Manuell", "📡 Automatisch (Optokoppler)"])
        
        with tab1:
            with st.form("manual_entry"):
                val = st.number_input("Aktueller Stand (kWh)", step=0.1)
                dt = st.date_input("Datum", datetime.now())
                if st.form_submit_button("Speichern"):
                    save_reading(user, dt.strftime("%Y-%m-%d"), val)
                    st.success("Daten gespeichert!")

        with tab2:
            device_url = discover_tasmota_device()
            if device_url:
                st.success(f"Sensor gefunden: {device_url}")
                if st.button("Jetzt live abrufen"):
                    try:
                        res = requests.get(device_url, timeout=5).json()
                        stand = res['StatusSNS']['SML']['Total_in']
                        save_reading(user, datetime.now().strftime("%Y-%m-%d %H:%M"), stand)
                        st.balloons()
                        st.metric("Live-Stand", f"{stand} kWh")
                    except:
                        st.error("Fehler beim Abruf der Tasmota-Daten.")
            else:
                st.info("Kein lokaler Sensor gefunden. (Im Cloud-Modus normal)")

    else:
        st.header(f"📊 Auswertung für {user.capitalize()}")
        
        # WICHTIG: Wir laden nur die Daten des aktuellen Nutzers!
        conn = sqlite3.connect("energy_history.db")
        query = "SELECT date, reading FROM energy WHERE username = ? ORDER BY date ASC"
        df = pd.read_sql_query(query, conn, params=(user,))
        conn.close()

        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            
            # Grafik
            fig = px.area(df, x='date', y='reading', title="Dein Energieverbrauch")
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabelle
            st.subheader("Deine letzten Messungen")
            st.table(df.tail(5))
        else:
            st.warning("Noch keine Daten vorhanden. Bitte wechsle zu 'Daten eingeben'.")