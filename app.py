import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit_authenticator as stauth
import plotly.express as px
import re
from datetime import datetime, timedelta

# --- 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS VISUALES ---
st.set_page_config(page_title="Dashboard VDU - Fuente Mayor", layout="wide", page_icon="🎰")

# Estilos CSS personalizados para mantener la estética oscura y profesional
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; color: #ffffff; }
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
    }
    .report-title { color: #00D1FF; font-weight: bold; margin-bottom: 8px; text-transform: uppercase; font-size: 0.85rem; }
    .main-kpi-val { font-size: 2.5rem; font-weight: 800; color: #FFFFFF; }
    .main-kpi-label { font-size: 0.8rem; color: #A0A0A0; text-transform: uppercase; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

def form_num(valor):
    """Formatea números al estilo contable local: $ 1.250.000"""
    try:
        if pd.isna(valor): return "$ 0"
        return f"$ {valor:,.0f}".replace(',', '.')
    except:
        return "$ 0"

# IDs de los Libros de Google Sheets (Configuración y Datos)
ID_CONFIGURACION = "1W_68ToMyy_nu1oPH7ePFj74_vc1op5bGiFoP4KtaY0I"
ID_DATOS_2026 = "1ZYn6foApzeEeKg_qKzW9faQFjBPXHoc8ffB_CeZ3f_s"
ID_DATOS_2025 = "1aAl_PX1wpBWgTu9bLc81Wn57jSyt8Kqfwm4B4Fsa1W0"
ID_INGRESO_PERSONAS = "1H-j4-gudnexcxnbk0oFMHBJNovDOyWOIWZCLaprEdYw"

# --- 2. MOTOR DE DATOS (LECTURA Y LIMPIEZA) ---
@st.cache_data(ttl=60)
def load_all_data():
    """Carga y procesa todos los orígenes de datos sin eliminar filas por error"""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        
        # --- A. CARGA DE USUARIOS ---
        sheet_u = client.open_by_key(ID_CONFIGURACION).worksheet("Usuarios")
        df_u = pd.DataFrame(sheet_u.get_all_records())
        df_u.columns = [str(c).strip() for c in df_u.columns]
        
        # --- B. CARGA DE DATOS DE SLOTS (CUBO) ---
        def get_cubo_data(book_id):
            try:
                sheet = client.open_by_key(book_id).worksheet("Cubo")
                data = sheet.get_all_values()
                if len(data) < 2: return pd.DataFrame()
                
                df = pd.DataFrame(data[1:], columns=data[0])
                df.columns = [str(c).strip() for c in df.columns]
                
                # Mapeo de columnas para asegurar compatibilidad
                df = df.rename(columns={
                    'asset_id': 'asset_Id', 'Asset ID': 'asset_Id', 'Asset id': 'asset_Id',
                    'FECHA': 'fecha', 'Fecha': 'fecha',
                    'COIN IN': 'coin_in', 'COIN_IN': 'coin_in',
                    'WIN': 'win', 'NET WIN': 'win',
                    'JACKPOT': 'jackpot'
                })
                
                # Conversión de fecha amigable (no elimina filas, pone NaT si falla)
                df['fecha_dt'] = pd.to_datetime(df['fecha'], dayfirst=True, errors='coerce')
                df['fecha'] = df['fecha_dt'].dt.date
                return df
            except Exception as e:
                st.warning(f"Error cargando hoja Cubo en ID {book_id}: {e}")
                return pd.DataFrame()

        df_2025 = get_cubo_data(ID_DATOS_2025)
        df_2026 = get_cubo_data(ID_DATOS_2026)
        df_s = pd.concat([df_2025, df_2026], ignore_index=True)
        
        def clean_currency(x):
            """Limpia formatos de moneda complejos sin perder el dato"""
            if x is None or str(x).strip() == "" or str(x).lower() == "nan": return 0.0
            cleaned = re.sub(r'[^\d.,-]', '', str(x))
            # Lógica para detectar separador decimal (coma vs punto)
            if ',' in cleaned and '.' in cleaned:
                cleaned = cleaned.replace('.', '').replace(',', '.')
            elif ',' in cleaned:
                cleaned = cleaned.replace(',', '.')
            try: 
                return float(cleaned)
            except: 
                return 0.0

        # Aplicar limpieza de valores numéricos
        columnas_dinero = ['coin_in', 'win', 'jackpot']
        for col in columnas_dinero:
            if col in df_s.columns:
                df_s[col] = df_s[col].apply(clean_currency)
            else:
                df_s[col] = 0.0

        # --- C. CARGA DE INGRESO DE PERSONAS ---
        try:
            sheet_p = client.open_by_key(ID_INGRESO_PERSONAS).worksheet("Cubo")
            data_p = sheet_p.get_all_values()
            if len(data_p) >= 2:
                df_p = pd.DataFrame(data_p[1:], columns=data_p[0])
                df_p.columns = [str(c).strip() for c in df_p.columns]
                df_p = df_p.rename(columns={'FECHA': 'fecha', 'Fecha': 'fecha', 'CANTIDAD': 'cantidad'})
                df_p['fecha_dt'] = pd.to_datetime(df_p['fecha'], dayfirst=True, errors='coerce')
                df_p['fecha'] = df_p['fecha_dt'].dt.date
                df_p['cantidad'] = pd.to_numeric(df_p['cantidad'], errors='coerce').fillna(0)
            else:
                df_p = pd.DataFrame(columns=['fecha', 'cantidad'])
        except Exception:
            df_p = pd.DataFrame(columns=['fecha', 'cantidad'])
            
        return df_s, df_u, df_p
    except Exception as e:
        st.error(f"Error crítico en el motor de datos: {e}")
        return None, None, None

# Ejecutar carga inicial
df_slots, df_users, df_personas = load_all_data()

# --- 3. SISTEMA DE AUTENTICACIÓN ---
if df_users is not None:
    # Preparar credenciales desde el DataFrame de Usuarios
    user_dict = {}
    for _, row in df_users.iterrows():
        u = str(row['usuario']).lower().strip()
        user_dict[u] = {
            "name": str(row['nombre']),
            "password": str(row['password']),
            "role": str(row['rol'])
        }
    
    credentials = {"usernames": user_dict}
    authenticator = stauth.Authenticate(credentials, "casino_vdu_session", "vdu_key_2024", 30)
    
    # Login en pantalla principal
    name, authentication_status, username = authenticator.login(location='main')

    if authentication_status:
        # --- SIDEBAR DE NAVEGACIÓN ---
        with st.sidebar:
            st.image("https://fuentemayor.com.ar/wp-content/uploads/2021/04/Logo-Fuente-Mayor-Hotel-Casino.png", width=150)
            st.title("Sistema VDU")
            st.markdown(f"Bienvenido, **{name}**")
            st.divider()
            nav = st.radio("Secciones", ["📊 Dashboard General", "📈 Análisis Detallado", "⚙️ Administración"])
            st.divider()
            authenticator.logout('Cerrar Sesión', 'sidebar')

        # --- SECCIÓN: DASHBOARD GENERAL ---
        if nav == "📊 Dashboard General":
            st.title("Estado de Sala en Tiempo Real")
            
            if df_slots is not None and not df_slots.empty:
                # Filtros Globales
                with st.expander("🔍 Filtros Avanzados", expanded=True):
                    f_col1, f_col2 = st.columns([1, 2])
                    
                    # Rango de fechas dinámico basado en los datos cargados
                    min_date = df_slots['fecha'].min() if not df_slots['fecha'].isnull().all() else datetime.now().date()
                    max_date = df_slots['fecha'].max() if not df_slots['fecha'].isnull().all() else datetime.now().date()
                    
                    rango = f_col1.date_input("Periodo", [min_date, max_date])
                    
                    # Selectores multiselect
                    col_ids, col_mrc, col_mod = st.columns(3)
                    f_ids = col_ids.multiselect("Asset IDs", sorted(df_slots['asset_Id'].unique()))
                    f_marcas = col_mrc.multiselect("Marcas", sorted(df_slots['marca'].unique()) if 'marca' in df_slots.columns else [])
                    f_modelos = col_mod.multiselect("Modelos", sorted(df_slots['modelo'].unique()) if 'modelo' in df_slots.columns else [])

                # Aplicar Filtros al DataFrame de Slots
                df_f = df_slots.copy()
                if len(rango) == 2:
                    df_f = df_f[(df_f['fecha'] >= rango[0]) & (df_f['fecha'] <= rango[1])]
                
                if f_ids: df_f = df_f[df_f['asset_Id'].isin(f_ids)]
                if f_marcas: df_f = df_f[df_f['marca'].isin(f_marcas)]
                if f_modelos: df_f = df_f[df_f['modelo'].isin(f_modelos)]

                # Filtrar datos de Personas según fecha
                df_p_f = df_personas.copy()
                if len(rango) == 2:
                    df_p_f = df_p_f[(df_p_f['fecha'] >= rango[0]) & (df_p_f['fecha'] <= rango[1])]
                total_ingresos = df_p_f['cantidad'].sum()

                # --- FILA DE KPIs ---
                total_win = df_f['win'].sum()
                total_coin = df_f['coin_in'].sum()
                hold_pct = (total_win / total_coin * 100) if total_coin > 0 else 0
                win_persona = (total_win / total_ingresos) if total_ingresos > 0 else 0

                k1, k2, k3, k4 = st.columns(4)
                with k1: st.markdown(f"<div class='main-kpi-label'>NET WIN TOTAL</div><div class='main-kpi-val'>{form_num(total_win)}</div>", unsafe_allow_html=True)
                with k2: st.markdown(f"<div class='main-kpi-label'>COIN IN (APUESTAS)</div><div class='main-kpi-val'>{form_num(total_coin)}</div>", unsafe_allow_html=True)
                with k3: st.markdown(f"<div class='main-kpi-label'>INGRESO PERSONAS</div><div class='main-kpi-val'>{total_ingresos:,.0f}</div>", unsafe_allow_html=True)
                with k4: st.markdown(f"<div class='main-kpi-label'>WIN / PERSONA</div><div class='main-kpi-val'>{form_num(win_persona)}</div>", unsafe_allow_html=True)

                st.divider()

                # --- GRÁFICOS Y ANALÍTICA ---
                g1, g2 = st.columns([2, 1])
                
                with g1:
                    st.subheader("Evolución Temporal: Win vs Coin-In")
                    df_time = df_f.groupby('fecha')[['win', 'coin_in']].sum().reset_index()
                    fig_time = px.line(df_time, x='fecha', y=['win', 'coin_in'], 
                                       color_discrete_map={'win': '#00FFCC', 'coin_in': '#FF4B4B'},
                                       template="plotly_dark")
                    st.plotly_chart(fig_time, use_container_width=True)

                with g2:
                    st.subheader("🤖 Resumen del Analista")
                    if not df_f.empty:
                        best_asset = df_f.groupby('asset_Id')['win'].sum().idxmax()
                        val_asset = df_f.groupby('asset_Id')['win'].sum().max()
                        
                        st.markdown(f"""
                        <div class='report-box'>
                            <div class='report-title'>Activo más Rentable</div>
                            <p>El Asset ID <b>{best_asset}</b> es el líder del periodo con una recaudación de {form_num(val_asset)}.</p>
                        </div>
                        <div class='report-box'>
                            <div class='report-title'>Eficiencia de Hold</div>
                            <p>La sala está operando con un hold promedio del <b>{hold_pct:.2f}%</b>.</p>
                        </div>
                        """, unsafe_allow_html=True)

                # --- TABLA DE DATOS CRUDA (Para verificar que no faltan filas) ---
                with st.expander("📋 Ver registros filtrados"):
                    st.dataframe(df_f, use_container_width=True)
            else:
                st.warning("Cargando datos o no hay datos disponibles para los filtros seleccionados.")

        elif nav == "📈 Análisis Detallado":
            st.title("Análisis por Máquina / Fabricante")
            st.info("Esta sección permite comparar el rendimiento individual de cada terminal.")
            # Aquí iría la lógica de comparación de assets

        elif nav == "⚙️ Administración":
            st.title("Panel de Administración")
            if st.session_state.get('role') == 'admin':
                st.write("Gestión de accesos y configuración de Google Sheets.")
            else:
                st.error("No tienes permisos suficientes para acceder a esta sección.")

    elif authentication_status is False:
        st.error("Usuario o contraseña incorrectos")
    elif authentication_status is None:
        st.info("Por favor, ingrese sus credenciales para acceder al Dashboard.")