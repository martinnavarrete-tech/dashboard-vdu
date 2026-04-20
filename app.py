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
    .analysis-box { background-color: #161625; padding: 20px; border-radius: 10px; border-left: 5px solid #FF4B4B; margin: 10px 0; }
    .positive { color: #00FFCC; font-weight: bold; }
    .negative { color: #FF4B4B; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

def form_num(valor):
    try:
        # Formato de moneda: Punto para miles, coma para decimales (Estilo Argentina/ES)
        return f"$ {valor:,.0f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except:
        return "$ 0"

# IDs de los Libros de Google Sheets
ID_CONFIGURACION = "1W_68ToMyy_nu1oPH7ePFj74_vc1op5bGiFoP4AtaY0I"
ID_DATOS_2026 = "1ZYn6foApzeEeKg_qKzW9faQFjBPXHoc8ffB_CeZ3f_s"
ID_DATOS_2025 = "1aAl_PX1wpBWgTu9bLc81Wn57jSyt8Kqfwm4B4Fsa1W0"

# --- 2. MOTOR DE DATOS ---

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
        # Si la coma está en la posición de decimal (2 o 1 dígitos al final)
        partes = s.split(',')
        if len(partes[-1]) <= 2:
            s = s.replace(',', '.')
        else:
            # Es un separador de miles (ej: 1,250)
            s = s.replace(',', '')
    
    # 3. Limpiar cualquier carácter que no sea dígito, signo negativo o el primer punto decimal
    # Esto evita que "1.200.50" rompa el float
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
        
        sheet_u = client.open_by_key(ID_CONFIGURACION).worksheet("Usuarios")
        df_u = pd.DataFrame(sheet_u.get_all_records())
        
        def get_cubo_data(book_id):
            try:
                sheet = client.open_by_key(book_id).worksheet("Cubo")
                data = sheet.get_all_values()
                if not data or len(data) < 2: return pd.DataFrame()
                df = pd.DataFrame(data[1:], columns=data[0])
                df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=True, errors='coerce').dt.date
                return df.dropna(subset=['fecha'])
            except: return pd.DataFrame()

        df_2025 = get_cubo_data(ID_DATOS_2025)
        df_2026 = get_cubo_data(ID_DATOS_2026)
        df_s = pd.concat([df_2025, df_2026], ignore_index=True)
        
        # Limpieza robusta de columnas numéricas
        for col in ['coin_in', 'win', 'jackpot']:
            if col in df_s.columns:
                df_s[col] = df_s[col].apply(clean_numeric_vdu)
            
        return df_s, df_u
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None, None

df_slots, df_users = load_all_data()

# --- 3. COMPONENTES DE ANÁLISIS ---

def render_auditor_cuadros(df):
    if df.empty: return
    st.write("### 🧠 Análisis del Auditor Interno")
    c1, c2, c3, c4 = st.columns(4)
    
    df_assets = df.groupby('asset_Id')['win'].sum().reset_index()
    if not df_assets.empty:
        top_row = df_assets.sort_values('win', ascending=False).iloc[0]
        with c1:
            st.markdown(f"""<div class='metric-card'><div class='metric-label'>MÁXIMO RENDIMIENTO</div>
                <div class='metric-value'>Asset {top_row['asset_Id']}</div>
                <div class='metric-sub'>Generó {form_num(top_row['win'])} en este periodo.</div></div>""", unsafe_allow_html=True)
    
    t_win, t_ci = df['win'].sum(), df['coin_in'].sum()
    h_p = (t_win / t_ci * 100) if t_ci > 0 else 0
    with c2:
        st.markdown(f"""<div class='metric-card'><div class='metric-label'>EFICIENCIA DE HOLD</div>
            <div class='metric-value'>{h_p:.2f}%</div>
            <div class='metric-sub'>Promedio sobre {form_num(t_ci)} de entrada.</div></div>""", unsafe_allow_html=True)
    
    neg = df.groupby('asset_Id')['win'].sum()
    neg = neg[neg < 0]
    with c3:
        color = "#FF4B4B" if len(neg) > 0 else "#00D1FF"
        st.markdown(f"""<div class='metric-card' style='border-bottom-color: {color}'>
            <div class='metric-label'>ANOMALÍAS (WIN < 0)</div>
            <div class='metric-value'>{len(neg)} Activos</div>
            <div class='metric-sub'>Máquinas que dieron pérdida neta.</div></div>""", unsafe_allow_html=True)
            
    with c4:
        st.markdown(f"""<div class='metric-card'><div class='metric-label'>VOLUMEN TOTAL</div>
            <div class='metric-value'>{form_num(t_ci)}</div>
            <div class='metric-sub'>Coin In acumulado registrado.</div></div>""", unsafe_allow_html=True)

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
            st.write("---")
            authenticator.logout('Cerrar Sesión')

        if nav == "📊 Dashboard":
            st.title("Dashboard Fuente Mayor VDU")
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

            tab_main, tab_excep, tab_marca = st.tabs(["📉 Dashboard Principal", "⚠️ Excepciones", "🏷️ Comparativa Marca"])
            with tab_main:
                render_auditor_cuadros(df_f)
                st.write("### 📈 Evolución Temporal")
                df_daily = df_f.groupby('fecha')[['win', 'coin_in']].sum().reset_index()
                if not df_daily.empty:
                    fig = px.area(df_daily, x='fecha', y=['win', 'coin_in'], template="plotly_dark", 
                                 color_discrete_map={"win": "#00D1FF", "coin_in": "#FF4B4B"})
                    st.plotly_chart(fig, use_container_width=True)
                
                k1, k2, k3 = st.columns(3)
                k1.metric("Win Total", form_num(df_f['win'].sum()))
                k2.metric("Coin In Total", form_num(df_f['coin_in'].sum()))
                h_real = (df_f['win'].sum()/df_f['coin_in'].sum()*100) if df_f['coin_in'].sum()>0 else 0
                k3.metric("Hold Real", f"{h_real:.2f}%")

            with tab_excep:
                st.write("### ⚠️ Activos sin Juego")
                all_ids = set(df_slots['asset_Id'].unique()) if not f_id else set(f_id)
                active_ids = set(df_f[df_f['coin_in'] > 0]['asset_Id'].unique())
                inactive = sorted(list(all_ids - active_ids))
                if inactive:
                    st.warning(f"Se detectaron {len(inactive)} máquinas sin movimiento.")
                    st.write(inactive)
                else: st.success("Actividad detectada en todos los activos.")

            with tab_marca:
                st.write("### 🏷️ Desempeño por Marca")
                df_m = df_f.groupby('marca')['win'].sum().reset_index()
                if not df_m.empty:
                    st.plotly_chart(px.bar(df_m, x='marca', y='win', color='win', template="plotly_dark"), use_container_width=True)

        elif nav == "🔄 Analista Comparativo":
            st.title("⚖️ Diagnóstico Comparativo")
            with st.container(border=True):
                col1, col2 = st.columns(2)
                # Seleccionar rangos con seguridad de que no estén vacíos
                min_f, max_f = df_slots['fecha'].min(), df_slots['fecha'].max()
                r_a = col1.date_input("Periodo A (Actual)", [max_f - timedelta(days=7), max_f])
                r_b = col2.date_input("Periodo B (Anterior)", [max_f - timedelta(days=15), max_f - timedelta(days=8)])
                f_comp_marca = st.multiselect("Filtrar por Marca", sorted(df_slots['marca'].unique()))

            if len(r_a) == 2 and len(r_b) == 2:
                df_a = df_slots[(df_slots['fecha'] >= r_a[0]) & (df_slots['fecha'] <= r_a[1])]
                df_b = df_slots[(df_slots['fecha'] >= r_b[0]) & (df_slots['fecha'] <= r_b[1])]
                
                if f_comp_marca:
                    df_a = df_a[df_a['marca'].isin(f_comp_marca)]
                    df_b = df_b[df_b['marca'].isin(f_comp_marca)]
                
                wa, wb = df_a['win'].sum(), df_b['win'].sum()
                ca, cb = df_a['coin_in'].sum(), df_b['coin_in'].sum()
                diff_w, diff_c = wa - wb, ca - cb
                pct_w = (diff_w / wb * 100) if wb != 0 else 0
                pct_c = (diff_c / cb * 100) if cb != 0 else 0

                st.divider()
                st.subheader("📊 Resultados")
                k1, k2 = st.columns(2)
                k1.metric("Variación Win", form_num(diff_w), f"{pct_w:.2f}%")
                k2.metric("Variación Coin In", form_num(diff_c), f"{pct_c:.2f}%")

                # GRÁFICOS CON CONTROL DE VACÍO
                st.write("### 📊 Comparativa Visual por Marca")
                m_a_plot = df_a.groupby('marca')['win'].sum().reset_index(); m_a_plot['Periodo'] = 'A (Actual)'
                m_b_plot = df_b.groupby('marca')['win'].sum().reset_index(); m_b_plot['Periodo'] = 'B (Anterior)'
                df_plot = pd.concat([m_a_plot, m_b_plot])
                
                if not df_plot.empty and df_plot['win'].sum() != 0:
                    st.plotly_chart(px.bar(df_plot, x='marca', y='win', color='Periodo', barmode='group', template="plotly_dark"), use_container_width=True)
                else:
                    st.info("No hay datos suficientes para generar el gráfico comparativo.")

                st.subheader("🕵️ Informe de Inteligencia")
                m_a = df_a.groupby('marca')[['win', 'coin_in']].sum()
                m_b = df_b.groupby('marca')[['win', 'coin_in']].sum()
                m_comp = m_a.join(m_b, lsuffix='_A', rsuffix='_B', how='outer').fillna(0)
                
                if not m_comp.empty and (m_comp['win_A'].sum() > 0 or m_comp['win_B'].sum() > 0):
                    m_comp['diff_win'] = m_comp['win_A'] - m_comp['win_B']
                    df_ws = m_comp.sort_values('diff_win', ascending=False)
                    
                    if len(df_ws) >= 1:
                        st.markdown(f"""<div class='analysis-box'><b>Rendimiento:</b><br>
                            • Crecimiento: <b>{df_ws.index[0]}</b> ({form_num(df_ws['diff_win'].values[0])})<br>
                            • Caída: <b>{df_ws.index[-1]}</b> ({form_num(df_ws['diff_win'].values[-1])})</div>""", unsafe_allow_html=True)
                else:
                    st.warning("Sin datos de marcas para el análisis detallado.")

                st.write("### 📜 Diagnóstico Final")
                if pct_w > 0 and pct_c > 0: st.success("Salud Positiva: El Win sube respaldado por volumen.")
                elif pct_w > 0 and pct_c < 0: st.info("Alerta de Hold: Win sube con menos juego (retención alta).")
                elif pct_w < 0 and pct_c > 0: st.warning("Alerta de Pagos: Más juego pero menos Win (Jackpots pagados).")
                else: st.error("Tendencia negativa general.")
            else: st.info("Seleccione fechas válidas para ambos periodos.")

        elif nav == "👤 Gestión":
            st.title("Gestión de Usuarios")
            st.table(df_users[['nombre', 'usuario', 'rol']])

    elif st.session_state.get("authentication_status") is False:
        st.error('Credenciales incorrectas')