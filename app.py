import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit_authenticator as stauth
import plotly.express as px
import re
from datetime import datetime, timedelta

# --- 1. CONFIGURACIÓN Y ESTILOS AVANZADOS ---
st.set_page_config(page_title="Dashboard VDU", layout="wide", page_icon="🎰")

# Paleta de colores Sielcon integrada en la UI nativa
st.markdown("""
    <style>
    /* Estructuración de bloques modulares rígidos */
    .sielcon-card {
        background-color: #11111b;
        border: 1px solid #2b2b3c;
        border-radius: 6px;
        padding: 15px;
        margin-bottom: 10px;
    }
    
    /* Contenedor unificado para KPIs */
    .kpi-container {
        display: flex;
        justify-content: space-between;
        background-color: #11111b;
        border: 1px solid #2b2b3c;
        border-radius: 6px;
        padding: 20px;
        min-height: 140px;
    }
    .kpi-box {
        flex: 1;
        text-align: left;
        padding: 0 10px;
    }
    .kpi-box:not(:last-child) {
        border-right: 1px solid #2b2b3c;
    }
    .kpi-title {
        color: #8e9aa8;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }
    .kpi-value {
        color: #ffffff;
        font-size: 1.8rem;
        font-weight: 800;
        line-height: 1.1;
    }
    .kpi-subtext {
        color: #a0a0A0;
        font-size: 0.75rem;
        font-weight: bold;
        margin-top: 4px;
    }

    /* Tarjetas del Analista (Modulares) */
    .analyst-card {
        background-color: #161625;
        border-left: 4px solid #00D1FF;
        border-radius: 4px;
        padding: 12px;
        min-height: 120px;
    }
    .analyst-title {
        color: #00D1FF;
        font-size: 0.8rem;
        font-weight: 700;
        text-transform: uppercase;
        margin-bottom: 6px;
    }
    .analyst-text {
        color: #e0e0e0;
        font-size: 0.8rem;
        line-height: 1.3;
    }
    
    /* Headers de secciones de datos */
    .section-header {
        font-size: 1rem;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
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

# --- 2. MOTOR DE DATOS CACHEADO ---
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
        
        # 2. Cargar Hojas "Cubo" de Slots
        def get_cubo_data(book_id):
            try:
                sheet = client.open_by_key(book_id).worksheet("Cubo")
                data = sheet.get_all_values()
                if not data: return pd.DataFrame()
                df = pd.DataFrame(data[1:], columns=data[0])
                df.columns = [str(c).strip() for c in df.columns]
                df = df.rename(columns={'asset_id': 'asset_Id', 'Asset ID': 'asset_Id', 'Asset id': 'asset_Id'})
                df = df.loc[:, ~df.columns.str.contains('^$|Unnamed', case=False, na=False)]
                df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=True, errors='coerce').dt.date
                return df.dropna(subset=['fecha'])
            except:
                return pd.DataFrame()

        df_2025 = get_cubo_data(ID_DATOS_2025)
        df_2026 = get_cubo_data(ID_DATOS_2026)
        df_s = pd.concat([df_2025, df_2026], ignore_index=True)
        
        # 3. Cargar Hoja de Ingreso de Personas
        try:
            sheet_p = client.open_by_key(ID_INGRESO_PERSONAS).worksheet("Cubo")
            data_p = sheet_p.get_all_values()
            if data_p and len(data_p) >= 2:
                df_p = pd.DataFrame(data_p[1:], columns=data_p[0])
                df_p.columns = [str(c).strip() for c in df_p.columns]
                df_p = df_p.rename(columns={'FECHA': 'fecha', 'Fecha': 'fecha', 'CANTIDAD': 'cantidad', 'Cantidad': 'cantidad'})
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

# --- 3. INTERFAZ DE LOGUEO Y NAVEGACIÓN ---
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

        # =========================================================================
        # VISTA: DASHBOARD DE SALA
        # =========================================================================
        if nav == "📊 Dashboard de Sala":
            st.title("Dashboard Fuente Mayor VDU")
            
            if df_slots is not None and not df_slots.empty:
                
                # --- FILA SUPERIOR: FILTROS + BANNER DE KPIS UNIFICADOS ---
                col_filtros, col_kpis = st.columns([1.1, 2.9])
                
                with col_filtros:
                    st.markdown("<div class='sielcon-card' style='min-height: 140px;'>", unsafe_allow_html=True)
                    safe_min = df_slots['fecha'].min()
                    safe_max = df_slots['fecha'].max()
                    f_rango = st.date_input("Ventana Temporal", [safe_min, safe_max], label_visibility="collapsed")
                    
                    sub_c1, sub_c2 = st.columns(2)
                    f_id = sub_c1.multiselect("🆔 Asset ID", sorted(df_slots['asset_Id'].unique()), placeholder="Assets")
                    f_marca = sub_c2.multiselect("🎰 Marca", sorted(df_slots['marca'].unique()), placeholder="Marcas")
                    
                    sub_c3, sub_c4 = st.columns(2)
                    f_modelo = sub_c3.multiselect("📦 Modelo", sorted(df_slots['modelo'].unique()), placeholder="Modelos")
                    f_juego = sub_c4.multiselect("🎮 Juego", sorted(df_slots['juego'].unique()), placeholder="Juegos")
                    st.markdown("</div>", unsafe_allow_html=True)
                
                # Reglas de filtrado unificado (Slots y Asistencia)
                df_f = df_slots.copy()
                if isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
                    df_f = df_f[(df_f['fecha'] >= f_rango[0]) & (df_f['fecha'] <= f_rango[1])]
                if f_id: df_f = df_f[df_f['asset_Id'].isin(f_id)]
                if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
                if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]
                if f_juego: df_f = df_f[df_f['juego'].isin(f_juego)]

                df_p_f = df_personas.copy() if df_personas is not None else pd.DataFrame()
                if not df_p_f.empty and isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
                    df_p_f = df_p_f[(df_p_f['fecha'] >= f_rango[0]) & (df_p_f['fecha'] <= f_rango[1])]

                # Cálculos métricos base
                wt = df_f['win'].sum()
                ct = df_f['coin_in'].sum()
                ht = (wt / ct * 100) if ct > 0 else 0
                asistencia = df_p_f['cantidad'].sum() if not df_p_f.empty else 0
                win_persona = (wt / asistencia) if asistencia > 0 else 0

                with col_kpis:
                    st.markdown(f"""
                        <div class='kpi-container'>
                            <div class='kpi-box'>
                                <div class='kpi-title'>Net Win Total</div>
                                <div class='kpi-value'>{form_num(wt)}</div>
                            </div>
                            <div class='kpi-box'>
                                <div class='kpi-title'>Coin In</div>
                                <div class='kpi-value'>{form_num(ct)}</div>
                            </div>
                            <div class='kpi-box'>
                                <div class='kpi-title'>Hold Real %</div>
                                <div class='kpi-value'>{ht:.2f}%</div>
                            </div>
                            <div class='kpi-box'>
                                <div class='kpi-title'>Ingresos de Sala</div>
                                <div class='kpi-value' style='color:#FF9F43;'>{asistencia:,.0f}</div>
                                <div class='kpi-subtext'>EFF: {form_num(win_persona)} x PAX</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                st.divider()

                # --- CUADRÍCULA CENTRAL: MATRIZ DE EXCEPCIONES EXPUESTA EN PARALELO ---
                m_col1, m_col2, m_col3 = st.columns([1.5, 1.2, 1.3])

                with m_col1:
                    st.markdown("<div class='section-header'>🚫 Máquinas sin Juego</div>", unsafe_allow_html=True)
                    sin_juego = df_f.groupby('asset_Id')['coin_in'].sum()
                    sin_juego = sin_juego[sin_juego == 0].index.tolist()
                    if sin_juego:
                        df_sj = df_f[df_f['asset_Id'].isin(sin_juego)][['asset_Id', 'marca', 'modelo', 'juego']].drop_duplicates()
                        st.dataframe(df_sj, use_container_width=True, height=220, hide_index=True)
                    else:
                        st.success("100% de activos con actividad comercial.")

                with m_col2:
                    st.markdown("<div class='section-header'>💎 Jackpots > 1M</div>", unsafe_allow_html=True)
                    altos_premios = df_f[df_f['jackpot'] >= 1000000][['fecha', 'asset_Id', 'jackpot']]
                    if not altos_premios.empty:
                        st.dataframe(altos_premios.sort_values('jackpot', ascending=False), use_container_width=True, height=220, hide_index=True)
                    else:
                        st.info("Sin registros mayores a $ 1M.")

                with m_col3:
                    st.markdown("<div class='section-header'>📊 Resumen por Marcas</div>", unsafe_allow_html=True)
                    df_comp = df_f.groupby('marca').agg({'win': 'sum', 'coin_in': 'sum', 'asset_Id': 'nunique'}).reset_index()
                    df_comp['Hold %'] = (df_comp['win'] / df_comp['coin_in'] * 100).round(2)
                    df_comp = df_comp.rename(columns={'asset_Id': 'Q'}).sort_values('win', ascending=False)
                    st.dataframe(df_comp[['marca', 'Q', 'Hold %']], use_container_width=True, height=220, hide_index=True)

                st.divider()

                # --- FILA DE REPORTES AUTOMÁTICOS (ANALISTA DE SALA) ---
                st.markdown("<div class='section-header'>🤖 Analista de Sala: Insights Clave</div>", unsafe_allow_html=True)
                a1, a2, a3, a4 = st.columns(4)
                
                with a1:
                    top_m = df_f.groupby('marca')['win'].sum().idxmax() if not df_f.empty else "N/A"
                    val_m = df_f.groupby('marca')['win'].sum().max() if not df_f.empty else 0
                    st.markdown(f"<div class='analyst-card'><div class='analyst-title'>Dominio de Sala</div><div class='analyst-text'><b>{top_m}</b> es el motor principal del casino con un win neto de {form_num(val_m)}.</div></div>", unsafe_allow_html=True)
                
                with a2:
                    avg_hold = df_f.groupby('asset_Id').apply(lambda x: (x['win'].sum()/x['coin_in'].sum()*100) if x['coin_in'].sum()>0 else 0)
                    outliers = len(avg_hold[avg_hold > 15])
                    st.markdown(f"<div class='analyst-card' style='border-left-color:#FF4B4B;'><div class='analyst-title'>Alerta de Desvíos</div><div class='analyst-text'>Se detectaron <b>{outliers} máquinas</b> rindiendo con hold por encima del 15% (Riesgo de fuga).</div></div>", unsafe_allow_html=True)
                
                with a3:
                    jack_sum = df_f['jackpot'].sum()
                    st.markdown(f"<div class='analyst-card' style='border-left-color:#FF9F43;'><div class='analyst-title'>Premios Entregados</div><div class='analyst-text'>Un acumulado de <b>{form_num(jack_sum)}</b> devuelto en Jackpots impactó la retención global del ciclo.</div></div>", unsafe_allow_html=True)
                
                with a4:
                    eficiencia = (wt / len(df_f['asset_Id'].unique())) if len(df_f['asset_Id'].unique()) > 0 else 0
                    st.markdown(f"<div class='analyst-card'><div class='analyst-title'>Rendimiento Unitario</div><div class='analyst-text'>El promedio de producción por posición se ubica actualmente en <b>{form_num(eficiencia)}</b>.</div></div>", unsafe_allow_html=True)

                st.divider()

                # --- FILA INFERIOR: GRÁFICOS PARALELOS LIMPIOS Y NORMALIZADOS ---
                g_col1, g_col2 = st.columns([2.1, 1.9])

                with g_col1:
                    st.markdown("<div class='section-header'>📈 Evolución Financiera de Sala ($)</div>", unsafe_allow_html=True)
                    df_time = df_f.groupby('fecha')[['win', 'coin_in']].sum().reset_index()
                    # Mapeo limpio para evitar leyendas confusas en el eje
                    df_time_melt = df_time.melt(id_vars='fecha', value_vars=['win', 'coin_in'], var_name='Métrica', value_name='Monto')
                    df_time_melt['Métrica'] = df_time_melt['Métrica'].replace({'win': 'Net Win', 'coin_in': 'Coin In'})
                    
                    fig_slots = px.area(df_time_melt, x='fecha', y='Monto', color='Métrica', template="plotly_dark",
                                        color_discrete_map={'Net Win': '#00D1FF', 'Coin In': '#FF4B4B'})
                    fig_slots.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=280, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig_slots, use_container_width=True)

                with g_col2:
                    st.markdown("<div class='section-header'>👥 Curva de Tráfico e Ingresos (PAX)</div>", unsafe_allow_html=True)
                    if not df_p_f.empty:
                        df_p_daily = df_p_f.groupby('fecha')['cantidad'].sum().reset_index()
                        fig_pers = px.bar(df_p_daily, x='fecha', y='cantidad', template="plotly_dark", color_discrete_sequence=['#FF9F43'])
                        fig_pers.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=280, yaxis_title="Clientes")
                        st.plotly_chart(fig_pers, use_container_width=True)
                    else:
                        st.info("Sin registros de control de accesos para las fechas seleccionadas.")
            else:
                st.error("Error: Sin conexión con la hoja fuente 'Cubo'.")

        # =========================================================================
        # VISTA: ANALISTA COMPARATIVO
        # =========================================================================
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
                    diff_w = wa - wb
                    pct_w = (diff_w / wb * 100) if wb != 0 else 0
                    
                    m1, m2 = st.columns(2)
                    m1.metric("Variación WIN (A vs B)", form_num(diff_w), f"{pct_w:.2f}%")
                    m2.metric("Variación COIN IN (A vs B)", form_num(ca - cb), f"{((ca-cb)/cb*100 if cb!=0 else 0):.2f}%")

                    st.divider()
                    st.subheader("Desglose por Asset")
                    df_diff = pd.merge(
                        df_a.groupby('asset_Id')['win'].sum().reset_index(),
                        df_b.groupby('asset_Id')['win'].sum().reset_index(),
                        on='asset_Id', suffixes=('_A', '_B'), how='outer'
                    ).fillna(0)
                    df_diff['Var. $'] = df_diff['win_A'] - df_diff['win_B']
                    st.dataframe(df_diff.sort_values('Var. $', ascending=False), use_container_width=True, hide_index=True)

        # =========================================================================
        # VISTA: GESTIÓN DE USUARIOS
        # =========================================================================
        elif nav == "👤 Gestión Usuarios":
            st.title("👤 Administración de Cuentas")
            st.dataframe(df_users[['nombre', 'usuario', 'rol']], use_container_width=True, hide_index=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Usuario o Contraseña incorrectos')