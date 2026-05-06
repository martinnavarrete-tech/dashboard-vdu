import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit_authenticator as stauth
import plotly.express as px
import re
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
    }
    .report-box { 
        background-color: #161625; 
        padding: 20px; 
        border-radius: 10px; 
        border-left: 5px solid #00D1FF; 
        margin-bottom: 20px;
        min-height: 150px;
    }
    .report-title { color: #00D1FF; font-weight: bold; margin-bottom: 10px; text-transform: uppercase; font-size: 0.9rem; }
    .report-text { color: #E0E0E0; font-size: 0.85rem; line-height: 1.4; }
    .main-kpi-val { font-size: 2.8rem; font-weight: 800; color: #FFFFFF; line-height: 1.1; }
    .main-kpi-label { font-size: 0.9rem; color: #A0A0A0; text-transform: uppercase; font-weight: bold; }
    .highlight-red { color: #FF4B4B; font-weight: bold; }
    .highlight-green { color: #00FFCC; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

def form_num(valor):
    """Formatea números al estilo contable: $ 1.250.000"""
    try:
        return f"$ {valor:,.0f}".replace(',', '.')
    except:
        return "$ 0"

# IDs de los Libros de Google Sheets
ID_CONFIGURACION = "1W_68ToMyy_nu1oPH7ePFj74_vc1op5bGiFoP4KtaY0I"
ID_DATOS_2026 = "1ZYn6foApzeEeKg_qKzW9faQFjBPXHoc8ffB_CeZ3f_s"
ID_DATOS_2025 = "1aAl_PX1wpBWgTu9bLc81Wn57jSyt8Kqfwm4B4Fsa1W0"
ID_INGRESO_PERSONAS = "1H-j4-gudnexcxnbk0oFMHBJNovDOyWOIWZCLaprEdYw"

# --- 2. MOTOR DE DATOS ---
@st.cache_data(ttl=60)
def load_all_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        
        # 1. Cargar Usuarios con limpieza extrema de columnas
        try:
            sheet_u = client.open_by_key(ID_CONFIGURACION).worksheet("Usuarios")
            data_u = sheet_u.get_all_records()
            if not data_u:
                return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
            
            df_u = pd.DataFrame(data_u)
            # Limpiar nombres de columnas: quitar espacios, saltos de línea y pasar a minúsculas
            df_u.columns = [re.sub(r'[^a-z0-9]', '', str(c).lower().strip()) for c in df_u.columns]
        except Exception as e:
            st.error(f"Error cargando pestaña 'Usuarios': {e}")
            df_u = pd.DataFrame()
        
        # 2. Función para extraer datos de Máquinas (Hoja Cubo)
        def get_cubo_data(book_id):
            try:
                sheet = client.open_by_key(book_id).worksheet("Cubo")
                data = sheet.get_all_values()
                if not data: return pd.DataFrame()
                df = pd.DataFrame(data[1:], columns=data[0])
                df.columns = [str(c).strip() for c in df.columns]
                df = df.rename(columns={'asset_id': 'asset_Id', 'Asset ID': 'asset_Id', 'Asset id': 'asset_Id'})
                df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=True, errors='coerce').dt.date
                for col in ['coin_in', 'win', 'jackpot']:
                    if col in df.columns:
                        df[col] = df[col].apply(lambda x: float(re.sub(r'[^\d.]', '', str(x).replace(',','.'))) if x else 0.0)
                return df.dropna(subset=['fecha'])
            except: return pd.DataFrame()

        df_2025 = get_cubo_data(ID_DATOS_2025)
        df_2026 = get_cubo_data(ID_DATOS_2026)
        df_slots = pd.concat([df_2025, df_2026], ignore_index=True)

        # 3. Cargar Ingreso de Personas
        try:
            sheet_p = client.open_by_key(ID_INGRESO_PERSONAS).worksheet("Cubo")
            data_p = sheet_p.get_all_values()
            df_p = pd.DataFrame(data_p[1:], columns=data_p[0])
            df_p.columns = [str(c).strip() for c in df_p.columns]
            df_p['fecha'] = pd.to_datetime(df_p['fecha'], dayfirst=True, errors='coerce').dt.date
            df_p['cantidad'] = pd.to_numeric(df_p['cantidad'], errors='coerce').fillna(0)
            df_p = df_p.dropna(subset=['fecha'])
        except:
            df_p = pd.DataFrame()
            
        return df_slots, df_u, df_p
    except Exception as e:
        st.error(f"Error crítico de conexión: {e}")
        return None, None, None

df_slots, df_users, df_personas = load_all_data()

# --- 3. INTERFAZ PRINCIPAL ---
if df_users is not None and not df_users.empty:
    # Columnas esperadas después de la limpieza extrema (solo letras y números, minúsculas)
    # 'usuario' -> 'usuario', 'nombre' -> 'nombre', etc.
    cols_actuales = list(df_users.columns)
    required = ['usuario', 'nombre', 'password', 'rol']
    
    if all(c in cols_actuales for c in required):
        credentials = {"usernames": {}}
        for _, row in df_users.iterrows():
            user_key = str(row['usuario']).lower().strip()
            credentials["usernames"][user_key] = {
                "name": str(row['nombre']),
                "password": str(row['password']),
                "role": str(row['rol'])
            }
        
        authenticator = stauth.Authenticate(credentials, "vdu_app", "auth_key", 30)
        authenticator.login(location='main')
    else:
        st.error("⚠️ Error de estructura en la tabla 'Usuarios'")
        st.write("El sistema busca estas columnas: `usuario`, `nombre`, `password`, `rol`.")
        st.write("Columnas detectadas en tu Sheets:", cols_actuales)
        st.info("💡 Por favor, asegúrate de que la primera fila de tu hoja 'Usuarios' tenga exactamente esos nombres.")
        st.stop()

    if st.session_state.get("authentication_status"):
        with st.sidebar:
            st.title("🛡️ Casino Fuente Mayor")
            st.write(f"Operador: **{st.session_state['name']}**")
            st.divider()
            nav = st.radio("Navegación", ["📊 Dashboard de Sala", "🔄 Analista Comparativo", "👤 Gestión Usuarios"])
            st.write("")
            authenticator.logout('Cerrar Sesión', 'sidebar')

        if nav == "📊 Dashboard de Sala":
            st.title("Dashboard Fuente Mayor VDU")
            
            if not df_slots.empty:
                # Filtros Globales
                with st.container(border=True):
                    r1, r2 = st.columns([1, 3])
                    f_rango = r1.date_input("📅 Ventana Temporal", [df_slots['fecha'].min(), df_slots['fecha'].max()])
                    
                    c1, c2, c3, c4 = st.columns(4)
                    f_id = c1.multiselect("🆔 Asset ID", sorted(df_slots['asset_Id'].unique()))
                    f_marca = c2.multiselect("🎰 Marca", sorted(df_slots['marca'].unique()))
                    f_modelo = c3.multiselect("📦 Modelo", sorted(df_slots['modelo'].unique()))
                    f_juego = c4.multiselect("🎮 Juego", sorted(df_slots['juego'].unique()))
                
                # Aplicar Filtros
                df_f = df_slots.copy()
                if isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
                    df_f = df_f[(df_f['fecha'] >= f_rango[0]) & (df_f['fecha'] <= f_rango[1])]
                
                if f_id: df_f = df_f[df_f['asset_Id'].isin(f_id)]
                if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
                if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]
                if f_juego: df_f = df_f[df_f['juego'].isin(f_juego)]

                # KPIs Principales
                wt = df_f['win'].sum()
                ct = df_f['coin_in'].sum()
                
                # Ingreso personas
                mask_p = (df_personas['fecha'] >= f_rango[0]) & (df_personas['fecha'] <= f_rango[1]) if len(f_rango)==2 else True
                df_p_f = df_personas[mask_p]
                total_p = df_p_f['cantidad'].sum()
                win_persona = (wt / total_p) if total_p > 0 else 0

                k1, k2, k3, k4 = st.columns(4)
                k1.markdown(f"<div class='main-kpi-label'>NET WIN TOTAL</div><div class='main-kpi-val'>{form_num(wt)}</div>", unsafe_allow_html=True)
                k2.markdown(f"<div class='main-kpi-label'>COIN IN</div><div class='main-kpi-val'>{form_num(ct)}</div>", unsafe_allow_html=True)
                k3.markdown(f"<div class='main-kpi-label'>INGRESOS</div><div class='main-kpi-val'>{total_p:,.0f}</div>", unsafe_allow_html=True)
                k4.markdown(f"<div class='main-kpi-label'>WIN/PERSONA</div><div class='main-kpi-val'>{form_num(win_persona)}</div>", unsafe_allow_html=True)

                # --- ANALISTA ---
                st.divider()
                st.subheader("🤖 Analista Interno")
                a1, a2, a3, a4 = st.columns(4)
                
                with a1:
                    if not df_f.empty:
                        res_m = df_f.groupby('marca')['win'].sum()
                        top_marca = res_m.idxmax()
                        st.markdown(f"<div class='report-box'><div class='report-title'>Líder</div><div class='report-text'><b>{top_marca}</b> es la marca más rentable del periodo.</div></div>", unsafe_allow_html=True)
                with a2:
                    if not df_f.empty:
                        hold_avg = (wt/ct*100) if ct>0 else 0
                        st.markdown(f"<div class='report-box'><div class='report-title'>Hold General</div><div class='report-text'>El hold promedio de sala es de <b>{hold_avg:.2f}%</b>.</div></div>", unsafe_allow_html=True)
                with a3:
                    jack_sum = df_f['jackpot'].sum()
                    st.markdown(f"<div class='report-box'><div class='report-title'>Jackpots</div><div class='report-text'>Total pagado: <b>{form_num(jack_sum)}</b>.</div></div>", unsafe_allow_html=True)
                with a4:
                    n_m = len(df_f['asset_Id'].unique())
                    prom = (wt/n_m) if n_m>0 else 0
                    st.markdown(f"<div class='report-box'><div class='report-title'>Eficiencia</div><div class='report-text'>Win promedio por máquina: <b>{form_num(prom)}</b>.</div></div>", unsafe_allow_html=True)

        elif nav == "🔄 Analista Comparativo":
            st.title("⚖️ Comparativa")
            st.info("Seleccione periodos en la barra lateral o filtros de fecha.")

        elif nav == "👤 Gestión Usuarios":
            st.title("👤 Administración")
            st.dataframe(df_users, use_container_width=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Usuario o Contraseña incorrectos')
else:
    st.warning("No se pudo cargar la base de usuarios.")