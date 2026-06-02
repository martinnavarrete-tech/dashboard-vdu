import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit_authenticator as stauth
import plotly.express as px
import re
from datetime import datetime, timedelta

# --- 1. CONFIGURACIÓN Y ESTILOS AVANZADOS (ESTILO SIELCON) ---
st.set_page_config(page_title="Dashboard VDU", layout="wide", page_icon="🎰")

st.markdown("""
    <style>
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 1rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
    .filter-bar {
        background-color: #0d0e12;
        border: 1px solid #1e222d;
        border-radius: 4px;
        padding: 12px;
        margin-bottom: 15px;
    }
    .sielcon-panel {
        background-color: #0d0e12;
        border: 1px solid #1e222d;
        border-radius: 4px;
        padding: 12px;
        margin-bottom: 15px;
    }
    .panel-header {
        font-size: 0.85rem;
        font-weight: 700;
        color: #ffffff;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 10px;
        border-bottom: 1px solid #1e222d;
        padding-bottom: 6px;
    }
    .kpi-wrapper {
        background-color: #0d0e12;
        border: 1px solid #1e222d;
        border-radius: 4px;
        padding: 15px;
        text-align: center;
        height: 100%;
    }
    .kpi-title {
        color: #848e9c;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 5px;
    }
    .kpi-value {
        color: #ffffff;
        font-size: 1.9rem;
        font-weight: 800;
        line-height: 1.1;
    }
    .kpi-subtext {
        color: #ff9f43;
        font-size: 0.75rem;
        font-weight: bold;
        margin-top: 5px;
    }
    .analyst-box {
        background-color: #121622;
        border-left: 4px solid #00d1ff;
        border-radius: 2px;
        padding: 10px;
        min-height: 95px;
    }
    .analyst-title {
        color: #00d1ff;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        margin-bottom: 4px;
    }
    .analyst-text {
        color: #d1d4dc;
        font-size: 0.78rem;
        line-height: 1.3;
    }
    </style>
""", unsafe_allow_html=True)

def form_num(valor):
    """Formatea números al estilo contable: $ 1.250.000"""
    try:
        return f"$ {valor:,.0f}".replace(',', '.')
    except:
        return "$ 0"

def clean_numeric_string(val):
    """Limpia textos sin formato, remueve puntos de miles regionales y convierte a float"""
    if not val or str(val).strip() == "": 
        return 0.0
    cleaned = re.sub(r'[^\d.,-]', '', str(val).strip())
    if ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        cleaned = cleaned.replace(',', '.')
    try:
        return float(cleaned)
    except:
        return 0.0

# IDs de los Libros de Google Sheets
ID_CONFIGURACION = "1W_68ToMyy_nu1oPH7ePFj74_vc1op5bGiFoP4KtaY0I"
ID_DATOS_2026 = "1ZYn6foApzeEeKg_qKzW9faQFjBPXHoc8ffB_CeZ3f_s"
ID_DATOS_2025 = "1aAl_PX1wpBWgTu9bLc81Wn57jSyt8Kqfwm4B4Fsa1W0"
ID_INGRESO_PERSONAS = "1H-j4-gudnexcxnbk0oFMHBJNovDOyWOIWZCLaprEdYw"
ID_INGRESO_BILLETES = "17c6P1pY21SC_xFoLulC7FgvUBz8zj8xz-61gsC-vsaI"

