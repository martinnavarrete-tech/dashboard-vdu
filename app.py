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

# Estilos CSS personalizados para una apariencia Premium y moderna
st.markdown("""
    <style>
    .metric-card {
        background-color: #1E1E2E;  
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #333;
        border-bottom: 4px solid #00D1FF;
        margin-bottom: 15px;
        min-height: 150px;
    }
    .metric-label { color: #A0A0A0; font-size: 0.75rem; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px; }
    .metric-value { color: white; font-size: 1.6rem; font-weight: bold; margin: 8px 0; }
    .metric-sub { font-size: 0.8rem; color: #CCCCCC; line-height: 1.3; }
    .main-kpi-val { font-size: 2.5rem; font-weight: 800; color: #FFFFFF; line-height: 1.1; }
    .main-kpi-label { font-size: 0.85rem; color: #A0A0A0; font-weight: bold; text-transform: uppercase; }
    .analysis-box { background-color: #161625; padding: 20px; border-radius: 10px; border-left: 5px solid #FF4B4B; margin: 10px 0; }
    </style>
""", unsafe_allow_html=True)

def form_num(valor):
    """Formatea números al estilo contable: $ 1.250.000"""
    try:
        if valor is None: return "$ 0"
        return f"$ {valor:,.0f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except:
        return "$ 0"

# IDs de los Libros de Google Sheets
ID_CONFIGURACION = "1W_68ToMyy_nu1oPH7ePFj74_vc1op5bGiFoP4AtaY0I"
ID_DATOS_2026 = "1ZYn6foApzeEeKg_qKzW9faQFjBPXHoc8ffB_CeZ3f_s"
ID_DATOS_2025 = "1aAl_PX1wpBWgTu9bLc81Wn57jSyt8Kqfwm4B4Fsa1W0"

# --- 2. MOTOR DE DATOS Y LIMPIEZA ---

def clean_numeric_vdu(value):
    """
    Limpia strings numéricos de Google Sheets de forma ultra-robusta.
    Maneja casos donde las comas se corrieron o los puntos se malinterpretan.
    """
    if value is None or value == "": return 0.0
    s = str(value).strip()
    if s.lower() in ["nan", "null", "none", "-"]: return 0.0
    
    # 1. Eliminar símbolos de moneda y espacios
    s = s.replace('$', '').replace(' ', '')
    
    # 2. Heurística para detectar separadores:
    # Si hay puntos y comas (ej: 1.250,50) -> es formato latino.
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    # Si hay comas pero no puntos (ej: 1,250.00 o 1250,50)
    elif ',' in s:
        partes = s.split(',')
        # Si la parte final tiene 2 o menos caracteres, probablemente es decimal (ej: 100,50)
        if len(partes[-1]) <= 2:
            s = s.replace(',', '.')
        else:
            # Es un separador de miles (ej: 1,250)
            s = s.replace(',', '')
    
    # 3. Limpiar cualquier carácter que no sea dígito, signo negativo o punto
    s = re.sub(r'[^0-9.\-]', '', s)
    
    # Si después de limpiar hay múltiples puntos, conservar solo el último como decimal
    if s.count('.') > 1:
        partes = s.split('.')
        s = "".join(partes[:-1]) + "." + partes[-1]

    try:
        return float(s)
    except:
        return 0.0

@st.cache_data(ttl=60)
def load_all_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        
        # Cargar configuración de Usuarios
        sheet_u = client.open_by_key(ID_CONFIGURACION).worksheet("Usuarios")
        df_u = pd.DataFrame(sheet_u.get_all_records())
        
        def get_cubo_data(book_id):
            try:
                sheet = client.open_by_key(book_id).worksheet("Cubo")
                data = sheet.get_all_values()
                if not data or len(data) < 2: return pd.DataFrame()
                
                df = pd.DataFrame(data[1:], columns=data[0])
                df = df.loc[:, ~df.columns.str.contains('^$|Unnamed', case=False, na=False)]
                
                # Conversión de fechas (DD/MM/YYYY)
                df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=True, errors='coerce').dt.date
                return df.dropna(subset=['fecha'])
            except Exception:
                return pd.DataFrame()

        # Unificar años 2025 y 2026
        df_2025 = get_cubo_data(ID_DATOS_2025)
        df_2026 = get_cubo_data(ID_DATOS_2026)
        df_s = pd.concat([df_2025, df_2026], ignore_index=True)
        
        if df_s.empty:
            return pd.DataFrame(), df_u

        # Aplicar limpieza numérica a columnas críticas
        for col in ['coin_in', 'win', 'jackpot']:
            if col in df_s.columns:
                df_s[col] = df_s[col].apply(clean_numeric_vdu)
            
        return df_s, df_u
    except Exception as e:
        st.error(f"Error de conexión con Google Sheets: {e}")
        return None, None

