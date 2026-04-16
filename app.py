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
    .report-box { background-color: #161625; padding: 25px; border-radius: 10px; border-left: 4px solid #00D1FF; margin-top: 20px; }
    .main-kpi-val { font-size: 2.8rem; font-weight: 800; color: #FFFFFF; line-height: 1.1; }
    .main-kpi-label { font-size: 0.9rem; color: #A0A0A0; text-transform: uppercase; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

def form_num(valor):
    try:
        return f"$ {valor:,.0f}".replace(',', '.')
    except:
        return "$ 0"

# IDs de los Libros de Google Sheets
ID_CONFIGURACION = "1W_68ToMyy_nu1oPH7ePFj74_vc1op5bGiFoP4KtaY0I"
ID_DATOS_CUBO = "1ZYn6foApzeEeKg_qKzW9faQFjBPXHoc8ffB_CeZ3f_s"

# --- 2. MOTOR DE DATOS ---
@st.cache_data(ttl=60)
def load_all_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        
        # Usuarios (Libro Configuración)
        sheet_u = client.open_by_key(ID_CONFIGURACION).worksheet("Usuarios")
        df_u = pd.DataFrame(sheet_u.get_all_records())
        
        # Cubo (Libro Datos)
        sheet_s = client.open_by_key(ID_DATOS_CUBO).worksheet("Cubo")
        data_s = sheet_s.get_all_values()
        df_s = pd.DataFrame(data_s[1:], columns=data_s[0])
        
        df_s = df_s.loc[:, df_s.columns.str.contains('^$|Unnamed') == False]
        df_s['fecha'] = pd.to_datetime(df_s['fecha'], dayfirst=True, errors='coerce').dt.date
        df_s = df_s.dropna(subset=['fecha'])
        
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
        
        # Feedback (Ahora en Libro Configuración)
        df_fback = pd.DataFrame(columns=["ID", "Fecha", "Usuario", "Categoria", "Consulta", "Respuesta", "Estado"])
        try:
            sheet_f = client.open_by_key(ID_CONFIGURACION).worksheet("Feedback")
            data_f = sheet_f.get_all_records()
            if data_f:
                df_fback = pd.DataFrame(data_f)
        except:
            pass
            
        return df_s, df_u, df_fback
    except Exception as e:
        st.error(f"Error de sincronización de datos: {e}")
        return None, None, pd.DataFrame()

df_slots, df_users, df_feedback = load_all_data()

# --- FUNCIONES DE ESCRITURA ---
def enviar_consulta(usuario, categoria, texto):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        
        try:
            # Apuntamos al libro de Configuración
            sheet = client.open_by_key(ID_CONFIGURACION).worksheet("Feedback")
        except:
            st.error("La pestaña 'Feedback' no fue encontrada en el libro VDU_Configuracion.")
            return False
            
        nuevo_id = f"Q-{datetime.now().strftime('%d%H%M%S')}"
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
        sheet.append_row([nuevo_id, fecha, usuario, categoria, texto, "", "Pendiente"])
        return True
    except Exception as e:
        st.error(f"Error técnico al guardar: {e}")
        return False

def responder_consulta(ticket_id, respuesta_texto):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(ID_CONFIGURACION).worksheet("Feedback")
        celda = sheet.find(ticket_id)
        if celda:
            sheet.update_cell(celda.row, 6, respuesta_texto)
            sheet.update_cell(celda.row, 7, "Respondido")
            return True
        return False
    except Exception as e:
        st.error(f"Error al responder: {e}")
        return False

# --- 3. AUTENTICACIÓN ---
if df_users is not None:
    credentials = {"usernames": {u.lower(): {"name": r['nombre'], "password": str(r['password']), "role": r['rol']} 
                   for u, r in df_users.set_index('usuario').iterrows()}}
    authenticator = stauth.Authenticate(credentials, "vdu_app", "auth_key", 30)
    authenticator.login(location='main')

    if st.session_state.get("authentication_status"):
        curr_user = st.session_state['username'].lower()
        user_role = credentials["usernames"][curr_user]["role"]

        with st.sidebar:
            st.title("🛡️ Casino Fuente Mayor")
            st.write(f"Usuario: **{st.session_state['name']}**")
            st.caption(f"Rol: {user_role}")
            st.divider()
            nav = st.radio("Navegación", ["📊 Dashboard de Sala", "🔄 Analista Comparativo", "📩 Consultas al Analista", "👤 Gestión Usuarios"])
            st.write("")
            authenticator.logout('Cerrar Sesión')

        if nav == "📊 Dashboard de Sala":
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
                
                st.subheader("🤵 Hallazgos Detallados")
                
                if not df_f.empty:
                    col_analisis = 'modelo' if f_marca else 'marca'
                    contexto = f"en {', '.join(f_marca)}" if f_marca else "del mercado"

                    lider_df = df_f.groupby(col_analisis)['win'].sum().reset_index()
                    lider_row = lider_df.sort_values('win', ascending=False).iloc[0]
                    share_win = (lider_row['win'] / wt * 100) if wt > 0 else 0

                    efi_df = df_f.groupby(col_analisis).agg({'win':'sum', 'coin_in':'sum'})
                    efi_df['yield'] = efi_df['win'] / efi_df['coin_in']
                    efi_row = efi_df.sort_values('yield', ascending=False).iloc[0]
                    performance_vs_avg = (efi_row['yield'] / (wt/ct)) if ct > 0 else 0

                    perf_asset = df_f.groupby('asset_Id').agg({'win':'sum','coin_in':'sum'}).reset_index()
                    ociosas = perf_asset[perf_asset['coin_in'] <= 0]
                    pct_ociosas = (len(ociosas) / len(perf_asset) * 100) if not perf_asset.empty else 0
                    ociosas_ids = ", ".join(map(str, ociosas['asset_Id'].tolist()[:5])) + ("..." if len(ociosas) > 5 else "")

                    promedio_win_id = wt / len(perf_asset) if not perf_asset.empty else 0
                    superan_promedio = len(perf_asset[perf_asset['win'] > promedio_win_id])

                    h1, h2, h3, h4 = st.columns(4)
                    with h1:
                        st.markdown(f"<div class='metric-card' style='border-left:5px solid #00D1FF;'><div class='metric-label'>💎 DOMINIO MERCADO</div><div class='metric-value'>{lider_row[col_analisis]}</div><div class='metric-sub'>Representa el <b>{share_win:.1f}%</b> del Win Total {contexto}.</div></div>", unsafe_allow_html=True)
                    with h2:
                        st.markdown(f"<div class='metric-card' style='border-left:5px solid #00FF88;'><div class='metric-label'>🚀 MÁXIMA EFICIENCIA</div><div class='metric-value'>{efi_row.name}</div><div class='metric-sub'>Rinde <b>{performance_vs_avg:.1f}x</b> más que el promedio del mercado.</div></div>", unsafe_allow_html=True)
                    with h3:
                        st.markdown(f"<div class='metric-card' style='border-left:5px solid #FF4B4B;'><div class='metric-label'>⚠️ LUCRO CESANTE</div><div class='metric-value'>{len(ociosas)} Assets</div><div class='metric-sub'><b>{pct_ociosas:.1f}%</b> de la flota inactiva.<br>IDs: {ociosas_ids if ociosas_ids else 'Ninguno'}</div></div>", unsafe_allow_html=True)
                    with h4:
                        st.markdown(f"<div class='metric-card' style='border-left:5px solid #FFCC00;'><div class='metric-label'>📊 PROMEDIO ID</div><div class='metric-value'>{form_num(promedio_win_id)}</div><div class='metric-sub'><b>{superan_promedio}</b> activos superan el rendimiento medio.</div></div>", unsafe_allow_html=True)

            with tab2:
                col1, col2 = st.columns(2)
                df_marca_w = df_f.groupby('marca')['win'].sum().reset_index()
                col1.plotly_chart(px.pie(df_marca_w, values='win', names='marca', hole=.4, template="plotly_dark", title="Win Share (Ganancia)"), use_container_width=True)
                df_marca_c = df_f.groupby('marca')['coin_in'].sum().reset_index()
                col2.plotly_chart(px.pie(df_marca_c, values='coin_in', names='marca', hole=.4, template="plotly_dark", title="Coin In Share (Tráfico)"), use_container_width=True)

            with tab3:
                st.subheader("🔎 Detalle de Máquinas sin Actividad")
                if not df_f.empty and not ociosas.empty:
                    det_ociosas = pd.merge(ociosas[['asset_Id']], df_f[['asset_Id', 'marca', 'modelo', 'juego']].drop_duplicates(), on='asset_Id')
                    st.table(det_ociosas)
                else:
                    st.success("Todos los activos seleccionados presentan actividad.")

        elif nav == "🔄 Analista Comparativo":
            st.title("⚖️ Diagnóstico Comparativo de Períodos")
            with st.container(border=True):
                f_c1, f_c2 = st.columns(2)
                r_a = f_c1.date_input("Período A (Actual)", [df_slots['fecha'].max() - timedelta(days=7), df_slots['fecha'].max()])
                r_b = f_c2.date_input("Período B (Referencia)", [df_slots['fecha'].max() - timedelta(days=15), df_slots['fecha'].max() - timedelta(days=8)])

            if len(r_a) == 2 and len(r_b) == 2:
                df_a, df_b = df_slots[(df_slots['fecha'] >= r_a[0]) & (df_slots['fecha'] <= r_a[1])], df_slots[(df_slots['fecha'] >= r_b[0]) & (df_slots['fecha'] <= r_b[1])]
                wa, wb = df_a['win'].sum(), df_b['win'].sum()
                ca, cb = df_a['coin_in'].sum(), df_b['coin_in'].sum()
                pct_w = ((wa - wb) / wb * 100) if wb != 0 else 0
                pct_c = ((ca - cb) / cb * 100) if cb != 0 else 0
                
                v1, v2, v3, v4 = st.columns(4)
                with v1: st.markdown(f"<div class='metric-card' style='border-left:5px solid #00FF88;'><div class='metric-label'>Variación Win</div><div class='metric-value'>{form_num(wa)}</div><div class='metric-sub'>{pct_w:+.1f}% vs Ref.</div></div>", unsafe_allow_html=True)
                with v2: st.markdown(f"<div class='metric-card' style='border-left:5px solid #FFCC00;'><div class='metric-label'>Impacto Tráfico</div><div class='metric-value'>{pct_c:+.1f}%</div><div class='metric-sub'>Delta de Coin In.</div></div>", unsafe_allow_html=True)
                with v3:
                    pa, pb = df_a.groupby('asset_Id')['win'].sum(), df_b.groupby('asset_Id')['win'].sum()
                    dif = (pa - pb).dropna().sort_values()
                    st.markdown(f"<div class='metric-card' style='border-left:5px solid #FF4B4B;'><div class='metric-label'>Asset Crítico</div><div class='metric-value'>ID {dif.index[0] if not dif.empty else 'N/A'}</div><div class='metric-sub'>Mayor caída de recaudación.</div></div>", unsafe_allow_html=True)
                with v4:
                    st.markdown(f"<div class='metric-card' style='border-left:5px solid #A0A0A0;'><div class='metric-label'>Eficiencia Comp.</div><div class='metric-value'>{(wa/ca*100 if ca>0 else 0):.1f}%</div><div class='metric-sub'>Hold Real del período actual.</div></div>", unsafe_allow_html=True)

        elif nav == "📩 Consultas al Analista":
            st.title("📩 Centro de Consultas")
            
            if user_role == "Analista":
                st.info("💡 **Modo Analista:** Responde a las inquietudes de sala.")
                pendientes = df_feedback[df_feedback['Estado'] == 'Pendiente']
                if not pendientes.empty:
                    ticket_sel = st.selectbox("Ticket a responder", pendientes['ID'].tolist())
                    row_sel = pendientes[pendientes['ID'] == ticket_sel].iloc[0]
                    st.warning(f"**{row_sel['Usuario']} pregunta:** {row_sel['Consulta']}")
                    resp_txt = st.text_area("Escribe tu respuesta:")
                    if st.button("Enviar Respuesta"):
                        if responder_consulta(ticket_sel, resp_txt):
                            st.success("Respuesta guardada.")
                            st.cache_data.clear()
                            st.rerun()
                else:
                    st.success("No hay consultas pendientes.")
            else:
                with st.expander("➕ CREAR NUEVA CONSULTA", expanded=True):
                    with st.form("form_q"):
                        cat = st.selectbox("Categoría", ["Solicitud de Informe", "Anomalía detectada", "Duda de Asset", "Otro"])
                        duda = st.text_area("Explica tu duda o hallazgo:")
                        if st.form_submit_button("Enviar al Analista"):
                            if duda:
                                if enviar_consulta(st.session_state['name'], cat, duda):
                                    st.success("Consulta enviada con éxito.")
                                    st.cache_data.clear()
                                    st.rerun()
                            else: st.error("Por favor escribe tu consulta.")

            st.subheader("📋 Historial de Consultas")
            if not df_feedback.empty:
                st.dataframe(df_feedback.sort_values("Fecha", ascending=False), use_container_width=True, hide_index=True)
            else:
                st.write("Aún no hay consultas en el historial.")

        elif nav == "👤 Gestión Usuarios":
            st.title("👤 Gestión de Usuarios")
            st.dataframe(df_users[['nombre', 'usuario', 'rol', 'password']], use_container_width=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Credenciales incorrectas')    