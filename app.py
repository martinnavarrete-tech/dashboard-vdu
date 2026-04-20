import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit_authenticator as stauth
import plotly.express as px
import re
import requests
import time
from datetime import datetime, timedelta

# --- 1. CONFIGURACIÓN Y ESTILOS ---
st.set_page_config(page_title="Dashboard VDU", layout="wide", page_icon="🎰")

st.markdown("""
    <style>
    .metric-card {
        background-color: #1E1E2E;  
        padding: 20px;
        border-radius: 10px;
        border-bottom: 4px solid #333;
        margin-bottom: 15px;
        min-height: 160px;
    }
    .metric-label { color: #A0A0A0; font-size: 0.75rem; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px; }
    .metric-value { color: white; font-size: 1.5rem; font-weight: bold; margin: 8px 0; }
    .metric-sub { font-size: 0.85rem; font-weight: 500; line-height: 1.3; }
    .main-kpi-val { font-size: 2.5rem; font-weight: 800; color: #FFFFFF; line-height: 1.1; }
    .main-kpi-label { font-size: 0.9rem; color: #A0A0A0; text-transform: uppercase; font-weight: bold; }
    .status-badge { padding: 4px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; text-transform: uppercase; }
    </style>
""", unsafe_allow_html=True)

def form_num(valor):
    try:
        return f"$ {valor:,.0f}".replace(',', '.')
    except:
        return "$ 0"

# IDs de los Libros de Google Sheets
ID_CONFIGURACION = "1W_68ToMyy_nu1oPH7ePFj74_vc1op5bGiFoP4KtaY0I"
ID_DATOS_2026 = "1ZYn6foApzeEeKg_qKzW9faQFjBPXHoc8ffB_CeZ3f_s"
ID_DATOS_2025 = "1aAl_PX1wpBWgTu9bLc81Wn57jSyt8Kqfwm4B4Fsa1W0"

# --- 2. MOTOR DE DATOS ---
@st.cache_data(ttl=60)
def load_all_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        
        sheet_u = client.open_by_key(ID_CONFIGURACION).worksheet("Usuarios")
        df_u = pd.DataFrame(sheet_u.get_all_records())
        
        def get_cubo_data(book_id):
            try:
                sheet = client.open_by_key(book_id).worksheet("Cubo")
                data = sheet.get_all_values()
                if not data: return pd.DataFrame()
                df = pd.DataFrame(data[1:], columns=data[0])
                df = df.loc[:, ~df.columns.str.contains('^$|Unnamed', case=False, na=False)]
                df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=True, errors='coerce').dt.date
                return df.dropna(subset=['fecha'])
            except: return pd.DataFrame()

        df_2025 = get_cubo_data(ID_DATOS_2025)
        df_2026 = get_cubo_data(ID_DATOS_2026)
        df_s = pd.concat([df_2025, df_2026], ignore_index=True)
        
        for col in ['coin_in', 'win', 'jackpot']:
            if col in df_s.columns:
                def clean_currency(x):
                    if not x or str(x).strip() == "": return 0.0
                    cleaned = re.sub(r'[^\d.,-]', '', str(x))
                    if ',' in cleaned and '.' in cleaned: cleaned = cleaned.replace('.', '').replace(',', '.')
                    elif ',' in cleaned: cleaned = cleaned.replace(',', '.')
                    try: return float(cleaned)
                    except: return 0.0
                df_s[col] = df_s[col].apply(clean_currency)
            
        return df_s, df_u
    except Exception as e:
        st.error(f"Error crítico de sincronización: {e}")
        return None, None

df_slots, df_users = load_all_data()