df_slots, df_users = load_all_data()

# --- 3. COMPONENTES DE ANÁLISIS ---

def render_kpi_cards(df):
    if df.empty: return
    c1, c2, c3, c4 = st.columns(4)
    
    # Cálculo de métricas
    t_win = df['win'].sum()
    t_ci = df['coin_in'].sum()
    hold = (t_win / t_ci * 100) if t_ci > 0 else 0
    
    with c1:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>NET WIN TOTAL</div><div class='metric-value'>{form_num(t_win)}</div><div class='metric-sub'>Ganancia neta acumulada</div></div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>COIN IN</div><div class='metric-value'>{form_num(t_ci)}</div><div class='metric-sub'>Volumen total de apuestas</div></div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>HOLD REAL %</div><div class='metric-value'>{hold:.2f}%</div><div class='metric-sub'>Retención sobre Coin In</div></div>", unsafe_allow_html=True)
    with c4:
        # Asset con más Win
        df_top = df.groupby('asset_Id')['win'].sum().reset_index()
        top_asset = df_top.sort_values('win', ascending=False).iloc[0] if not df_top.empty else {"asset_Id": "N/A", "win": 0}
        st.markdown(f"<div class='metric-card'><div class='metric-label'>TOP ASSET</div><div class='metric-value'>ID {top_asset['asset_Id']}</div><div class='metric-sub'>Líder en rendimiento</div></div>", unsafe_allow_html=True)

# --- 4. INTERFAZ Y NAVEGACIÓN ---

