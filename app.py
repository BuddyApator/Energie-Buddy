import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import requests
import json
import os
import time
import urllib.parse
from zeroconf import Zeroconf, ServiceBrowser
import socket
from datetime import datetime

# --- DATEI-PFADE ---
SETTINGS_FILE = "buddy_settings.json"
DB_FILE = "energy_history.db"

# --- DATENBANK-FUNKTIONEN ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS daily_usage (datum DATE PRIMARY KEY, zaehlerstand REAL)')
    conn.commit()
    conn.close()

def save_reading(stand):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    heute = datetime.now().strftime('%Y-%m-%d')
    c.execute("INSERT OR REPLACE INTO daily_usage VALUES (?, ?)", (heute, stand))
    conn.commit()
    conn.close()

# --- SETTINGS-FUNKTIONEN ---
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {"ip": None, "preis": 0.35, "budget": 5.0, "mode": "manual", "kundennummer": "", "stadtwerke_mail": ""}

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)

# --- AUTO-DISCOVERY KLASSE ---
class TasmotaDiscovery:
    def __init__(self):
        self.found_devices = {}
    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            ip = socket.inet_ntoa(info.addresses[0])
            self.found_devices[name.split('.')[0]] = ip

# --- APP SETUP & DESIGN ---
st.set_page_config(page_title="Energie-Buddy PRO", page_icon="⚡", layout="wide")
init_db()
settings = load_settings()

st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(rgba(0,0,0,0.75), rgba(0,0,0,0.75)), 
                    url('https://images.unsplash.com/photo-1473341304170-971dccb5ac1e?auto=format&fit=crop&w=1920&q=80');
        background-size: cover;
    }
    .main-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(15px);
        border-radius: 20px;
        padding: 20px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        margin-bottom: 20px;
    }
    h1, h2, h3, .stMetric, label, p { color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR (KONFIGURATION) ---
st.sidebar.title("⚙️ Einstellungen")
mode = st.sidebar.radio("Erfassungs-Modus:", ["Automatisch (Hichi/Tasmota)", "Manuelle Eingabe"], 
                         index=0 if settings.get("mode") == "auto" else 1)

preis = st.sidebar.number_input("Strompreis (€/kWh)", value=settings.get("preis", 0.35), step=0.01)
budget = st.sidebar.slider("Tages-Budget (€)", 1.0, 20.0, value=settings.get("budget", 5.0))

st.sidebar.markdown("---")
k_num = st.sidebar.text_input("Kundennummer", value=settings.get("kundennummer", ""))
s_mail = st.sidebar.text_input("E-Mail Stadtwerke", value=settings.get("stadtwerke_mail", ""))

if st.sidebar.button("Speichern & Aktualisieren"):
    settings.update({
        "preis": preis, "budget": budget, "kundennummer": k_num, 
        "stadtwerke_mail": s_mail, "mode": "auto" if "Auto" in mode else "manual"
    })
    save_settings(settings)
    st.sidebar.success("Einstellungen gespeichert!")
    st.rerun()

if st.sidebar.button("🔴 Verbindung zurücksetzen"):
    settings["ip"] = None
    save_settings(settings)
    st.rerun()

# --- HAUPTBEREICH ---
st.title("🛡️ Dein Energie-Buddy")

# Logik für Live-Daten oder Manuelle Eingabe
watt, total = 0, 0

if settings["mode"] == "auto":
    if settings["ip"] is None:
        st.info("Suche nach Optokoppler im WLAN...")
        if st.button("🔍 Netzwerk jetzt scannen"):
            zc = Zeroconf()
            listener = TasmotaDiscovery()
            ServiceBrowser(zc, "_http._tcp.local.", listener)
            with st.spinner("Ich suche..."):
                time.sleep(3)
            zc.close()
            if listener.found_devices:
                dev = st.selectbox("Gefundene Geräte:", list(listener.found_devices.keys()))
                if st.button("Dieses Gerät verbinden"):
                    settings["ip"] = listener.found_devices[dev]
                    save_settings(settings)
                    st.rerun()
            else:
                st.error("Kein Tasmota-Gerät gefunden. Prüfe dein WLAN.")
    else:
        try:
            url = f"http://{settings['ip']}/cm?cmnd=status%2010"
            r = requests.get(url, timeout=2).json()
            watt = r['StatusSNS']['SML']['Power_curr']
            total = r['StatusSNS']['SML']['Total_in']
            save_reading(total)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Live-Verbrauch", f"{watt} W")
            c2.metric("Kosten / h", f"{(watt/1000*preis):.2f} €")
            c3.metric("Zählerstand", f"{total} kWh")
        except:
            st.error("⚠️ Hardware nicht erreichbar. Ist der Lesekopf online?")

else:
    st.markdown('<div class="main-card">', unsafe_allow_html=True)
    with st.form("manual_form"):
        st.subheader("✍️ Manueller Zählerstand")
        total = st.number_input("Aktueller Stand in kWh", format="%.2f")
        if st.form_submit_button("Speichern"):
            save_reading(total)
            st.success("Zählerstand für heute vermerkt!")
    st.markdown('</div>', unsafe_allow_html=True)

# --- ANALYSE & EXPORT ---
tab1, tab2, tab3 = st.tabs(["📊 Wochenansicht", "🎮 Spar-Challenge", "📩 Stadtwerke / Export"])

with tab1:
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM daily_usage ORDER BY datum", conn)
    conn.close()
    if len(df) > 1:
        df['verbrauch'] = df['zaehlerstand'].diff()
        df['kosten'] = df['verbrauch'] * preis
        fig = px.bar(df.dropna(), x='datum', y='kosten', title="Tageskosten (€)", color_discrete_sequence=['#2ecc71'])
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Daten für den 2. Tag fehlen noch für die Grafik.")

with tab2:
    st.markdown('<div class="main-card">', unsafe_allow_html=True)
    if len(df) > 1:
        heute_kosten = (df['zaehlerstand'].iloc[-1] - df['zaehlerstand'].iloc[-2]) * preis
        prozent = min(heute_kosten / budget, 1.0)
        st.progress(prozent)
        st.write(f"Heute: **{heute_kosten:.2f} €** von **{budget:.2f} €**")
    else:
        st.write("Challenge startet nach dem zweiten Eintrag!")
    st.markdown('</div>', unsafe_allow_html=True)

with tab3:
    col_l, col_r = st.columns(2)
    with col_l:
        st.write("### E-Mail an Stadtwerke")
        betreff = f"Zaehlerstand {settings['kundennummer']}"
        body = f"Anbei mein Zählerstand vom {datetime.now().strftime('%d.%m.%Y')}: {total} kWh. KD-Nr: {settings['kundennummer']}"
        mailto = f"mailto:{settings['stadtwerke_mail']}?subject={urllib.parse.quote(betreff)}&body={urllib.parse.quote(body)}"
        st.markdown(f'<a href="{mailto}" target="_blank" style="text-decoration:none;"><div style="background:#2ecc71;color:white;padding:10px;border-radius:10px;text-align:center;">📧 Mail öffnen</div></a>', unsafe_allow_html=True)
    
    with col_r:
        st.write("### Daten-Export")
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 CSV herunterladen", data=csv, file_name="energie_buddy_data.csv", mime="text/csv")

# Auto-Refresh für Live-Daten
if settings["mode"] == "auto" and settings["ip"] is not None:
    time.sleep(5)
    st.rerun()