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
        
        # 1. Cargar Usuarios
        sheet_u = client.open_by_key(ID_CONFIGURACION).worksheet("Usuarios")
        df_u = pd.DataFrame(sheet_u.get_all_records())
        df_u.columns = [str(c).strip() for c in df_u.columns]
        
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
        df_s = pd.concat([df_2025, df_2026], ignore_index=True)

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
            
        return df_s, df_u, df_p
    except Exception as e:
        st.error(f"Error crítico de conexión: {e}")
        return None, None, None

df_slots, df_users, df_personas = load_all_data()

# --- 3. INTERFAZ PRINCIPAL ---
if df_users is not None:
    credentials = {"usernames": {str(u).lower(): {"name": r['nombre'], "password": str(r['password']), "role": r['rol']} 
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
                ht = (wt/ct*100) if ct > 0 else 0
                
                # Filtrar personas para el mismo periodo
                mask_p = (df_personas['fecha'] >= f_rango[0]) & (df_personas['fecha'] <= f_rango[1]) if len(f_rango)==2 else True
                df_p_f = df_personas[mask_p]
                total_p = df_p_f['cantidad'].sum()
                win_persona = (wt / total_p) if total_p > 0 else 0

                k1, k2, k3, k4 = st.columns(4)
                k1.markdown(f"<div class='main-kpi-label'>NET WIN TOTAL</div><div class='main-kpi-val'>{form_num(wt)}</div>", unsafe_allow_html=True)
                k2.markdown(f"<div class='main-kpi-label'>COIN IN</div><div class='main-kpi-val'>{form_num(ct)}</div>", unsafe_allow_html=True)
                k3.markdown(f"<div class='main-kpi-label'>INGRESOS</div><div class='main-kpi-val'>{total_p:,.0f}</div>", unsafe_allow_html=True)
                k4.markdown(f"<div class='main-kpi-label'>WIN/PERSONA</div><div class='main-kpi-val'>{form_num(win_persona)}</div>", unsafe_allow_html=True)

                # --- ANALISTA INTERNO (DASHBOARD) ---
                st.divider()
                st.subheader("🤖 Analista Interno: Hallazgos de Sala")
                a1, a2, a3, a4 = st.columns(4)
                
                with a1:
                    top_marca = df_f.groupby('marca')['win'].sum().idxmax()
                    val_marca = df_f.groupby('marca')['win'].sum().max()
                    st.markdown(f"""<div class='report-box'><div class='report-title'>Líder de Rentabilidad</div><div class='report-text'>La marca <b>{top_marca}</b> domina la sala con un win de {form_num(val_marca)}, representando el {((val_marca/wt*100) if wt>0 else 0):.1f}% del total.</div></div>""", unsafe_allow_html=True)
                
                with a2:
                    # Cálculo de Hold por máquina
                    hold_m = df_f.groupby('asset_Id').apply(lambda x: (x['win'].sum()/x['coin_in'].sum()*100) if x['coin_in'].sum()>0 else 0)
                    outliers = len(hold_m[hold_m > 15])
                    st.markdown(f"""<div class='report-box'><div class='report-title'>Alertas de Hold</div><div class='report-text'>Se detectaron <b>{outliers} activos</b> con Hold superior al 15%. Se recomienda revisar configuración de pagos para no ahuyentar al cliente.</div></div>""", unsafe_allow_html=True)
                
                with a3:
                    jack_sum = df_f['jackpot'].sum()
                    st.markdown(f"""<div class='report-box'><div class='report-title'>Impacto Jackpots</div><div class='report-text'>Se han pagado <b>{form_num(jack_sum)}</b> en premios acumulados. Este valor es clave para la percepción de premio en sala.</div></div>""", unsafe_allow_html=True)
                
                with a4:
                    n_activos = len(df_f['asset_Id'].unique())
                    eficiencia = (wt / n_activos) if n_activos > 0 else 0
                    st.markdown(f"""<div class='report-box'><div class='report-title'>Promedio Win/Asset</div><div class='report-text'>Cada posición genera en promedio <b>{form_num(eficiencia)}</b>. Activos con win menor al 50% del promedio deben evaluarse para cambio.</div></div>""", unsafe_allow_html=True)

                # --- EXCEPCIONES Y REPORTES ---
                st.divider()
                with st.expander("🛠️ Herramientas de Análisis Avanzado (Excepciones y Jackpots)"):
                    tabs = st.tabs(["🚫 Máquinas sin Juego", "💎 Jackpots > 1M", "📈 Comparativa por Marcas"])
                    
                    with tabs[0]:
                        actividad = df_f.groupby(['asset_Id', 'marca', 'modelo', 'juego'])['coin_in'].sum().reset_index()
                        sin_juego = actividad[actividad['coin_in'] == 0]
                        if not sin_juego.empty:
                            st.warning(f"Se encontraron {len(sin_juego)} máquinas sin actividad.")
                            st.dataframe(sin_juego, use_container_width=True)
                        else:
                            st.success("Todas las máquinas registraron actividad.")

                    with tabs[1]:
                        j_altos = df_f[df_f['jackpot'] >= 1000000][['fecha', 'asset_Id', 'marca', 'juego', 'jackpot']]
                        if not j_altos.empty:
                            st.info("Premios Jackpots superiores a 1 Millón.")
                            st.dataframe(j_altos.sort_values('jackpot', ascending=False), use_container_width=True)
                        else:
                            st.write("No hay registros superiores a 1M.")

                    with tabs[2]:
                        df_m = df_f.groupby('marca').agg({'win': 'sum', 'coin_in': 'sum', 'asset_Id': 'nunique'}).reset_index()
                        df_m['Hold %'] = (df_m['win'] / df_m['coin_in'] * 100).round(2)
                        st.dataframe(df_m.sort_values('win', ascending=False), use_container_width=True)

                # Gráfico de Correlación Ingresos vs Win
                st.divider()
                c_izq, c_der = st.columns(2)
                with c_izq:
                    df_p_daily = df_p_f.groupby('fecha')['cantidad'].sum().reset_index()
                    st.plotly_chart(px.line(df_p_daily, x='fecha', y='cantidad', title="Flujo Diario de Personas", template="plotly_dark", color_discrete_sequence=['#00FFCC']), use_container_width=True)
                with c_der:
                    df_w_daily = df_f.groupby('fecha')['win'].sum().reset_index()
                    df_merged = pd.merge(df_p_daily, df_w_daily, on='fecha')
                    st.plotly_chart(px.scatter(df_merged, x='cantidad', y='win', trendline="ols", title="Relación Ingresos vs Win", template="plotly_dark"), use_container_width=True)

        elif nav == "🔄 Analista Comparativo":
            st.title("⚖️ Diagnóstico Comparativo de Periodos")
            if not df_slots.empty:
                with st.container(border=True):
                    col1, col2 = st.columns(2)
                    max_f = df_slots['fecha'].max()
                    r_act = col1.date_input("Periodo Actual (A)", [max_f - timedelta(days=7), max_f])
                    r_ant = col2.date_input("Periodo Anterior (B)", [max_f - timedelta(days=15), max_f - timedelta(days=8)])
                
                if len(r_act) == 2 and len(r_ant) == 2:
                    df_a = df_slots[(df_slots['fecha'] >= r_act[0]) & (df_slots['fecha'] <= r_act[1])]
                    df_b = df_slots[(df_slots['fecha'] >= r_ant[0]) & (df_slots['fecha'] <= r_ant[1])]
                    
                    wa, wb = df_a['win'].sum(), df_b['win'].sum()
                    ca, cb = df_a['coin_in'].sum(), df_b['coin_in'].sum()
                    
                    m1, m2 = st.columns(2)
                    m1.metric("Variación WIN", form_num(wa - wb), f"{((wa-wb)/wb*100 if wb>0 else 0):.1f}%")
                    m2.metric("Variación COIN IN", form_num(ca - cb), f"{((ca-cb)/cb*100 if cb>0 else 0):.1f}%")

                    st.divider()
                    st.subheader("🔍 Hallazgos Críticos")
                    h1, h2 = st.columns(2)
                    with h1:
                        # Marcas con mayor caída de volumen
                        ma_vol = df_a.groupby('marca')['coin_in'].sum()
                        mb_vol = df_b.groupby('marca')['coin_in'].sum()
                        diff_vol = ((ma_vol - mb_vol) / mb_vol * 100).sort_values()
                        if not diff_vol.empty and diff_vol.iloc[0] < -5:
                            st.markdown(f"""<div class='report-box' style='border-left-color: #FF4B4B'><div class='report-title'>Alerta de Volumen</div><div class='report-text'>La marca <span class='highlight-red'>{diff_vol.index[0]}</span> cayó un <span class='highlight-red'>{diff_vol.iloc[0]:.1f}%</span> en volumen de juego. Evaluar si hubo fallas técnicas o falta de interés.</div></div>""", unsafe_allow_html=True)
                        else:
                            st.markdown(f"""<div class='report-box'><div class='report-title'>Estabilidad de Marcas</div><div class='report-text'>El volumen de las marcas principales se mantiene estable sin caídas significativas detectadas.</div></div>""", unsafe_allow_html=True)
                    
                    with h2:
                        ha, hb = (wa/ca*100) if ca>0 else 0, (wb/cb*100) if cb>0 else 0
                        if ha > hb:
                            st.markdown(f"""<div class='report-box' style='border-left-color: #00FFCC'><div class='report-title'>Mejora de Retención</div><div class='report-text'>El Hold Real subió de {hb:.1f}% a <span class='highlight-green'>{ha:.1f}%</span>. Mayor rentabilidad por cada peso apostado en el periodo actual.</div></div>""", unsafe_allow_html=True)
                        else:
                            st.markdown(f"""<div class='report-box'><div class='report-title'>Análisis de Pago</div><div class='report-text'>El Hold bajó un {(hb-ha):.1f}%. Las máquinas están pagando más premios, lo cual puede atraer más volumen a largo plazo.</div></div>""", unsafe_allow_html=True)

        elif nav == "👤 Gestión Usuarios":
            st.title("👤 Administración")
            st.dataframe(df_users[['nombre', 'usuario', 'rol']], use_container_width=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Usuario o Contraseña incorrectos')