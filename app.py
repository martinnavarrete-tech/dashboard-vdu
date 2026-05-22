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
        min-height: 180px;
    }
    .metric-label { color: #A0A0A0; font-size: 0.75rem; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px; }
    .metric-value { color: white; font-size: 1.7rem; font-weight: bold; margin: 8px 0; }
    .metric-sub { font-size: 0.85rem; font-weight: 500; line-height: 1.3; }
    .report-box { 
        background-color: #161625; 
        padding: 15px; 
        border-radius: 8px; 
        border-left: 5px solid #00D1FF; 
        margin-bottom: 15px;
        min-height: 130px;
    }
    .report-title { color: #00D1FF; font-weight: bold; margin-bottom: 8px; text-transform: uppercase; font-size: 0.85rem; }
    .report-text { color: #E0E0E0; font-size: 0.8rem; line-height: 1.4; }
    .main-kpi-val { font-size: 2.2rem; font-weight: 800; color: #FFFFFF; line-height: 1.1; }
    .main-kpi-label { font-size: 0.8rem; color: #A0A0A0; text-transform: uppercase; font-weight: bold; }
    .highlight-red { color: #FF4B4B; font-weight: bold; }
    .highlight-green { color: #00FFCC; font-weight: bold; }
    
    /* Contenedores para emular estructura rígida Sielcon */
    .sielcon-block {
        background-color: #11111b;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #2b2b3c;
        margin-bottom: 15px;
    }
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
        
        # 2. Función para extraer específicamente la hoja "Cubo" de Slots
        def get_cubo_data(book_id):
            try:
                sheet = client.open_by_key(book_id).worksheet("Cubo")
                data = sheet.get_all_values()
                if not data:
                    return pd.DataFrame()
                
                df = pd.DataFrame(data[1:], columns=data[0])
                df.columns = [str(c).strip() for c in df.columns]
                
                mapeo = {'asset_id': 'asset_Id', 'Asset ID': 'asset_Id', 'Asset id': 'asset_Id'}
                df = df.rename(columns=mapeo)
                
                df = df.loc[:, ~df.columns.str.contains('^$|Unnamed', case=False, na=False)]
                df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=True, errors='coerce').dt.date
                return df.dropna(subset=['fecha'])
            except Exception as e:
                st.warning(f"Aviso: No se encontró la hoja 'Cubo' en el libro {book_id}. Error: {e}")
                return pd.DataFrame()

        df_2025 = get_cubo_data(ID_DATOS_2025)
        df_2026 = get_cubo_data(ID_DATOS_2026)
        df_s = pd.concat([df_2025, df_2026], ignore_index=True)
        
        # 3. Cargar la hoja "Cubo" de Ingreso de Personas
        try:
            sheet_p = client.open_by_key(ID_INGRESO_PERSONAS).worksheet("Cubo")
            data_p = sheet_p.get_all_values()
            if data_p and len(data_p) >= 2:
                df_p = pd.DataFrame(data_p[1:], columns=data_p[0])
                df_p.columns = [str(c).strip() for c in df_p.columns]
                df_p = df_p.rename(columns={'FECHA': 'fecha', 'Fecha': 'fecha', 'CANTIDAD': 'cantidad', 'Cantidad': 'cantidad'})
                df_p = df_p.loc[:, ~df_p.columns.str.contains('^$|Unnamed', case=False, na=False)]
                df_p['fecha'] = pd.to_datetime(df_p['fecha'], dayfirst=True, errors='coerce').dt.date
                df_p['cantidad'] = pd.to_numeric(df_p['cantidad'], errors='coerce').fillna(0)
                df_p = df_p.dropna(subset=['fecha'])
            else:
                df_p = pd.DataFrame(columns=['fecha', 'cantidad'])
        except:
            df_p = pd.DataFrame(columns=['fecha', 'cantidad'])
        
        if df_s.empty:
            return pd.DataFrame(), df_u, df_p

        for col in ['coin_in', 'win', 'jackpot']:
            if col in df_s.columns:
                def clean_currency(x):
                    if not x or str(x).strip() == "": return 0.0
                    cleaned = re.sub(r'[^\d.,-]', '', str(x))
                    if ',' in cleaned and '.' in cleaned:
                        cleaned = cleaned.replace('.', '').replace(',', '.')
                    elif ',' in cleaned:
                        cleaned = cleaned.replace(',', '.')
                    try: return float(cleaned)
                    except: return 0.0
                df_s[col] = df_s[col].apply(clean_currency)
            
        return df_s, df_u, df_p
    except Exception as e:
        st.error(f"Error crítico de sincronización: {e}")
        return None, None, None

df_slots, df_users, df_personas = load_all_data()

# --- 3. INTERFAZ PRINCIPAL ---
if df_users is not None:
    try:
        credentials = {"usernames": {str(u).lower(): {"name": r['nombre'], "password": str(r['password']), "role": r['rol']} 
                       for u, r in df_users.set_index('usuario').iterrows()}}
    except KeyError as e:
        st.error(f"Error: No se encuentra la columna {e} en la hoja de Usuarios.")
        st.stop()

    authenticator = stauth.Authenticate(credentials, "vdu_app", "auth_key", 30)
    authenticator.login(location='main')

    if st.session_state.get("authentication_status"):
        curr_user = st.session_state.get('username', '').lower()
        user_role = credentials["usernames"].get(curr_user, {}).get("role", "Usuario")

        with st.sidebar:
            st.title("🛡️ Casino Fuente Mayor")
            st.write(f"Operador: **{st.session_state['name']}**")
            st.divider()
            nav = st.radio("Navegación", ["📊 Dashboard de Sala", "🔄 Analista Comparativo", "👤 Gestión Usuarios"])
            st.write("")
            authenticator.logout('Cerrar Sesión', 'sidebar')

        if nav == "📊 Dashboard de Sala":
            st.title("Dashboard Fuente Mayor VDU")
            
            if df_slots is not None and not df_slots.empty:
                
                # =========================================================================
                # FILA SUPERIOR: Filtros compactos integrados a la izquierda y KPIs a la derecha
                # =========================================================================
                with st.container():
                    col_filtros, col_kpis = st.columns([1.2, 2.8])
                    
                    with col_filtros:
                        st.markdown("<div class='sielcon-block'>", unsafe_allow_html=True)
                        safe_min = df_slots['fecha'].min()
                        safe_max = df_slots['fecha'].max()
                        f_rango = st.date_input("📅 Ventana Temporal", [safe_min, safe_max], label_visibility="collapsed")
                        
                        sub_c1, sub_c2 = st.columns(2)
                        f_id = sub_c1.multiselect("🆔 Asset ID", sorted(df_slots['asset_Id'].unique()), placeholder="Assets")
                        f_marca = sub_c2.multiselect("🎰 Marca", sorted(df_slots['marca'].unique()), placeholder="Marcas")
                        
                        sub_c3, sub_c4 = st.columns(2)
                        f_modelo = sub_c3.multiselect("📦 Modelo", sorted(df_slots['modelo'].unique()), placeholder="Modelos")
                        f_juego = sub_c4.multiselect("🎮 Juego", sorted(df_slots['juego'].unique()), placeholder="Juegos")
                        st.markdown("</div>", unsafe_allow_html=True)
                    
                    # Filtros para el set de Slots
                    df_f = df_slots.copy()
                    if isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
                        df_f = df_f[(df_f['fecha'] >= f_rango[0]) & (df_f['fecha'] <= f_rango[1])]
                    
                    if f_id: df_f = df_f[df_f['asset_Id'].isin(f_id)]
                    if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
                    if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]
                    if f_juego: df_f = df_f[df_f['juego'].isin(f_juego)]

                    # Filtros para el set de Personas (Sincronizado)
                    df_p_f = df_personas.copy() if df_personas is not None else pd.DataFrame()
                    if not df_p_f.empty and isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
                        df_p_f = df_p_f[(df_p_f['fecha'] >= f_rango[0]) & (df_p_f['fecha'] <= f_rango[1])]

                    wt = df_f['win'].sum()
                    ct = df_f['coin_in'].sum()
                    ht = (wt/ct*100) if ct > 0 else 0
                    asistencia = df_p_f['cantidad'].sum() if not df_p_f.empty else 0
                    win_persona = (wt / asistencia) if asistencia > 0 else 0

                    with col_kpis:
                        st.markdown("<div class='sielcon-block' style='min-height: 185px;'>", unsafe_allow_html=True)
                        k1, k2, k3, k4 = st.columns(4)
                        with k1: st.markdown(f"<div class='main-kpi-label'>NET WIN TOTAL</div><div class='main-kpi-val'>{form_num(wt)}</div>", unsafe_allow_html=True)
                        with k2: st.markdown(f"<div class='main-kpi-label'>COIN IN</div><div class='main-kpi-val'>{form_num(ct)}</div>", unsafe_allow_html=True)
                        with k3: st.markdown(f"<div class='main-kpi-label'>HOLD REAL %</div><div class='main-kpi-val'>{ht:.2f}%</div>", unsafe_allow_html=True)
                        with k4: st.markdown(f"<div class='main-kpi-label'>INGRESOS / WIN</div><div class='main-kpi-val' style='color:#FF9F43;'>{asistencia:,.0f}</div><div style='color:#A0A0A0; font-size:0.75rem; font-weight:bold; margin-top:2px;'>EFF: {form_num(win_persona)} x PAX</div>", unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)

                st.write("")

                # =========================================================================
                # CUADRÍCULA CENTRAL: Matriz expuesta de monitoreo en 3 columnas rígidas
                # =========================================================================
                m_col1, m_col2, m_col3 = st.columns([1.6, 1.2, 1.2])

                with m_col1:
                    st.markdown("### 🚫 Máquinas sin Juego")
                    sin_juego = df_f.groupby('asset_Id')['coin_in'].sum()
                    sin_juego = sin_juego[sin_juego == 0].index.tolist()
                    if sin_juego:
                        st.dataframe(df_f[df_f['asset_Id'].isin(sin_juego)][['asset_Id', 'marca', 'modelo', 'juego']].drop_duplicates(), use_container_width=True, height=250)
                    else:
                        st.success("Todas las máquinas registraron actividad.")

                with m_col2:
                    st.markdown("### 💎 Jackpots > 1M")
                    altos_premios = df_f[df_f['jackpot'] >= 1000000][['fecha', 'asset_Id', 'jackpot']]
                    if not altos_premios.empty:
                        st.dataframe(altos_premios.sort_values('jackpot', ascending=False), use_container_width=True, height=250)
                    else:
                        st.info("Sin Jackpots > 1M.")

                with m_col3:
                    st.markdown("### 📈 Resumen por Marcas")
                    df_comp = df_f.groupby('marca').agg({'win': 'sum', 'coin_in': 'sum', 'asset_Id': 'nunique'}).reset_index()
                    df_comp['Hold %'] = (df_comp['win'] / df_comp['coin_in'] * 100).round(1)
                    df_comp = df_comp.rename(columns={'asset_Id': 'Q'})
                    st.dataframe(df_comp[['marca', 'Q', 'Hold %']].sort_values('Hold %', ascending=False), use_container_width=True, height=250)

                st.write("")
                st.divider()

                # =========================================================================
                # FILA DE HALLAZGOS: Analista de Sala
                # =========================================================================
                st.subheader("🤖 Analista Interno: Hallazgos de Sala")
                a1, a2, a3, a4 = st.columns(4)
                
                with a1:
                    top_marca = df_f.groupby('marca')['win'].sum().idxmax() if not df_f.empty else "N/A"
                    val_marca = df_f.groupby('marca')['win'].sum().max() if not df_f.empty else 0
                    st.markdown(f"""<div class='report-box'><div class='report-title'>Líder de Rentabilidad</div><div class='report-text'>La marca <b>{top_marca}</b> domina la sala con un win de {form_num(val_marca)}, representando el {((val_marca/wt*100) if wt>0 else 0):.1f}% del total.</div></div>""", unsafe_allow_html=True)
                
                with a2:
                    avg_hold = df_f.groupby('asset_Id').apply(lambda x: (x['win'].sum()/x['coin_in'].sum()*100) if x['coin_in'].sum()>0 else 0)
                    outliers = len(avg_hold[avg_hold > 15])
                    st.markdown(f"""<div class='report-box'><div class='report-title'>Alertas de Hold</div><div class='report-text'>Se detectaron <b>{outliers} activos</b> con Hold superior al 15%. Se recomienda revisar configuración de pagos para mantener competitividad.</div></div>""", unsafe_allow_html=True)
                
                with a3:
                    jack_sum = df_f['jackpot'].sum()
                    st.markdown(f"""<div class='report-box'><div class='report-title'>Impacto Jackpots</div><div class='report-text'>Se han pagado <b>{form_num(jack_sum)}</b> en premios acumulados. Esto afecta directamente al Net Win pero fideliza al cliente.</div></div>""", unsafe_allow_html=True)
                
                with a4:
                    eficiencia = (wt / len(df_f['asset_Id'].unique())) if len(df_f['asset_Id'].unique()) > 0 else 0
                    st.markdown(f"""<div class='report-box'><div class='report-title'>Promedio Win/Asset</div><div class='report-text'>Cada posición genera en promedio <b>{form_num(eficiencia)}</b>. Activos por debajo del 50% de este valor deben ser evaluados.</div></div>""", unsafe_allow_html=True)

                st.divider()

                # =========================================================================
                # FILA INFERIOR: Gráfico Financiero de Slots en paralelo al gráfico de Ingreso de Personas
                # =========================================================================
                g_col1, g_col2 = st.columns([2.2, 1.8])

                with g_col1:
                    st.markdown("### 📈 Rendimiento Diario de Sala (Slots)")
                    df_time = df_f.groupby('fecha')[['win', 'coin_in']].sum().reset_index()
                    fig_slots = px.area(df_time, x='fecha', y=['win', 'coin_in'], template="plotly_dark", color_discrete_sequence=['#00D1FF', '#FF4B4B'])
                    fig_slots.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig_slots, use_container_width=True)

                with g_col2:
                    st.markdown("### 👥 Curva de Asistencia Diaria (Ingresos)")
                    if not df_p_f.empty:
                        df_p_daily = df_p_f.groupby('fecha')['cantidad'].sum().reset_index()
                        fig_pers = px.bar(df_p_daily, x='fecha', y='cantidad', template="plotly_dark", color_discrete_sequence=['#FF9F43'])
                        fig_pers.update_layout(margin=dict(l=10, r=10, t=10, b=10))
                        st.plotly_chart(fig_pers, use_container_width=True)
                    else:
                        st.info("Sin registros de asistencia para estas fechas.")
            else:
                st.error("Error: Sin datos en 'Cubo'.")

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
                    
                    # KPIs Comparativos
                    wa, wb = df_a['win'].sum(), df_b['win'].sum()
                    ca, cb = df_a['coin_in'].sum(), df_b['coin_in'].sum()
                    
                    diff_w = wa - wb
                    pct_w = (diff_w / wb * 100) if wb != 0 else 0
                    
                    m1, m2 = st.columns(2)
                    m1.metric("Variación WIN (A vs B)", form_num(diff_w), f"{pct_w:.2f}%", delta_color="normal")
                    m2.metric("Variación COIN IN (A vs B)", form_num(ca - cb), f"{((ca-cb)/cb*100 if cb!=0 else 0):.2f}%")

                    # --- HALLAZGOS DEL ANALISTA (COMPARATIVA) ---
                    st.divider()
                    st.subheader("🔍 Hallazgos Críticos del Comparador")
                    h1, h2 = st.columns(2)
                    
                    with h1:
                        ma_marca = df_a.groupby('marca')['coin_in'].sum()
                        mb_marca = df_b.groupby('marca')['coin_in'].sum()
                        caida = (ma_marca - mb_marca) / mb_marca * 100
                        peor_marca = caida.idxmin() if not caida.empty else "N/A"
                        val_caida = caida.min() if not caida.empty else 0
                        
                        if val_caida < -5:
                            st.markdown(f"""<div class='report-box' style='border-left-color: #FF4B4B'><div class='report-title'>Alerta de Volumen</div><div class='report-text'>La marca <span class='highlight-red'>{peor_marca}</span> ha sufrido una caída del <span class='highlight-red'>{val_caida:.1f}%</span> en su Coin In respecto al periodo anterior. Requiere revisión de tráfico en su isla.</div></div>""", unsafe_allow_html=True)
                        else:
                            st.markdown(f"""<div class='report-box'><div class='report-title'>Estabilidad de Marcas</div><div class='report-text'>No se detectan caídas críticas de volumen por marca. La operación se mantiene estable en términos de preferencia de cliente.</div></div>""", unsafe_allow_html=True)

                    with h2:
                        ha = (wa/ca*100) if ca>0 else 0
                        hb = (wb/cb*100) if cb>0 else 0
                        if ha > hb:
                            st.markdown(f"""<div class='report-box' style='border-left-color: #00FFCC'><div class='report-title'>Eficiencia de Retención</div><div class='report-text'>El Hold Real subió de {hb:.1f}% a <span class='highlight-green'>{ha:.1f}%</span>. Esto indica una mayor rentabilidad por cada peso apostado en el periodo actual.</div></div>""", unsafe_allow_html=True)
                        else:
                            st.markdown(f"""<div class='report-box'><div class='report-title'>Comportamiento de Pago</div><div class='report-text'>El Hold ha bajado un {(hb-ha):.1f}%, indicando que las máquinas han devuelto más premios en el periodo A.</div></div>""", unsafe_allow_html=True)

                    st.divider()
                    st.subheader("Desglose por Asset")
                    df_diff = pd.merge(
                        df_a.groupby('asset_Id')['win'].sum().reset_index(),
                        df_b.groupby('asset_Id')['win'].sum().reset_index(),
                        on='asset_Id', suffixes=('_A', '_B'), how='outer'
                    ).fillna(0)
                    df_diff['Var. $'] = df_diff['win_A'] - df_diff['win_B']
                    st.dataframe(df_diff.sort_values('Var. $', ascending=False), use_container_width=True)

        elif nav == "👤 Gestión Usuarios":
            st.title("👤 Administración")
            st.dataframe(df_users[['nombre', 'usuario', 'rol']], use_container_width=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Usuario o Contraseña incorrectos')