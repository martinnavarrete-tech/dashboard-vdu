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
        border-radius: 12px;
        border: 1px solid #333;
        border-bottom: 4px solid #00D1FF;
        margin-bottom: 15px;
        min-height: 150px;
    }
    .metric-label { color: #A0A0A0; font-size: 0.75rem; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px; }
    .metric-value { color: white; font-size: 1.4rem; font-weight: bold; margin: 8px 0; }
    .metric-sub { font-size: 0.8rem; color: #CCCCCC; line-height: 1.3; }
    .main-kpi-val { font-size: 2.2rem; font-weight: 800; color: #FFFFFF; }
    .main-kpi-label { font-size: 0.85rem; color: #A0A0A0; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

def form_num(valor):
    try:
        return f"$ {valor:,.0f}".replace(',', '.')
    except:
        return "$ 0"

# IDs de los Libros de Google Sheets
ID_CONFIGURACION = "1W_68ToMyy_nu1oPH7ePFj74_vc1op5bGiFoP4AtaY0I"
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
                df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=True, errors='coerce').dt.date
                return df.dropna(subset=['fecha'])
            except: return pd.DataFrame()

        df_2025 = get_cubo_data(ID_DATOS_2025)
        df_2026 = get_cubo_data(ID_DATOS_2026)
        df_s = pd.concat([df_2025, df_2026], ignore_index=True)
        
        for col in ['coin_in', 'win', 'jackpot']:
            if col in df_s.columns:
                df_s[col] = pd.to_numeric(df_s[col].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0)
            
        return df_s, df_u
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None, None

df_slots, df_users = load_all_data()

# --- 3. COMPONENTES DINÁMICOS ---
def render_auditor_cuadros(df):
    """Genera los 4 cuadros del Auditor Interno basados en los filtros actuales"""
    if df.empty:
        st.warning("No hay datos para el análisis del auditor.")
        return
    
    st.write("### 🧠 Análisis del Auditor Interno")
    c1, c2, c3, c4 = st.columns(4)
    
    # 1. Top Asset
    top_row = df.groupby('asset_Id')['win'].sum().reset_index().sort_values('win', ascending=False).iloc[0]
    with c1:
        st.markdown(f"""<div class='metric-card'>
            <div class='metric-label'>MÁXIMO RENDIMIENTO</div>
            <div class='metric-value'>Asset {top_row['asset_Id']}</div>
            <div class='metric-sub'>Generó {form_num(top_row['win'])} en el periodo.</div>
        </div>""", unsafe_allow_html=True)

    # 2. Eficiencia de Hold
    total_win = df['win'].sum()
    total_ci = df['coin_in'].sum()
    hold_p = (total_win / total_ci * 100) if total_ci > 0 else 0
    with c2:
        st.markdown(f"""<div class='metric-card'>
            <div class='metric-label'>EFICIENCIA DE HOLD</div>
            <div class='metric-value'>{hold_p:.2f}%</div>
            <div class='metric-sub'>Promedio ponderado de la selección.</div>
        </div>""", unsafe_allow_html=True)

    # 3. Anomalías
    negativos = df.groupby('asset_Id')['win'].sum()
    negativos = negativos[negativos < 0]
    with c3:
        color = "#FF4B4B" if len(negativos) > 0 else "#00D1FF"
        st.markdown(f"""<div class='metric-card' style='border-bottom-color: {color}'>
            <div class='metric-label'>ANOMALÍAS / WIN NEGATIVO</div>
            <div class='metric-value'>{len(negativos)} Activos</div>
            <div class='metric-sub'>Máquinas con pérdida neta detectada.</div>
        </div>""", unsafe_allow_html=True)

    # 4. Volumen
    with c4:
        st.markdown(f"""<div class='metric-card'>
            <div class='metric-label'>VOLUMEN PROYECTADO</div>
            <div class='metric-value'>{form_num(total_ci)}</div>
            <div class='metric-sub'>Total Coin In procesado con filtros.</div>
        </div>""", unsafe_allow_html=True)

# --- 4. INTERFAZ ---
if df_users is not None:
    credentials = {"usernames": {u.lower(): {"name": r['nombre'], "password": str(r['password']), "role": r['rol']} 
                   for u, r in df_users.set_index('usuario').iterrows()}}
    authenticator = stauth.Authenticate(credentials, "vdu_app", "auth_key", 30)
    authenticator.login(location='main')

    if st.session_state.get("authentication_status"):
        with st.sidebar:
            st.title("🎰 Casino VDU")
            nav = st.radio("Navegación", ["📊 Dashboard", "🔄 Analista Comparativo", "👤 Gestión"])
            authenticator.logout('Cerrar Sesión')

        if nav == "📊 Dashboard":
            # 1. TÍTULO
            st.title("Dashboard Fuente Mayor VDU")

            # 2. FILTROS
            with st.container(border=True):
                r1, r2 = st.columns([1, 3])
                f_rango = r1.date_input("📅 Ventana Temporal", [df_slots['fecha'].min(), df_slots['fecha'].max()])
                
                c1, c2, c3, c4 = st.columns(4)
                f_id = c1.multiselect("🆔 Asset ID", sorted(df_slots['asset_Id'].unique()))
                f_marca = c2.multiselect("🎰 Marca", sorted(df_slots['marca'].unique()))
                f_modelo = c3.multiselect("📦 Modelo", sorted(df_slots['modelo'].unique()))
                f_juego = c4.multiselect("🎮 Juego", sorted(df_slots['juego'].unique()))
            
            # Aplicar filtros
            df_f = df_slots.copy()
            if len(f_rango) == 2:
                df_f = df_f[(df_f['fecha'] >= f_rango[0]) & (df_f['fecha'] <= f_rango[1])]
            if f_id: df_f = df_f[df_f['asset_Id'].isin(f_id)]
            if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
            if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]
            if f_juego: df_f = df_f[df_f['juego'].isin(f_juego)]

            # 3. BOTONES DE CAMBIO DE VISTA
            tab_main, tab_excep, tab_marca = st.tabs(["📈 Dashboard Principal", "⚠️ Excepciones", "🏷️ Comparativa Marca"])

            with tab_main:
                # 4. CUADROS AUDITOR INTERNO (Dinamizados)
                render_auditor_cuadros(df_f)

                # 5. GRÁFICO (Línea/Área en lugar de barras)
                st.write("### 📈 Evolución Temporal")
                df_daily = df_f.groupby('fecha')[['win', 'coin_in']].sum().reset_index()
                fig = px.line(df_daily, x='fecha', y=['win', 'coin_in'], 
                             template="plotly_dark", 
                             color_discrete_map={"win": "#00D1FF", "coin_in": "#FF4B4B"})
                fig.update_traces(fill='tozeroy') # Convierte en gráfico de área para mayor visibilidad
                st.plotly_chart(fig, use_container_width=True)

                # KPIs Rápidos debajo
                k1, k2, k3 = st.columns(3)
                with k1: st.markdown(f"<div class='main-kpi-label'>NET WIN</div><div class='main-kpi-val'>{form_num(df_f['win'].sum())}</div>", unsafe_allow_html=True)
                with k2: st.markdown(f"<div class='main-kpi-label'>COIN IN</div><div class='main-kpi-val'>{form_num(df_f['coin_in'].sum())}</div>", unsafe_allow_html=True)
                with k3:
                    h = (df_f['win'].sum()/df_f['coin_in'].sum()*100) if df_f['coin_in'].sum()>0 else 0
                    st.markdown(f"<div class='main-kpi-label'>HOLD REAL</div><div class='main-kpi-val'>{h:.2f}%</div>", unsafe_allow_html=True)

            with tab_excep:
                st.write("### ⚠️ Activos sin Juego")
                all_ids = set(df_slots['asset_Id'].unique()) if not f_id else set(f_id)
                active_ids = set(df_f[df_f['coin_in'] > 0]['asset_Id'].unique())
                inactive = sorted(list(all_ids - active_ids))
                if inactive:
                    st.warning(f"Se encontraron {len(inactive)} máquinas sin movimiento en este periodo.")
                    st.write(inactive)
                else:
                    st.success("Todos los activos seleccionados tuvieron juego.")

            with tab_marca:
                st.write("### 🏷️ Rendimiento por Marca")
                df_m = df_f.groupby('marca')['win'].sum().reset_index()
                st.plotly_chart(px.bar(df_m, x='marca', y='win', color='win', template="plotly_dark"), use_container_width=True)

        elif nav == "🔄 Analista Comparativo":
            st.title("⚖️ Diagnóstico Comparativo")
            
            with st.container(border=True):
                col1, col2 = st.columns(2)
                with col1:
                    r_a = st.date_input("Periodo A (Actual)", [datetime.now().date() - timedelta(days=7), datetime.now().date()])
                with col2:
                    r_b = st.date_input("Periodo B (Anterior)", [datetime.now().date() - timedelta(days=14), datetime.now().date() - timedelta(days=8)])
                
                # Filtros restaurados en comparación
                f_comp_marca = st.multiselect("Filtrar por Marca", sorted(df_slots['marca'].unique()), key="f_comp")

            if len(r_a) == 2 and len(r_b) == 2:
                df_a = df_slots[(df_slots['fecha'] >= r_a[0]) & (df_slots['fecha'] <= r_a[1])]
                df_b = df_slots[(df_slots['fecha'] >= r_b[0]) & (df_slots['fecha'] <= r_b[1])]
                
                if f_comp_marca:
                    df_a = df_a[df_a['marca'].isin(f_comp_marca)]
                    df_b = df_b[df_b['marca'].isin(f_comp_marca)]

                w_a, w_b = df_a['win'].sum(), df_b['win'].sum()
                diff = w_a - w_b
                pct = (diff / w_b * 100) if w_b != 0 else 0

                st.divider()
                st.columns(3)[0].metric("Variación Win", form_num(diff), f"{pct:.2f}%")
                
                # Análisis dinámico comparativo
                st.write("### 🕵️ Informe del Analista")
                if diff > 0:
                    st.success(f"El rendimiento ha subido un {pct:.1f}% comparando ambos periodos.")
                else:
                    st.error(f"Se detecta una caída del {abs(pct):.1f}% en el rendimiento neto.")

        elif nav == "👤 Gestión":
            st.title("Gestión de Usuarios")
            st.table(df_users[['nombre', 'usuario', 'rol']])

    elif st.session_state.get("authentication_status") is False:
        st.error('Credenciales incorrectas')