import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit_authenticator as stauth
import plotly.express as px
import re
from datetime import timedelta

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
    .report-box { background-color: #161625; padding: 25px; border-radius: 10px; border-left: 4px solid #00D1FF; margin-top: 20px; }
    .main-kpi-val { font-size: 2.8rem; font-weight: 800; color: #FFFFFF; line-height: 1.1; }
    .main-kpi-label { font-size: 0.9rem; color: #A0A0A0; text-transform: uppercase; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

def form_num(valor):
    return f"$ {valor:,.0f}".replace(',', '.')

# --- 2. MOTOR DE DATOS CORREGIDO ---
@st.cache_data(ttl=60)
def load_all_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        
        sheet_u = client.open_by_key("1W_68ToMyy_nu1oPH7ePFj74_vc1op5bGiFoP4KtaY0I").worksheet("Usuarios")
        df_u = pd.DataFrame(sheet_u.get_all_records())
        
        sheet_s = client.open_by_key("1ZYn6foApzeEeKg_qKzW9faQFjBPXHoc8ffB_CeZ3f_s").worksheet("Cubo")
        data_s = sheet_s.get_all_values()
        df_s = pd.DataFrame(data_s[1:], columns=data_s[0])
        
        df_s = df_s.loc[:, df_s.columns.str.contains('^$|Unnamed') == False]
        df_s['fecha'] = pd.to_datetime(df_s['fecha'], dayfirst=True, errors='coerce').dt.date
        df_s = df_s.dropna(subset=['fecha'])
        
        # LIMPIEZA NUMÉRICA ESTRICTA PARA COINCIDIR CON GOOGLE SHEETS
        for col in ['coin_in', 'win', 'jackpot']:
            if col in df_s.columns:
                def clean_currency(x):
                    if not x or str(x).strip() == "": return 0.0
                    # Elimina todo excepto números, puntos, comas y el signo menos
                    cleaned = re.sub(r'[^\d.,-]', '', str(x))
                    if ',' in cleaned and '.' in cleaned: # Formato europeo/latam 1.234,56
                        cleaned = cleaned.replace('.', '').replace(',', '.')
                    elif ',' in cleaned: # Formato 1234,56
                        cleaned = cleaned.replace(',', '.')
                    try: return float(cleaned)
                    except: return 0.0
                df_s[col] = df_s[col].apply(clean_currency)
        
        return df_s, df_u
    except Exception as e:
        st.error(f"Error de sincronización: {e}")
        return None, None

df_slots, df_users = load_all_data()

# --- 3. AUTENTICACIÓN ---
if df_users is not None:
    credentials = {"usernames": {u.lower(): {"name": r['nombre'], "password": str(r['password']), "role": r['rol']} 
                   for u, r in df_users.set_index('usuario').iterrows()}}
    authenticator = stauth.Authenticate(credentials, "vdu_app", "auth_key", 30)
    authenticator.login(location='main')

    if st.session_state.get("authentication_status"):
        with st.sidebar:
            st.title("🛡️ Casino Fuente Mayor - VDU")
            st.write(f"Operador: **{st.session_state['name']}**")
            st.divider()
            nav = st.radio("Navegación", ["📊 Dashboard de Sala", "🔄 Analista Comparativo", "👤 Gestión Usuarios"])
            st.write("")
            authenticator.logout('Cerrar Sesión')

        # --- SECCIÓN 1: DASHBOARD DE SALA ---
        if nav == "📊 Dashboard de Sala":
            st.title("Dashboard Fuente Mayor VDU")
            
            # FILTROS SOLICITADOS (asset_Id, marca, modelo, juego)
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
            if len(f_rango) == 2: df_f = df_f[(df_f['fecha'] >= f_rango[0]) & (df_f['fecha'] <= f_rango[1])]
            if f_id: df_f = df_f[df_f['asset_Id'].isin(f_id)]
            if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
            if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]
            if f_juego: df_f = df_f[df_f['juego'].isin(f_juego)]

            # TOTALES CORREGIDOS
            wt, ct = df_f['win'].sum(), df_f['coin_in'].sum()
            ht = (wt/ct*100) if ct > 0 else 0
            
            st.write("")
            k1, k2, k3 = st.columns(3)
            with k1: st.markdown(f"<div class='main-kpi-label'>NET WIN TOTAL</div><div class='main-kpi-val'>{form_num(wt)}</div>", unsafe_allow_html=True)
            with k2: st.markdown(f"<div class='main-kpi-label'>COIN IN (TRÁFICO)</div><div class='main-kpi-val'>{form_num(ct)}</div>", unsafe_allow_html=True)
            with k3: st.markdown(f"<div class='main-kpi-label'>HOLD REAL %</div><div class='main-kpi-val'>{ht:.2f}%</div>", unsafe_allow_html=True)
            
            tab1, tab2, tab3 = st.tabs(["🌐 Vista General", "📈 Análisis por Marca", "🚨 Excepciones"])

            with tab1:
                st.plotly_chart(px.area(df_f.groupby('fecha')[['win', 'coin_in']].sum().reset_index(), x='fecha', y=['win', 'coin_in'], template="plotly_dark", color_discrete_sequence=['#00D1FF', '#FF4B4B']), use_container_width=True)
                
                st.subheader("🤵 Hallazgos del Auditor Estratégico")
                # Cálculos detallados para los cuadros
                perf_asset = df_f.groupby('asset_Id').agg({'win':'sum','coin_in':'sum','marca':'first'}).reset_index()
                ociosas = perf_asset[perf_asset['coin_in'] <= 0]
                avg_win_sala = wt / len(perf_asset) if not perf_asset.empty else 0
                
                h1, h2, h3, h4 = st.columns(4)
                with h1:
                    lider = df_f.groupby('marca')['win'].sum().idxmax() if not df_f.empty else "N/A"
                    st.markdown(f"<div class='metric-card' style='border-left:5px solid #00D1FF;'><div class='metric-label'>💎 Dominio Mercado</div><div class='metric-value'>{lider}</div><div class='metric-sub'>Líder en generación de ingresos.</div></div>", unsafe_allow_html=True)
                with h2:
                    efi = (df_f.groupby('marca')['win'].sum() / df_f.groupby('marca')['coin_in'].sum()).idxmax() if not df_f.empty else "N/A"
                    st.markdown(f"<div class='metric-card' style='border-left:5px solid #00FF88;'><div class='metric-label'>🚀 Máxima Eficiencia</div><div class='metric-value'>{efi}</div><div class='metric-sub'>Mejor conversión Coin-to-Win.</div></div>", unsafe_allow_html=True)
                with h3:
                    lista_ociosas = ", ".join(ociosas['asset_Id'].astype(str).tolist())
                    st.markdown(f"<div class='metric-card' style='border-left:5px solid #FF4B4B;'><div class='metric-label'>⚠️ Lucro Cesante</div><div class='metric-value'>{len(ociosas)} Assets</div><div class='metric-sub'><b>IDs:</b> {lista_ociosas if lista_ociosas else 'Ninguno'}</div></div>", unsafe_allow_html=True)
                with h4:
                    st.markdown(f"<div class='metric-card' style='border-left:5px solid #FFCC00;'><div class='metric-label'>📊 Promedio ID</div><div class='metric-value'>{form_num(avg_win_sala)}</div><div class='metric-sub'>Media de rendimiento por activo.</div></div>", unsafe_allow_html=True)

            with tab2:
                col1, col2 = st.columns(2)
                df_marca = df_f.groupby('marca')['win'].sum().reset_index()
                col1.plotly_chart(px.pie(df_marca, values='win', names='marca', hole=.4, template="plotly_dark", title="Win Share por Marca"), use_container_width=True)
                df_juego = df_f.groupby('juego')['win'].sum().nlargest(10).reset_index()
                col2.plotly_chart(px.bar(df_juego, x='win', y='juego', orientation='h', template="plotly_dark", title="Top 10 Juegos"), use_container_width=True)

            with tab3:
                st.subheader("🔎 Detalle de Máquinas sin Actividad")
                st.table(ociosas[['asset_Id', 'marca']])

        # --- SECCIÓN 2: ANALISTA COMPARATIVO ---
        elif nav == "🔄 Analista Comparativo":
            st.title("⚖️ Diagnóstico Comparativo de Períodos")
            
            with st.container(border=True):
                f_c1, f_c2 = st.columns(2)
                r_a = f_c1.date_input("Período A (Actual)", [df_slots['fecha'].max() - timedelta(days=7), df_slots['fecha'].max()])
                r_b = f_c2.date_input("Período B (Referencia)", [df_slots['fecha'].max() - timedelta(days=15), df_slots['fecha'].max() - timedelta(days=8)])

            if len(r_a) == 2 and len(r_b) == 2:
                df_a = df_slots[(df_slots['fecha'] >= r_a[0]) & (df_slots['fecha'] <= r_a[1])]
                df_b = df_slots[(df_slots['fecha'] >= r_b[0]) & (df_slots['fecha'] <= r_b[1])]
                
                wa, wb = df_a['win'].sum(), df_b['win'].sum()
                ca, cb = df_a['coin_in'].sum(), df_b['coin_in'].sum()
                pct_w = ((wa - wb) / wb * 100) if wb != 0 else 0
                pct_c = ((ca - cb) / cb * 100) if cb != 0 else 0
                
                v1, v2, v3, v4 = st.columns(4)
                with v1: st.markdown(f"<div class='metric-card' style='border-left:5px solid #00FF88;'><div class='metric-label'>Variación Win</div><div class='metric-value'>{form_num(wa)}</div><div class='metric-sub'>{pct_w:+.1f}% vs Ref.</div></div>", unsafe_allow_html=True)
                with v2: st.markdown(f"<div class='metric-card' style='border-left:5px solid #FFCC00;'><div class='metric-label'>Impacto Tráfico</div><div class='metric-value'>{pct_c:+.1f}%</div><div class='metric-sub'>Delta de Coin In.</div></div>", unsafe_allow_html=True)
                with v3:
                    # Máquina con mayor caída
                    pa, pb = df_a.groupby('asset_Id')['win'].sum(), df_b.groupby('asset_Id')['win'].sum()
                    dif_assets = (pa - pb).dropna().sort_values()
                    peor_id = dif_assets.index[0] if not dif_assets.empty else "N/A"
                    st.markdown(f"<div class='metric-card' style='border-left:5px solid #FF4B4B;'><div class='metric-label'>Asset Crítico</div><div class='metric-value'>ID {peor_id}</div><div class='metric-sub'>Mayor caída de recaudación.</div></div>", unsafe_allow_html=True)
                with v4:
                    ociosas_a = df_a.groupby('asset_Id')['coin_in'].sum()
                    st.markdown(f"<div class='metric-card' style='border-left:5px solid #A0A0A0;'><div class='metric-label'>Lucro Cesante</div><div class='metric-value'>{len(ociosas_a[ociosas_a==0])} Assets</div><div class='metric-sub'>Sin actividad en Período A.</div></div>", unsafe_allow_html=True)

                # INFORME NARRATIVO
                st.subheader("🕵️ Análisis Detallado del Analista")
                bajaron = dif_assets[dif_assets < 0]
                st.markdown(f"""
                <div class="report-box">
                    <h4>Diagnóstico Operativo Comparativo:</h4>
                    <ul>
                        <li><b>Rendimiento:</b> La sala presenta una variación neta del <b>{pct_w:+.1f}%</b> en ganancias.</li>
                        <li><b>Alertas de Desempeño:</b> Se detectaron <b>{len(bajaron)} máquinas</b> que recaudaron menos que el período anterior.</li>
                        <li><b>Top Caídas:</b> Los activos <b>{", ".join(bajaron.index[:5].astype(str))}</b> muestran la mayor pérdida de rentabilidad.</li>
                        <li><b>Eficiencia:</b> El Hold varió de <b>{(wb/cb*100 if cb>0 else 0):.2f}%</b> a <b>{(wa/ca*100 if ca>0 else 0):.2f}%</b>.</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)
                
                st.plotly_chart(px.bar(pd.DataFrame({'Per':['Actual','Referencia'],'Win':[wa,wb]}), x='Per', y='Win', color='Per', template="plotly_dark"), use_container_width=True)

        elif nav == "👤 Gestión Usuarios":
            st.title("👤 Gestión de Usuarios")
            st.dataframe(df_users[['nombre', 'usuario', 'rol']], use_container_width=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Credenciales incorrectas')