# --- 2. MOTOR DE DATOS CACHEADO ---
@st.cache_data(ttl=60)
def load_all_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        
        # 1. Usuarios
        sheet_u = client.open_by_key(ID_CONFIGURACION).worksheet("Usuarios")
        df_u = pd.DataFrame(sheet_u.get_all_records())
        df_u.columns = [str(c).strip() for c in df_u.columns]
        
        # 2. Hojas Slots (Pestaña Cubo)
        def get_cubo_data(book_id):
            try:
                sheet = client.open_by_key(book_id).worksheet("Cubo")
                data = sheet.get_all_values()
                if not data: return pd.DataFrame()
                df = pd.DataFrame(data[1:], columns=data[0])
                df.columns = [str(c).strip().lower() for c in df.columns]
                
                # Mapeo inteligente para la columna identificadora de máquina
                if 'cuim' in df.columns:
                    df = df.rename(columns={'cuim': 'asset_id'})
                
                df = df.loc[:, ~df.columns.str.contains('^$|Unnamed', case=False, na=False)]
                df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=True, errors='coerce').dt.date
                return df.dropna(subset=['fecha'])
            except:
                return pd.DataFrame()

        df_2025 = get_cubo_data(ID_DATOS_2025)
        df_2026 = get_cubo_data(ID_DATOS_2026)
        df_s = pd.concat([df_2025, df_2026], ignore_index=True)
        
        for col in ['coin_in', 'win', 'jackpot']:
            if col in df_s.columns:
                df_s[col] = df_s[col].apply(clean_numeric_string)

        # 3. Asistencia / Ocupación
        try:
            sheet_p = client.open_by_key(ID_INGRESO_PERSONAS).get_worksheet(0)
            data_p = sheet_p.get_all_values()
            if data_p and len(data_p) >= 2:
                df_p = pd.DataFrame(data_p[1:], columns=data_p[0])
                df_p.columns = [str(c).strip().lower() for c in df_p.columns]
                
                col_ocupacion = None
                for c in df_p.columns:
                    if 'ocupacion' in c or 'ocupaci' in c:
                        col_ocupacion = c
                        break
                
                if 'fecha' in df_p.columns and col_ocupacion:
                    df_p = df_p[['fecha', col_ocupacion]]
                    df_p = df_p.rename(columns={col_ocupacion: 'cantidad'})
                    df_p['fecha'] = pd.to_datetime(df_p['fecha'], errors='coerce').dt.date
                    df_p['cantidad'] = df_p['cantidad'].apply(clean_numeric_string)
                    df_p = df_p.dropna(subset=['fecha'])
                else:
                    df_p = pd.DataFrame(columns=['fecha', 'cantidad'])
            else:
                df_p = pd.DataFrame(columns=['fecha', 'cantidad'])
        except:
            df_p = pd.DataFrame(columns=['fecha', 'cantidad'])

        # 4. Cubo de Ingreso de Billetes 2026 (CORREGIDO CON NORMALIZACIÓN DE CUIM)
        try:
            sheet_b = client.open_by_key(ID_INGRESO_BILLETES).worksheet("Cubo")
            data_b = sheet_b.get_all_values()
            if data_b and len(data_b) >= 2:
                df_b = pd.DataFrame(data_b[1:], columns=data_b[0])
                df_b.columns = [str(c).strip().lower() for c in df_b.columns]
                
                # Homologación crítica de CUIM -> asset_id
                if 'cuim' in df_b.columns:
                    df_b = df_b.rename(columns={'cuim': 'asset_id'})
                elif 'asset_id' not in df_b.columns:
                    # Si no encuentra ninguna, busca la primera columna que empiece por 'asset'
                    for c in df_b.columns:
                        if 'asset' in c:
                            df_b = df_b.rename(columns={c: 'asset_id'})
                            break
                
                df_b['fecha'] = pd.to_datetime(df_b['fecha'], dayfirst=True, errors='coerce').dt.date
                df_b = df_b.dropna(subset=['fecha'])
                
                # Conversión matemática de todos los campos de texto a floats
                for col in df_b.columns:
                    if col not in ['fecha', 'asset_id', 'marca', 'modelo', 'juego']:
                        df_b[col] = df_b[col].apply(clean_numeric_string)
            else:
                df_b = pd.DataFrame()
        except Exception as e:
            df_b = pd.DataFrame()
            
        return df_s, df_u, df_p, df_b
    except Exception as e:
        st.error(f"Error crítico de sincronización: {e}")
        return None, None, None, None

df_slots, df_users, df_personas, df_billetes = load_all_data()

