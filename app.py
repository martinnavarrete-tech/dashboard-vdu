import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit_authenticator as stauth
import plotly.express as px
import re
import requests
import time
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
    .bot-response { background-color: #1E1E2E; border-left: 4px solid #00FF88; padding: 20px; border-radius: 5px; margin: 10px 0; color: #E0E0E0; line-height: 1.6; }
    .bot-alert { color: #FF4B4B; font-weight: bold; }
    .bot-highlight { color: #00FF88; font-weight: bold; }
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
        
        sheet_u = client.open_by_key(ID_CONFIGURACION).worksheet("Usuarios")
        df_u = pd.DataFrame(sheet_u.get_all_records())
        
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
        st.error(f"Error de sincronización: {e}")
        return None, None, pd.DataFrame()

df_slots, df_users, df_feedback = load_all_data()

# --- 3. ANALISTA LÓGICO MEJORADO ---
def get_logic_analysis(user_query, df_f):
    """
    Motor analítico que procesa los datos filtrados y genera diagnósticos inteligentes.
    """
    if df_f.empty:
        return "No hay datos suficientes para realizar un análisis. Por favor, ajusta los filtros."

    query = user_query.lower()
    
    # 1. Métricas Base
    total_win = df_f['win'].sum()
    total_coin = df_f['coin_in'].sum()
    total_jackpot = df_f['jackpot'].sum() if 'jackpot' in df_f.columns else 0
    hold = (total_win / total_coin * 100) if total_coin > 0 else 0
    assets_unique = df_f['asset_Id'].unique()
    assets_count = len(assets_unique)
    
    # 2. Análisis por Máquina
    by_asset = df_f.groupby('asset_Id').agg({'win': 'sum', 'coin_in': 'sum'}).reset_index()
    by_asset['hold'] = (by_asset['win'] / by_asset['coin_in'] * 100).fillna(0)
    
    top_performer = by_asset.sort_values('win', ascending=False).iloc[0]
    critical_hold = by_asset[by_asset['hold'] < 3.0]
    high_hold = by_asset[by_asset['hold'] > 15.0]

    # 3. Tendencia Temporal (Si hay más de 1 día)
    fechas = sorted(df_f['fecha'].unique())
    tendencia = ""
    if len(fechas) > 1:
        win_primera = df_f[df_f['fecha'] == fechas[0]]['win'].sum()
        win_ultima = df_f[df_f['fecha'] == fechas[-1]]['win'].sum()
        var = ((win_ultima - win_primera) / win_primera * 100) if win_primera > 0 else 0
        status_trend = "crecimiento" if var > 0 else "caída"
        tendencia = f"He observado una **{status_trend} del {abs(var):.1f}%** en el Win diario entre el inicio y el fin del periodo."

    # LÓGICA DE RESPUESTA SEGÚN INTENCIÓN
    
    # Intención: Anomalías o Problemas
    if any(word in query for word in ["anomalía", "error", "problema", "mal", "crítico", "baja"]):
        resp = f"🔍 **Diagnóstico de Anomalías:**\n\n"
        if not critical_assets.empty:
            resp += f"⚠️ Se detectaron **{len(critical_hold)} máquinas** con un Hold < 3%. Destacan los Assets: {', '.join(map(str, critical_hold['asset_Id'].tolist()[:3]))}. Esto podría indicar un Jackpot pagado recientemente o un desajuste en el porcentaje.\n"
        
        if total_coin < (df_slots['coin_in'].mean() * assets_count):
            resp += f"📉 El volumen de apuestas (Coin In) está por debajo del promedio histórico de la sala. Sugiero revisar el tráfico de clientes.\n"
        
        if not resp.count("\n") > 2:
            resp += "No se detectan comportamientos fuera de norma. La sala opera con un Hold estable de " + f"{hold:.2f}%."
        return resp

    # Intención: Rendimiento o Ranking
    elif any(word in query for word in ["mejor", "ranking", "top", "ganancia", "rendimiento"]):
        resp = f"🏆 **Análisis de Rendimiento:**\n\n"
        resp += f"La máquina estrella es la **ID {top_performer['asset_Id']}**, con una recaudación de {form_num(top_performer['win'])} y un Hold del {top_performer['hold']:.1f}%.\n"
        
        # Juego con más Coin In
        if 'juego' in df_f.columns:
            top_juego = df_f.groupby('juego')['coin_in'].sum().sort_values(ascending=False).index[0]
            resp += f"El título más jugado en este segmento es **{top_juego}**, traccionando la mayor parte del tráfico.\n"
        
        resp += f"\n{tendencia}"
        return resp

    # Intención: Hold o Eficiencia
    elif any(word in query for word in ["hold", "porcentaje", "eficiencia", "matemática"]):
        eval_hold = "Excelente" if 7 <= hold <= 11 else "Revisar"
        resp = f"📊 **Auditoría de Hold ({eval_hold}):**\n\n"
        resp += f"El Hold real consolidado es del **{hold:.2f}%**.\n"
        resp += f"- Coin In: {form_num(total_coin)}\n"
        resp += f"- Win: {form_num(total_win)}\n"
        if total_jackpot > 0:
            resp += f"- Impacto Jackpots: {form_num(total_jackpot)} (reducen el Win neto).\n"
        
        if not high_hold.empty:
            resp += f"\n💡 Nota: Hay {len(high_hold)} máquinas con Hold > 15%, lo que podría afectar la permanencia del cliente a largo plazo."
        return resp

    # Respuesta General Inteligente (Resumen Ejecutivo)
    else:
        resp = f"👋 **Resumen Ejecutivo de Sala:**\n\n"
        resp += f"Actualmente analizo **{assets_count} activos**. La sala presenta un Win total de **{form_num(total_win)}**.\n\n"
        resp += f"**Indicadores Clave:**\n"
        resp += f"- Hold Promedio: `{hold:.2f}%`\n"
        resp += f"- Máquina Líder: `ID {top_performer['asset_Id']}`\n"
        resp += f"- Estado de Tráfico: {'Estable' if total_coin > 0 else 'Sin datos'}\n\n"
        resp += f"¿Deseas un informe detallado sobre **anomalías**, **ranking de máquinas** o **eficiencia de hold**?"
        return resp

# --- 4. FUNCIONES DE ESCRITURA ---
def enviar_consulta_automatica(usuario, categoria, texto, ai_resp):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(ID_CONFIGURACION).worksheet("Feedback")
        
        nuevo_id = f"IA-{datetime.now().strftime('%d%H%M%S')}"
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
        
        sheet.append_row([nuevo_id, fecha, usuario, categoria, texto, ai_resp, "Finalizado"])
        return True
    except Exception as e:
        st.error(f"Error al registrar en Google Sheets: {e}")
        return False

# --- 5. INTERFAZ PRINCIPAL ---
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
            st.write(f"Operador: **{st.session_state['name']}**")
            st.divider()
            nav = st.radio("Navegación", ["📊 Dashboard de Sala", "🔄 Analista Comparativo", "🤖 Consultar al Bot", "👤 Gestión Usuarios"])
            st.write("")
            authenticator.logout('Cerrar Sesión')

        # Filtros globales (inicializados con todos los datos)
        if 'filtered_df' not in st.session_state:
            st.session_state['filtered_df'] = df_slots.copy()

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
            
            st.session_state['filtered_df'] = df_f

            wt, ct = df_f['win'].sum(), df_f['coin_in'].sum()
            ht = (wt/ct*100) if ct > 0 else 0
            
            k1, k2, k3 = st.columns(3)
            with k1: st.markdown(f"<div class='main-kpi-label'>NET WIN TOTAL</div><div class='main-kpi-val'>{form_num(wt)}</div>", unsafe_allow_html=True)
            with k2: st.markdown(f"<div class='main-kpi-label'>COIN IN</div><div class='main-kpi-val'>{form_num(ct)}</div>", unsafe_allow_html=True)
            with k3: st.markdown(f"<div class='main-kpi-label'>HOLD REAL %</div><div class='main-kpi-val'>{ht:.2f}%</div>", unsafe_allow_html=True)

            st.plotly_chart(px.area(df_f.groupby('fecha')[['win', 'coin_in']].sum().reset_index(), x='fecha', y=['win', 'coin_in'], template="plotly_dark", color_discrete_sequence=['#00D1FF', '#FF4B4B']), use_container_width=True)

        elif nav == "🔄 Analista Comparativo":
            st.title("⚖️ Diagnóstico Comparativo")
            st.info("Utilice esta sección para medir variaciones entre periodos.")

        elif nav == "🤖 Consultar al Bot":
            st.title("🤖 Analista de Sala Inteligente")
            st.markdown("### ¿Qué deseas auditar hoy?")
            st.caption("Analizo tendencias, anomalías y rankings basándome en los filtros de tu Dashboard.")
            
            df_analizar = st.session_state.get('filtered_df', df_slots)

            with st.container(border=True):
                with st.form("bot_form"):
                    pregunta = st.text_input("Haz una consulta técnica:", placeholder="Ej: ¿Qué anomalías hay? / Ranking de máquinas / Informe de Hold")
                    submit = st.form_submit_button("Analizar Datos")
                    
                    if submit and pregunta:
                        with st.spinner("Procesando auditoría de datos..."):
                            respuesta = get_logic_analysis(pregunta, df_analizar)
                            enviar_consulta_automatica(st.session_state['name'], "Análisis Inteligente", pregunta, respuesta)
                            st.markdown(f"<div class='bot-response'><b>🤖 Analista VDU:</b><br><br>{respuesta}</div>", unsafe_allow_html=True)
                            st.cache_data.clear()

            st.divider()
            st.subheader("📋 Registro de Análisis")
            _, _, df_feedback_updated = load_all_data()
            if not df_feedback_updated.empty:
                st.dataframe(df_feedback_updated.sort_values("Fecha", ascending=False), use_container_width=True, hide_index=True)

        elif nav == "👤 Gestión Usuarios":
            st.title("👤 Administración")
            st.dataframe(df_users[['nombre', 'usuario', 'rol']], use_container_width=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Usuario o Contraseña incorrectos')