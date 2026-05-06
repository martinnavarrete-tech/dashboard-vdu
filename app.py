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

# --- 2. MOTOR DE DATOS ---
@st.cache_data(ttl=60)
def load_all_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        
        # 1. Cargar Usuarios
        sheet_u = client.open_by_key(ID_CONFIGURACION).worksheet("Usuarios")
        df_u = pd.DataFrame(sheet_u.get_all_records())
        df_u.columns = [str(c).strip() for c in df_u.columns]
        
        # 2. Función para extraer específicamente la hoja "Cubo"
        def get_cubo_data(book_id):
            try:
                sheet = client.open_by_key(book_id).worksheet("Cubo")
                data = sheet.get_all_values()
                if not data or len(data) < 2:
                    return pd.DataFrame()
                
                df = pd.DataFrame(data[1:], columns=data[0])
                df.columns = [str(c).strip() for c in df.columns]
                
                # Mapeo de columnas para asegurar compatibilidad
                mapeo = {
                    'asset_id': 'asset_Id', 'Asset ID': 'asset_Id', 'Asset id': 'asset_Id',
                    'FECHA': 'fecha', 'Fecha': 'fecha',
                    'COIN IN': 'coin_in', 'COIN_IN': 'coin_in',
                    'WIN': 'win', 'NET WIN': 'win', 'NET_WIN': 'win',
                    'JACKPOT': 'jackpot'
                }
                df = df.rename(columns=mapeo)
                
                df = df.loc[:, ~df.columns.str.contains('^$|Unnamed', case=False, na=False)]
                df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=True, errors='coerce').dt.date
                return df.dropna(subset=['fecha'])
            except Exception as e:
                st.warning(f"Aviso: Error en el libro {book_id}. Error: {e}")
                return pd.DataFrame()

        df_2025 = get_cubo_data(ID_DATOS_2025)
        df_2026 = get_cubo_data(ID_DATOS_2026)
        df_s = pd.concat([df_2025, df_2026], ignore_index=True)
        
        # 3. Cargar Ingreso de Personas
        try:
            sheet_p = client.open_by_key(ID_INGRESO_PERSONAS).worksheet("Cubo")
            data_p = sheet_p.get_all_values()
            if len(data_p) >= 2:
                df_p = pd.DataFrame(data_p[1:], columns=data_p[0])
                df_p.columns = [str(c).strip() for c in df_p.columns]
                df_p = df_p.rename(columns={'FECHA': 'fecha', 'Fecha': 'fecha', 'CANTIDAD': 'cantidad'})
                df_p['fecha'] = pd.to_datetime(df_p['fecha'], dayfirst=True, errors='coerce').dt.date
                df_p['cantidad'] = pd.to_numeric(df_p['cantidad'], errors='coerce').fillna(0)
                df_p = df_p.dropna(subset=['fecha'])
            else:
                df_p = pd.DataFrame(columns=['fecha', 'cantidad'])
        except:
            df_p = pd.DataFrame(columns=['fecha', 'cantidad'])

        if df_s.empty:
            return pd.DataFrame(), df_u, df_p

        # Limpieza de Moneda
        def clean_currency(x):
            if not x or str(x).strip() == "": return 0.0
            cleaned = re.sub(r'[^\d.,-]', '', str(x))
            if ',' in cleaned and '.' in cleaned:
                cleaned = cleaned.replace('.', '').replace(',', '.')
            elif ',' in cleaned:
                cleaned = cleaned.replace(',', '.')
            try: return float(cleaned)
            except: return 0.0

        for col in ['coin_in', 'win', 'jackpot']:
            if col in df_s.columns:
                df_s[col] = df_s[col].apply(clean_currency)
            else:
                df_s[col] = 0.0
            
        return df_s, df_u, df_p
    except Exception as e:
        st.error(f"Error crítico de sincronización: {e}")
        return None, None, None

# Ejecución de carga global
df_slots, df_usuarios, df_personas = load_all_data()

# --- SISTEMA DE AUTENTICACIÓN ---
users_config = {"usernames": {}}
if df_usuarios is not None:
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
            valid_dates = df_slots['fecha'].dropna()
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
            df_f = df_f[(df_f['fecha'] >= f_rango[0]) & (df_f['fecha'] <= f_rango[1])]
        
        if f_asset: df_f = df_f[df_f['asset_Id'].isin(f_asset)]
        if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
        if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]

        # Aplicación de Filtros a Personas
        df_p_f = df_personas.copy() if df_personas is not None else pd.DataFrame()
        if not df_p_f.empty and isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
            df_p_f = df_p_f[(df_p_f['fecha'] >= f_rango[0]) & (df_p_f['fecha'] <= f_rango[1])]

        # --- FILA DE MÉTRICAS PRINCIPALES ---
        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        
        win_total = df_f['win'].sum()
        coin_total = df_f['coin_in'].sum()
        asistencia = df_p_f['cantidad'].sum() if not df_p_f.empty else 0
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
            df_daily = df_f.groupby('fecha')['win'].sum().reset_index()
            fig_win = px.area(df_daily, x='fecha', y='win', 
                             line_color='#00d1ff', template="plotly_dark")
            st.plotly_chart(fig_win, use_container_width=True)

        with col_g2:
            st.subheader("Visitas por Día")
            if not df_p_f.empty:
                df_p_daily = df_p_f.groupby('fecha')['cantidad'].sum().reset_index()
                fig_p = px.bar(df_p_daily, x='fecha', y='cantidad', 
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
                'win': 'sum',
                'coin_in': 'sum'
            }).reset_index()
            df_asset_perf['HOLD %'] = (df_asset_perf['win'] / df_asset_perf['coin_in'] * 100).fillna(0)
            st.dataframe(df_asset_perf.sort_values(by='win', ascending=False), use_container_width=True)
        else:
            st.write("No hay datos para comparar.")

    elif menu == "👤 Gestión Usuarios":
        st.subheader("Panel de Usuarios")
        st.table(df_usuarios[['nombre', 'usuario', 'rol']])

elif authentication_status is False:
    st.error("Credenciales incorrectas. Verifique su usuario y contraseña.")
elif authentication_status is None:
    st.info("Por favor, inicie sesión para acceder al panel de control.")