if df_users is not None:
    credentials = {"usernames": {u.lower(): {"name": r['nombre'], "password": str(r['password']), "role": r['rol']} 
                   for u, r in df_users.set_index('usuario').iterrows()}}
    authenticator = stauth.Authenticate(credentials, "vdu_app", "auth_key", 30)
    authenticator.login(location='main')

    if st.session_state.get("authentication_status"):
        with st.sidebar:
            st.title("🎰 Casino VDU")
            st.write(f"Usuario: **{st.session_state['name']}**")
            st.divider()
            nav = st.radio("Navegación", ["📊 Dashboard Principal", "⚖️ Comparativo Años", "👤 Usuarios"])
            st.divider()
            authenticator.logout('Cerrar Sesión', 'sidebar')

        # --- SECCIÓN DASHBOARD PRINCIPAL ---
        if nav == "📊 Dashboard Principal":
            st.title("Dashboard Fuente Mayor VDU")
            
            if df_slots is not None and not df_slots.empty:
                # Filtros en contenedor
                with st.container(border=True):
                    f1, f2 = st.columns([1, 3])
                    
                    # PREVENCIÓN ERROR MIN/MAX (Empty sequence)
                    safe_min = df_slots['fecha'].min() if not df_slots['fecha'].empty else datetime.now().date()
                    safe_max = df_slots['fecha'].max() if not df_slots['fecha'].empty else datetime.now().date()
                    
                    rango = f1.date_input("📅 Rango de Fechas", [safe_min, safe_max])
                    
                    c1, c2, c3, c4 = st.columns(4)
                    f_id = c1.multiselect("🆔 Asset ID", sorted(df_slots['asset_Id'].unique()))
                    f_marca = c2.multiselect("🎰 Marca", sorted(df_slots['marca'].unique()))
                    f_modelo = c3.multiselect("📦 Modelo", sorted(df_slots['modelo'].unique()))
                    f_juego = c4.multiselect("🎮 Juego", sorted(df_slots['juego'].unique()))
                
                # Aplicar Filtros
                df_f = df_slots.copy()
                if isinstance(rango, (list, tuple)) and len(rango) == 2:
                    df_f = df_f[(df_f['fecha'] >= rango[0]) & (df_f['fecha'] <= rango[1])]
                
                if f_id: df_f = df_f[df_f['asset_Id'].isin(f_id)]
                if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
                if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]
                if f_juego: df_f = df_f[df_f['juego'].isin(f_juego)]

                # Visualización
                render_kpi_cards(df_f)
                
                tab_evol, tab_dist = st.tabs(["📈 Evolución", "📊 Distribución"])
                
                with tab_evol:
                    df_daily = df_f.groupby('fecha')[['win', 'coin_in']].sum().reset_index()
                    if not df_daily.empty:
                        fig = px.area(df_daily, x='fecha', y=['win', 'coin_in'], 
                                     template="plotly_dark", 
                                     color_discrete_map={"win": "#00D1FF", "coin_in": "#FF4B4B"},
                                     title="Win vs Coin In Diario")
                        st.plotly_chart(fig, use_container_width=True)
                
                with tab_dist:
                    col_a, col_b = st.columns(2)
                    with col_a:
                        df_m = df_f.groupby('marca')['win'].sum().reset_index()
                        st.plotly_chart(px.pie(df_m, names='marca', values='win', title="Win por Marca", hole=0.4, template="plotly_dark"), use_container_width=True)
                    with col_b:
                        df_mod = df_f.groupby('modelo')['win'].sum().reset_index().sort_values('win', ascending=False).head(10)
                        st.plotly_chart(px.bar(df_mod, x='modelo', y='win', title="Top 10 Modelos (Win)", template="plotly_dark"), use_container_width=True)
            else:
                st.warning("⚠️ No hay datos disponibles para mostrar.")

        # --- SECCIÓN ANALISTA COMPARATIVO ---
        elif nav == "⚖️ Comparativo Años":
            st.title("⚖️ Diagnóstico de Variación")
            st.info("Compare el rendimiento entre dos periodos específicos.")
            
            with st.container(border=True):
                col1, col2 = st.columns(2)
                f_max = df_slots['fecha'].max()
                r_a = col1.date_input("Periodo A (Actual)", [f_max - timedelta(days=7), f_max])
                r_b = col2.date_input("Periodo B (Anterior)", [f_max - timedelta(days=15), f_max - timedelta(days=8)])
            
            if len(r_a) == 2 and len(r_b) == 2:
                df_a = df_slots[(df_slots['fecha'] >= r_a[0]) & (df_slots['fecha'] <= r_a[1])]
                df_b = df_slots[(df_slots['fecha'] >= r_b[0]) & (df_slots['fecha'] <= r_b[1])]
                
                wa, wb = df_a['win'].sum(), df_b['win'].sum()
                ca, cb = df_a['coin_in'].sum(), df_b['coin_in'].sum()
                
                diff_w = wa - wb
                pct_w = (diff_w / wb * 100) if wb != 0 else 0
                
                k1, k2 = st.columns(2)
                k1.metric("Variación Win", form_num(diff_w), f"{pct_w:.2f}%")
                k2.metric("Variación Coin In", form_num(ca - cb), f"{((ca-cb)/cb*100 if cb!=0 else 0):.2f}%")
                
                st.write("### 🕵️ Diagnóstico del Auditor")
                if pct_w > 0:
                    st.success(f"El Win ha incrementado un {pct_w:.2f}% respecto al periodo anterior.")
                else:
                    st.error(f"Se detectó una caída del {abs(pct_w):.2f}% en el Win neto.")

        # --- SECCIÓN GESTIÓN ---
        elif nav == "👤 Usuarios":
            st.title("Gestión de Acceso")
            st.dataframe(df_users[['nombre', 'usuario', 'rol']], use_container_width=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Credenciales incorrectas. Verifique usuario y contraseña.')