# --- 3. LOGUEO Y ENRUTAMIENTO ---
if df_users is not None and not df_users.empty:
    credentials = {
        "usernames": {
            str(row['usuario']).strip().lower(): {
                "name": row['nombre'], 
                "password": str(row['password']).strip(), 
                "role": row['rol']
            } 
            for _, row in df_users.iterrows()
        }
    }

    authenticator = stauth.Authenticate(
        credentials=credentials,
        cookie_name="vdu_app_cookie",
        key="vdu_signature_key",
        cookie_expiry_days=30
    )

    authenticator.login(location='main')

    if st.session_state.get("authentication_status") == True:
        with st.sidebar:
            st.title("🎰 Fuente Mayor")
            st.write(f"Operador: **{st.session_state.get('name')}**")
            st.divider()
            nav = st.radio("Menú de Análisis", ["📊 Dashboard de Sala", "💵 Control de Billetes", "🔄 Analista Comparativo", "👤 Gestión Usuarios"])
            st.write("")
            authenticator.logout('Cerrar Sesión', 'sidebar')

        safe_min = df_slots['fecha'].min() if df_slots is not None and not df_slots.empty else datetime.now().date()
        safe_max = df_slots['fecha'].max() if df_slots is not None and not df_slots.empty else datetime.now().date()

        # =========================================================================
        # VISTA: DASHBOARD DE SALA
        # =========================================================================
        if nav == "📊 Dashboard de Sala":
            st.subheader("Dashboard Fuente Mayor VDU")
            
            if df_slots is not None and not df_slots.empty:
                st.markdown("<div class='filter-bar'>", unsafe_allow_html=True)
                f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns([1.2, 1, 1, 1, 1])
                
                with f_col1:
                    f_rango = st.date_input("Ventana Temporal", [safe_min, safe_max], label_visibility="collapsed")
                with f_col2:
                    f_id = st.multiselect("CUIM / N° Máquina", sorted(df_slots['asset_id'].unique()), placeholder="🆔 CUIM / N° Máquina", label_visibility="collapsed")
                with f_col3:
                    f_marca = st.multiselect("Marca", sorted(df_slots['marca'].unique()), placeholder="🎰 Marca", label_visibility="collapsed")
                with f_col4:
                    f_modelo = st.multiselect("Modelo", sorted(df_slots['modelo'].unique()), placeholder="📦 Modelo", label_visibility="collapsed")
                with f_col5:
                    f_juego = st.multiselect("Juego", sorted(df_slots['juego'].unique()), placeholder="🎮 Juego", label_visibility="collapsed")
                st.markdown("</div>", unsafe_allow_html=True)
                
                df_f = df_slots.copy()
                if isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
                    df_f = df_f[(df_f['fecha'] >= f_rango[0]) & (df_f['fecha'] <= f_rango[1])]
                if f_id: df_f = df_f[df_f['asset_id'].isin(f_id)]
                if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
                if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]
                if f_juego: df_f = df_f[df_f['juego'].isin(f_juego)]

                df_p_f = df_personas.copy() if df_personas is not None else pd.DataFrame()
                if not df_p_f.empty and isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
                    df_p_f = df_p_f[(df_p_f['fecha'] >= f_rango[0]) & (df_p_f['fecha'] <= f_rango[1])]

                wt = df_f['win'].sum()
                ct = df_f['coin_in'].sum()
                ht = (wt / ct * 100) if ct > 0 else 0
                asistencia = df_p_f['cantidad'].sum() if not df_p_f.empty else 0
                win_persona = (wt / asistencia) if asistencia > 0 else 0

                k_col1, k_col2, k_col3, k_col4 = st.columns(4)
                with k_col1:
                    st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Net Win Total</div><div class='kpi-value'>{form_num(wt)}</div></div>", unsafe_allow_html=True)
                with k_col2:
                    st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Coin In</div><div class='kpi-value'>{form_num(ct)}</div></div>", unsafe_allow_html=True)
                with k_col3:
                    st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Hold Real %</div><div class='kpi-value' style='color:#00ffcc;'>{ht:.2f}%</div></div>", unsafe_allow_html=True)
                with k_col4:
                    st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Ocupación / Tráfico</div><div class='kpi-value' style='color:#ff9f43;'>{asistencia:,.0f}</div><div class='kpi-subtext'>EFF: {form_num(win_persona)} x PAX</div></div>", unsafe_allow_html=True)

                st.write("")

                m_col1, m_col2, m_col3 = st.columns([1.4, 1.3, 1.3])
                with m_col1:
                    st.markdown("<div class='sielcon-panel'>", unsafe_allow_html=True)
                    st.markdown("<div class='panel-header'>🚫 Máquinas sin Actividad (CUIM)</div>", unsafe_allow_html=True)
                    sin_juego = df_f.groupby('asset_id')['coin_in'].sum()
                    sin_juego = sin_juego[sin_juego == 0].index.tolist()
                    if sin_juego:
                        df_sj = df_f[df_f['asset_id'].isin(sin_juego)][['asset_id', 'marca', 'modelo', 'juego']].drop_duplicates()
                        df_sj = df_sj.rename(columns={'asset_id': 'CUIM / N° Maq'})
                        st.dataframe(df_sj, use_container_width=True, height=180, hide_index=True)
                    else:
                        st.success("Operación óptima: 0 máquinas inactivas.")
                    st.markdown("</div>", unsafe_allow_html=True)

                with m_col2:
                    st.markdown("<div class='sielcon-panel'>", unsafe_allow_html=True)
                    st.markdown("<div class='panel-header'>💎 Jackpots Mayores > 1M</div>", unsafe_allow_html=True)
                    altos_premios = df_f[df_f['jackpot'] >= 1000000][['fecha', 'asset_id', 'jackpot']]
                    if not altos_premios.empty:
                        altos_premios = altos_premios.rename(columns={'asset_id': 'CUIM'})
                        st.dataframe(altos_premios.sort_values('jackpot', ascending=False), use_container_width=True, height=180, hide_index=True)
                    else:
                        st.info("Sin registros de premios especiales.")
                    st.markdown("</div>", unsafe_allow_html=True)

                with m_col3:
                    st.markdown("<div class='sielcon-panel'>", unsafe_allow_html=True)
                    st.markdown("<div class='panel-header'>📊 Rendimiento por Fabricante</div>", unsafe_allow_html=True)
                    df_comp = df_f.groupby('marca').agg({'win': 'sum', 'coin_in': 'sum', 'asset_id': 'nunique'}).reset_index()
                    df_comp['Hold %'] = (df_comp['win'] / df_comp['coin_in'] * 100).round(2)
                    df_comp = df_comp.rename(columns={'asset_id': 'Q'}).sort_values('win', ascending=False)
                    st.dataframe(df_comp[['marca', 'Q', 'Hold %']], use_container_width=True, height=180, hide_index=True)
                    st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("<div class='sielcon-panel' style='padding-bottom:5px;'>", unsafe_allow_html=True)
                st.markdown("<div class='panel-header'>🤖 Monitoreo Algorítmico de Sala</div>", unsafe_allow_html=True)
                a1, a2, a3, a4 = st.columns(4)
                with a1:
                    top_m = df_f.groupby('marca')['win'].sum().idxmax() if not df_f.empty else "N/A"
                    val_m = df_f.groupby('marca')['win'].sum().max() if not df_f.empty else 0
                    st.markdown(f"<div class='analyst-box'><div class='analyst-title'>Líder del Mercado</div><div class='analyst-text'><b>{top_m}</b> encabeza el profit de sala con una recaudación neta de {form_num(val_m)}.</div></div>", unsafe_allow_html=True)
                with a2:
                    avg_hold = df_f.groupby('asset_id').apply(lambda x: (x['win'].sum()/x['coin_in'].sum()*100) if x['coin_in'].sum()>0 else 0)
                    outliers = len(avg_hold[avg_hold > 15])
                    st.markdown(f"<div class='analyst-box' style='border-left-color:#ef5350;'><div class='analyst-title'>Alerta de Desvíos</div><div class='analyst-text'>Detectados <b>{outliers} CUIMs</b> con Hold Real superior al 15%. Riesgo potencial de rechazo de clientes.</div></div>", unsafe_allow_html=True)
                with a3:
                    jack_sum = df_f['jackpot'].sum()
                    st.markdown(f"<div class='analyst-box' style='border-left-color:#ff9f43;'><div class='analyst-title'>Volumen de Premios</div><div class='analyst-text'>Un total de <b>{form_num(jack_sum)}</b> fue entregado en Jackpots acumulados durante el ciclo seleccionado.</div></div>", unsafe_allow_html=True)
                with a4:
                    eficiencia = (wt / len(df_f['asset_id'].unique())) if len(df_f['asset_id'].unique()) > 0 else 0
                    st.markdown(f"<div class='analyst-box'><div class='analyst-title'>Eficiencia Media</div><div class='analyst-text'>La media de rendimiento por terminal instalada se posiciona en <b>{form_num(eficiencia)}</b>.</div></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

                g_col1, g_col2 = st.columns([2, 2])
                with g_col1:
                    st.markdown("<div class='sielcon-panel'>", unsafe_allow_html=True)
                    st.markdown("<div class='panel-header'>📈 Evolución Temporal Financiera (Slots)</div>", unsafe_allow_html=True)
                    df_time = df_f.groupby('fecha')[['win', 'coin_in']].sum().reset_index()
                    df_time_melt = df_time.melt(id_vars='fecha', value_vars=['win', 'coin_in'], var_name='Métrica', value_name='Monto')
                    df_time_melt['Métrica'] = df_time_melt['Métrica'].replace({'win': 'Net Win', 'coin_in': 'Coin In'})
                    
                    fig_slots = px.area(df_time_melt, x='fecha', y='Monto', color='Métrica', template="plotly_dark",
                                        color_discrete_map={'Net Win': '#00D1FF', 'Coin In': '#FF4B4B'})
                    fig_slots.update_layout(margin=dict(l=10, r=10, t=5, b=5), height=220, xaxis_title=None, yaxis_title=None,
                                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig_slots, use_container_width=True)
                    st.markdown("</div>", unsafe_allow_html=True)

                with g_col2:
                    st.markdown("<div class='sielcon-panel'>", unsafe_allow_html=True)
                    st.markdown("<div class='panel-header'>👥 Comportamiento de Asistencia (Ocupación)</div>", unsafe_allow_html=True)
                    if not df_p_f.empty:
                        df_p_daily = df_p_f.groupby('fecha')['cantidad'].sum().reset_index()
                        fig_pers = px.bar(df_p_daily, x='fecha', y='cantidad', template="plotly_dark", color_discrete_sequence=['#FF9F43'])
                        fig_pers.update_layout(margin=dict(l=10, r=10, t=5, b=5), height=220, xaxis_title=None, yaxis_title=None)
                        st.plotly_chart(fig_pers, use_container_width=True)
                    else:
                        st.info("Sin datos de ocupación en este rango.")
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.error("Error al mapear la base de datos 'Cubo'.")

        # =========================================================================
        # VISTA: CONTROL DE BILLETES (REPARADA CONTRA EL NOMBRE 'CUIM')
        # =========================================================================
        elif nav == "💵 Control de Billetes":
            st.subheader("Reporte Avanzado de Drop Físico por CUIM / N° Máquina")
            
            if df_billetes is not None and not df_billetes.empty:
                st.markdown("<div class='filter-bar'>", unsafe_allow_html=True)
                fb_col1, fb_col2 = st.columns([1.5, 3.5])
                with fb_col1:
                    fb_rango = st.date_input("Filtrar Rango Billetes", [df_billetes['fecha'].min(), df_billetes['fecha'].max()], label_visibility="collapsed")
                with fb_col2:
                    fb_id = st.multiselect("Filtrar por CUIM (N° Máquina)", sorted(df_billetes['asset_id'].unique()), placeholder="🆔 Seleccionar CUIM...", label_visibility="collapsed")
                st.markdown("</div>", unsafe_allow_html=True)
                
                df_b_f = df_billetes.copy()
                if isinstance(fb_rango, (list, tuple)) and len(fb_rango) == 2:
                    df_b_f = df_b_f[(df_b_f['fecha'] >= fb_rango[0]) & (df_b_f['fecha'] <= fb_rango[1])]
                if fb_id:
                    df_b_f = df_b_f[df_b_f['asset_id'].isin(fb_id)]
                
                col_denominaciones = [c for c in df_b_f.columns if c.lower() not in ['fecha', 'asset_id', 'total', 'marca', 'modelo', 'juego']]
                total_pesos_drop = df_b_f['total'].sum() if 'total' in df_b_f.columns else 0.0
                total_piezas_físicas = df_b_f[col_denominaciones].sum().sum() if col_denominaciones else 0

                bk1, bk2 = st.columns(2)
                with bk1:
                    st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Total Recaudado en Pesos ($)</div><div class='kpi-value' style='color:#00ffcc;'>{form_num(total_pesos_drop)}</div></div>", unsafe_allow_html=True)
                with bk2:
                    st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Volumen Total de Billetes Físicos</div><div class='kpi-value'>{total_piezas_físicas:,.0f} u.</div></div>", unsafe_allow_html=True)
                
                st.write("")
                bg_col1, bg_col2 = st.columns([2, 2])
                
                with bg_col1:
                    st.markdown("<div class='sielcon-panel'>", unsafe_allow_html=True)
                    st.markdown("<div class='panel-header'>💵 Recaudación Total en Pesos ($) por CUIM / N° Máquina</div>", unsafe_allow_html=True)
                    if 'total' in df_b_f.columns:
                        df_maquina_cash = df_b_f.groupby('asset_id')['total'].sum().reset_index().sort_values('total', ascending=False)
                        df_maquina_cash.columns = ['CUIM / N° Máquina', 'Total Recaudado ($)']
                        st.dataframe(df_maquina_cash.style.format({'Total Recaudado ($)': lambda x: form_num(x)}), use_container_width=True, height=250, hide_index=True)
                    else:
                        st.warning("No se localizó la columna 'total' en el libro origen.")
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                with bg_col2:
                    st.markdown("<div class='sielcon-panel'>", unsafe_allow_html=True)
                    st.markdown("<div class='panel-header'>📊 Desglose de Unidades por Denominación</div>", unsafe_allow_html=True)
                    if col_denominaciones:
                        df_denom = df_b_f[col_denominaciones].sum().reset_index()
                        df_denom.columns = ['Denominación', 'Cantidad de Billetes']
                        df_denom = df_denom.sort_values('Cantidad de Billetes', ascending=False)
                        
                        fig_denom = px.bar(df_denom, x='Denominación', y='Cantidad de Billetes', template="plotly_dark", color_discrete_sequence=['#00D1FF'])
                        fig_denom.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=230, xaxis_title=None, yaxis_title=None)
                        st.plotly_chart(fig_denom, use_container_width=True)
                    else:
                        st.info("Sin registros de denominaciones detalladas.")
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.error("No se pudo cargar la base 'Cubo' del libro de Billetes o está vacío.")

        # =========================================================================
        # VISTA: ANALISTA COMPARATIVO
        # =========================================================================
        elif nav == "🔄 Analista Comparativo":
            st.subheader("⚖️ Diagnóstico Comparativo de Periodos")
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
                    st.markdown("### Desglose Técnico por CUIM / Posición")
                    df_diff = pd.merge(
                        df_a.groupby('asset_id')['win'].sum().reset_index(),
                        df_b.groupby('asset_id')['win'].sum().reset_index(),
                        on='asset_id', suffixes=('_A', '_B'), how='outer'
                    ).fillna(0)
                    df_diff['Var. $'] = df_diff['win_A'] - df_diff['win_B']
                    df_diff = df_diff.rename(columns={'asset_id': 'CUIM'})
                    st.dataframe(df_diff.sort_values('Var. $', ascending=False), use_container_width=True, hide_index=True)

        # =========================================================================
        # VISTA: GESTIÓN DE USUARIOS
        # =========================================================================
        elif nav == "👤 Gestión Usuarios":
            st.subheader("👤 Auditoría de Accesos")
            st.dataframe(df_users[['nombre', 'usuario', 'rol']], use_container_width=True, hide_index=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Credenciales de acceso no válidas')