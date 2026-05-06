import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit_authenticator as stauth
import plotly.express as px
import re
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Dashboard Casino VDU", layout="wide", page_icon="🎰")

# Estilos CSS para mantener la estética original y profesional
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; }
    .main-kpi { background-color: #1E1E2E; padding: 20px; border-radius: 10px; border-bottom: 4px solid #333; }
    </style>
""", unsafe_allow_html=True)

# IDs de Google Sheets
ID_CONFIGURACION = "1W_68ToMyy_nu1oPH7ePFj74_vc1op5bGiFoP4KtaY0I"
ID_DATOS_2026 = "1ZYn6foApzeEeKg_qKzW9faQFjBPXHoc8ffB_CeZ3f_s"
ID_DATOS_2025 = "1aAl_PX1wpBWgTu9bLc81Wn57jSyt8Kqfwm4B4Fsa1W0"
ID_INGRESO_PERSONAS = "1H-j4-gudnexcxnbk0oFMHBJNovDOyWOIWZCLaprEdYw"

# --- FUNCIONES DE CARGA DE DATOS ---

def get_gspread_client():
    """Establece la conexión con Google Sheets usando las credenciales de secrets"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)
def load_data_vdu():
    """Carga y procesa todos los orígenes de datos sin eliminar filas"""
    client = get_gspread_client()
    
    # 1. Carga de Usuarios para Autenticación
    sheet_u = client.open_by_key(ID_CONFIGURACION).worksheet("Usuarios")
    df_u = pd.DataFrame(sheet_u.get_all_records())
    
    # 2. Datos Slots (Cubo 2025 y 2026)
    def fetch_cubo(id_book):
        try:
            sh = client.open_by_key(id_book).worksheet("Cubo")
            data = sh.get_all_values()
            if len(data) < 2: return pd.DataFrame()
            df = pd.DataFrame(data[1:], columns=data[0])
            return df
        except:
            return pd.DataFrame()

    df_25 = fetch_cubo(ID_DATOS_2025)
    df_26 = fetch_cubo(ID_DATOS_2026)
    df_main = pd.concat([df_25, df_26], ignore_index=True)
    
    # 3. Datos Ingreso de Personas
    try:
        sheet_p = client.open_by_key(ID_INGRESO_PERSONAS).worksheet("Cubo")
        data_p = sheet_p.get_all_values()
        if len(data_p) >= 2:
            df_p = pd.DataFrame(data_p[1:], columns=data_p[0])
            df_p.columns = [c.strip() for c in df_p.columns]
            df_p['FECHA'] = pd.to_datetime(df_p['FECHA'], dayfirst=True, errors='coerce').dt.date
            df_p['CANTIDAD'] = pd.to_numeric(df_p['CANTIDAD'], errors='coerce').fillna(0)
        else:
            df_p = pd.DataFrame(columns=['FECHA', 'CANTIDAD'])
    except:
        df_p = pd.DataFrame(columns=['FECHA', 'CANTIDAD'])

    # --- PROCESAMIENTO DE SLOTS ---
    df_main.columns = [c.strip() for c in df_main.columns]
    
    def clean_currency(x):
        """Limpia formatos de moneda sin perder datos por errores de casteo"""
        if pd.isna(x) or str(x).strip() == "": return 0.0
        res = re.sub(r'[^\d.,-]', '', str(x))
        if ',' in res and '.' in res: res = res.replace('.', '').replace(',', '.')
        elif ',' in res: res = res.replace(',', '.')
        try: return float(res)
        except: return 0.0

    columnas_valor = ['COIN IN', 'NET WIN', 'JACKPOT']
    for col in columnas_valor:
        if col in df_main.columns:
            df_main[col] = df_main[col].apply(clean_currency)
        else:
            df_main[col] = 0.0
    
    df_main['FECHA'] = pd.to_datetime(df_main['FECHA'], dayfirst=True, errors='coerce').dt.date
    
    return df_main, df_u, df_p

# Ejecución de carga global
df_slots, df_usuarios, df_personas = load_data_vdu()

# --- SISTEMA DE AUTENTICACIÓN ---
# Se construye el diccionario de configuración respetando la estructura del componente
users_config = {"usernames": {}}
for _, row in df_usuarios.iterrows():
    u = str(row['usuario']).strip()
    users_config["usernames"][u] = {
        "name": str(row['nombre']),
        "password": str(row['password']),
        "role": str(row['rol'])
    }

authenticator = stauth.Authenticate(
    users_config,
    "casino_vdu_cookie",
    "signature_key",
    cookie_expiry_days=30
)

name, authentication_status, username = authenticator.login(location='main')

if authentication_status:
    # --- SIDEBAR NAVEGACIÓN ---
    with st.sidebar:
        st.title("Casino Fuente Mayor")
        st.write(f"Operador: **{name}**")
        st.divider()
        menu = st.radio("Navegación", ["📊 Dashboard de Sala", "📈 Analista Comparativo", "👤 Gestión Usuarios"])
        st.divider()
        authenticator.logout("Cerrar Sesión", "sidebar")

    if menu == "📊 Dashboard de Sala":
        st.title("Dashboard Fuente Mayor VDU")

        # --- SECCIÓN DE FILTROS ---
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            
            # Filtro de fecha dinámico
            valid_dates = df_slots['FECHA'].dropna()
            min_f = valid_dates.min() if not valid_dates.empty else datetime.now().date()
            max_f = valid_dates.max() if not valid_dates.empty else datetime.now().date()
            f_rango = c1.date_input("Ventana Temporal", [min_f, max_f])
            
            # Selectores de categorías
            f_asset = c2.multiselect("🆔 Asset ID", sorted(df_slots['asset_Id'].unique()))
            f_marca = c3.multiselect("🏭 Marca", sorted(df_slots['marca'].unique()) if 'marca' in df_slots.columns else [])
            f_modelo = c4.multiselect("📦 Modelo", sorted(df_slots['modelo'].unique()) if 'modelo' in df_slots.columns else [])

        # Aplicación de Filtros a Slots
        df_f = df_slots.copy()
        if isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
            df_f = df_f[(df_f['FECHA'] >= f_rango[0]) & (df_f['FECHA'] <= f_rango[1])]
        
        if f_asset: df_f = df_f[df_f['asset_Id'].isin(f_asset)]
        if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
        if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]

        # Aplicación de Filtros a Personas
        df_p_f = df_personas.copy()
        if isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
            df_p_f = df_p_f[(df_p_f['FECHA'] >= f_rango[0]) & (df_p_f['FECHA'] <= f_rango[1])]

        # --- FILA DE MÉTRICAS PRINCIPALES ---
        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        
        win_total = df_f['NET WIN'].sum()
        coin_total = df_f['COIN IN'].sum()
        asistencia = df_p_f['CANTIDAD'].sum()
        win_persona = (win_total / asistencia) if asistencia > 0 else 0

        m1.metric("Net Win Total", f"$ {win_total:,.0f}".replace(",", "."))
        m2.metric("Coin In", f"$ {coin_total:,.0f}".replace(",", "."))
        m3.metric("Ingreso Personas", f"{asistencia:,.0f}".replace(",", "."))
        m4.metric("Win / Persona", f"$ {win_persona:,.2f}".replace(",", "."))

        # --- SECCIÓN DE GRÁFICOS ---
        st.divider()
        col_g1, col_g2 = st.columns([2, 1])

        with col_g1:
            st.subheader("Rendimiento Diario (Net Win)")
            df_daily = df_f.groupby('FECHA')['NET WIN'].sum().reset_index()
            fig_win = px.area(df_daily, x='FECHA', y='NET WIN', 
                             line_color='#00d1ff', template="plotly_dark")
            st.plotly_chart(fig_win, use_container_width=True)

        with col_g2:
            st.subheader("Visitas por Día")
            if not df_p_f.empty:
                df_p_daily = df_p_f.groupby('FECHA')['CANTIDAD'].sum().reset_index()
                fig_p = px.bar(df_p_daily, x='FECHA', y='CANTIDAD', 
                              color_discrete_sequence=['#ffaa00'], template="plotly_dark")
                st.plotly_chart(fig_p, use_container_width=True)
            else:
                st.info("Sin datos de visitas en este rango.")

        # Tabla de auditoría
        with st.expander("Detalle de Registros Filtrados"):
            st.dataframe(df_f, use_container_width=True)

    elif menu == "📈 Analista Comparativo":
        st.subheader("Análisis de Performance por Asset")
        if not df_f.empty:
            df_asset_perf = df_f.groupby('asset_Id').agg({
                'NET WIN': 'sum',
                'COIN IN': 'sum'
            }).reset_index()
            df_asset_perf['HOLD %'] = (df_asset_perf['NET WIN'] / df_asset_perf['COIN IN'] * 100).fillna(0)
            st.dataframe(df_asset_perf.sort_values(by='NET WIN', ascending=False), use_container_width=True)
        else:
            st.write("No hay datos para comparar.")

    elif menu == "👤 Gestión Usuarios":
        st.subheader("Panel de Usuarios")
        st.table(df_usuarios[['nombre', 'usuario', 'rol']])

elif authentication_status is False:
    st.error("Credenciales incorrectas. Verifique su usuario y contraseña.")
elif authentication_status is None:
    st.info("Por favor, inicie sesión para acceder al panel de control.")