# --- 3. FUNCIONES DE ANÁLISIS ---
def render_internal_analyst(df):
    """Genera los 4 cuadros de análisis dinámico"""
    if df.empty: return
    
    st.write("### 🧠 Análisis del Analista Interno")
    c1, c2, c3, c4 = st.columns(4)
    
    # 1. Rendimiento Top
    top_asset = df.groupby('asset_Id')['win'].sum().idxmax()
    top_val = df.groupby('asset_Id')['win'].sum().max()
    with c1:
        st.markdown(f"""<div class='metric-card'>
            <div class='metric-label'>Máximo Rendimiento</div>
            <div class='metric-value'>Asset {top_asset}</div>
            <div class='metric-sub'>Generó {form_num(top_val)} en el periodo filtrado.</div>
        </div>""", unsafe_allow_html=True)

    # 2. Eficiencia de Hold
    avg_hold = (df['win'].sum() / df['coin_in'].sum() * 100) if df['coin_in'].sum() > 0 else 0
    with c2:
        st.markdown(f"""<div class='metric-card'>
            <div class='metric-label'>Eficiencia de Hold</div>
            <div class='metric-value'>{avg_hold:.2f}%</div>
            <div class='metric-sub'>Promedio ponderado de la selección actual.</div>
        </div>""", unsafe_allow_html=True)

    # 3. Alerta de Anomalías
    low_performers = df.groupby('asset_Id').filter(lambda x: x['win'].sum() < 0)
    num_neg = len(low_performers['asset_Id'].unique())
    with c3:
        color = "#FF4B4B" if num_neg > 0 else "#00D1FF"
        st.markdown(f"""<div class='metric-card' style='border-bottom-color: {color}'>
            <div class='metric-label'>Anomalías / Win Negativo</div>
            <div class='metric-value'>{num_neg} Activos</div>
            <div class='metric-sub'>Máquinas con Win total negativo en la selección.</div>
        </div>""", unsafe_allow_html=True)

    # 4. Volumen de Juego
    total_ci = df['coin_in'].sum()
    with c4:
        st.markdown(f"""<div class='metric-card'>
            <div class='metric-label'>Volumen Proyectado</div>
            <div class='metric-value'>{form_num(total_ci)}</div>
            <div class='metric-sub'>Total de Coin In procesado en los filtros activos.</div>
        </div>""", unsafe_allow_html=True)

# --- 4. INTERFAZ PRINCIPAL ---
if df_users is not None:
    credentials = {"usernames": {u.lower(): {"name": r['nombre'], "password": str(r['password']), "role": r['rol']} 
                   for u, r in df_users.set_index('usuario').iterrows()}}
    authenticator = stauth.Authenticate(credentials, "vdu_app", "auth_key", 30)
    authenticator.login(location='main')

    if st.session_state.get("authentication_status"):
        with st.sidebar:
            st.title("🛡️ Casino Fuente Mayor")
            st.write(f"Operador: **{st.session_state['name']}**")
            st.divider()
            nav = st.radio("Navegación", ["📊 Dashboard de Sala", "🔄 Analista Comparativo", "👤 Gestión Usuarios"])
            st.write("")
            authenticator.logout('Cerrar Sesión')

        if nav == "📊 Dashboard de Sala":
            st.title("Dashboard Fuente Mayor VDU")
            
            # Selectores de Vista (Restaurados)
            tab_main, tab_excep, tab_marca = st.tabs(["📉 Dashboard Principal", "⚠️ Excepciones", "🏷️ Comparativa Marca"])

            with st.container(border=True):
                r1, r2 = st.columns([1, 3])
                f_rango = r1.date_input("📅 Ventana Temporal", [df_slots['fecha'].min(), df_slots['fecha'].max()])
                c1, c2, c3, c4 = st.columns(4)
                f_id = c1.multiselect("🆔 Asset ID", sorted(df_slots['asset_Id'].unique()))
                f_marca = c2.multiselect("🎰 Marca", sorted(df_slots['marca'].unique()))
                f_modelo = c3.multiselect("📦 Modelo", sorted(df_slots['modelo'].unique()))
                f_juego = c4.multiselect("🎮 Juego", sorted(df_slots['juego'].unique()))
            
            df_f = df_slots.copy()
            if len(f_rango) == 2:
                df_f = df_f[(df_f['fecha'] >= f_rango[0]) & (df_f['fecha'] <= f_rango[1])]
            if f_id: df_f = df_f[df_f['asset_Id'].isin(f_id)]
            if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
            if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]
            if f_juego: df_f = df_f[df_f['juego'].isin(f_juego)]

            with tab_main:
                # KPIs Principales
                wt, ct = df_f['win'].sum(), df_f['coin_in'].sum()
                ht = (wt/ct*100) if ct > 0 else 0
                
                k1, k2, k3 = st.columns(3)
                with k1: st.markdown(f"<div class='main-kpi-label'>NET WIN TOTAL</div><div class='main-kpi-val'>{form_num(wt)}</div>", unsafe_allow_html=True)
                with k2: st.markdown(f"<div class='main-kpi-label'>COIN IN</div><div class='main-kpi-val'>{form_num(ct)}</div>", unsafe_allow_html=True)
                with k3: st.markdown(f"<div class='main-kpi-label'>HOLD REAL %</div><div class='main-kpi-val'>{ht:.2f}%</div>", unsafe_allow_html=True)

                st.plotly_chart(px.area(df_f.groupby('fecha')[['win', 'coin_in']].sum().reset_index(), x='fecha', y=['win', 'coin_in'], template="plotly_dark", color_discrete_sequence=['#00D1FF', '#FF4B4B']), use_container_width=True)
                
                # Cuadros del Analista Interno (Dinamizados)
                render_internal_analyst(df_f)

            with tab_excep:
                st.write("### ⚠️ Máquinas sin Movimiento")
                # Lógica para detectar máquinas con coin_in = 0 en el periodo
                total_assets = df_slots['asset_Id'].unique()
                active_assets = df_f[df_f['coin_in'] > 0]['asset_Id'].unique()
                inactive = [a for a in total_assets if a not in active_assets]
                if f_id: inactive = [a for a in inactive if a in f_id]
                
                if inactive:
                    st.warning(f"Se detectaron {len(inactive)} activos sin Coin In en el rango seleccionado.")
                    st.write(inactive)
                else:
                    st.success("Todos los activos seleccionados presentan actividad.")

            with tab_marca:
                st.write("### 🏷️ Rendimiento por Marca")
                df_m = df_f.groupby('marca')[['win', 'coin_in']].sum().reset_index()
                st.plotly_chart(px.bar(df_m, x='marca', y='win', color='win', template="plotly_dark"), use_container_width=True)

        elif nav == "🔄 Analista Comparativo":
            st.title("⚖️ Diagnóstico Comparativo entre Periodos")
            
            with st.container(border=True):
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Periodo A (Referencia)")
                    r_a = st.date_input("Rango A", [df_slots['fecha'].max() - timedelta(days=30), df_slots['fecha'].max()], key="ra")
                with col2:
                    st.subheader("Periodo B (Comparación)")
                    r_b = st.date_input("Rango B", [df_slots['fecha'].max() - timedelta(days=60), df_slots['fecha'].max() - timedelta(days=31)], key="rb")
                
                # Filtros compartidos para la comparación
                f_comp = st.multiselect("Filtrar comparación por Marca", sorted(df_slots['marca'].unique()))

            if len(r_a) == 2 and len(r_b) == 2:
                df_a = df_slots[(df_slots['fecha'] >= r_a[0]) & (df_slots['fecha'] <= r_a[1])]
                df_b = df_slots[(df_slots['fecha'] >= r_b[0]) & (df_slots['fecha'] <= r_b[1])]
                
                if f_comp:
                    df_a = df_a[df_a['marca'].isin(f_comp)]
                    df_b = df_b[df_b['marca'].isin(f_comp)]

                win_a, win_b = df_a['win'].sum(), df_b['win'].sum()
                diff = win_a - win_b
                per = (diff / win_b * 100) if win_b != 0 else 0

                st.divider()
                c1, c2, c3 = st.columns(3)
                c1.metric("Win Periodo A", form_num(win_a))
                c2.metric("Win Periodo B", form_num(win_b))
                c3.metric("Variación", form_num(diff), f"{per:.2f}%")
                
                # Análisis del analista en comparación
                st.write("### 🧠 Conclusión del Analista")
                if diff > 0:
                    st.success(f"El periodo A presenta un crecimiento de {form_num(diff)} respecto al periodo B.")
                else:
                    st.error(f"Se detecta una caída de rendimiento del {abs(per):.2f}% en el periodo seleccionado.")

        elif nav == "👤 Gestión Usuarios":
            st.title("👤 Administración de Acceso")
            st.dataframe(df_users[['nombre', 'usuario', 'rol']], use_container_width=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Usuario o Contraseña incorrectos')