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

# --- 3. ANALISTA LÓGICO (SIN COSTO) ---
def get_logic_analysis(user_query, df_f):
    """
    Simula una IA analizando los datos actuales sin usar APIs externas.
    Detecta palabras clave y calcula métricas en tiempo real.
    """
    query = user_query.lower()
    
    # Cálculos base sobre los datos filtrados
    total_win = df_f['win'].sum()
    total_coin = df_f['coin_in'].sum()
    hold = (total_win / total_coin * 100) if total_coin > 0 else 0
    assets_count = len(df_f['asset_Id'].unique())
    
    # Identificar mejores y peores
    by_asset = df_f.groupby('asset_Id')['win'].sum().sort_values(ascending=False)
    top_asset = by_asset.index[0] if not by_asset.empty else "N/A"
    top_win = by_asset.iloc[0] if not by_asset.empty else 0
    
    low_hold_assets = df_f.groupby('asset_Id').apply(lambda x: (x['win'].sum()/x['coin_in'].sum()*100) if x['coin_in'].sum() > 0 else 0)
    critical_assets = low_hold_assets[low_hold_assets < 3].index.tolist()

    # Lógica de respuesta por intención
    if any(word in query for word in ["anomalía", "error", "problema", "mal", "crítico"]):
        resp = f"🔍 **Informe de Anomalías:** He detectado que de los {assets_count} activos analizados, "
        if critical_assets:
            resp += f"hay **{len(critical_assets)} máquinas** con un Hold peligrosamente bajo (menor al 3%). "
            resp += f"Recomiendo inspeccionar los Assets: {', '.join(map(str, critical_assets[:5]))}."
        else:
            resp += "el rendimiento general es estable. El Hold promedio está en un saludable " + f"{hold:.2f}%."
        return resp

    elif any(word in query for word in ["mejor", "ganancia", "top", "máquina", "ranking"]):
        return (f"🏆 **Ranking de Rendimiento:** La máquina con mayor recaudación en este periodo es la **ID {top_asset}**, "
                f"con un Net Win de {form_num(top_win)}. "
                f"Esto representa un impacto significativo sobre el total de {form_num(total_win)} de la sala.")

    elif any(word in query for word in ["hold", "porcentaje", "eficiencia"]):
        status = "dentro del rango esperado" if 5 <= hold <= 12 else "fuera de los parámetros ideales"
        return (f"📊 **Análisis de Eficiencia:** El Hold real actual es del **{hold:.2f}%**. "
                f"Este valor se encuentra {status}. "
                f"Recuerda que el Coin In total analizado es de {form_num(total_coin)}.")

    else:
        # Respuesta genérica inteligente
        return (f"👋 Hola, soy tu Analista VDU. Basado en los filtros actuales:\n\n"
                f"- Analizo **{assets_count}** activos.\n"
                f"- El Net Win acumulado es **{form_num(total_win)}**.\n"
                f"- El tráfico (Coin In) es de **{form_num(total_coin)}**.\n"
                f"- El Hold promedio es **{hold:.2f}%**.\n\n"
                f"¿Deseas que profundice en alguna máquina o anomalía específica?")

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
        
        # Guardar en Sheet
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

        # Aplicar filtros globales para que el bot los use
        df_f_global = df_slots.copy()

        if nav == "📊 Dashboard de Sala":
            st.title("Dashboard Fuente Mayor VDU")
            # --- FILTROS ---
            with st.container(border=True):
                r1, r2 = st.columns([1, 3])
                f_rango = r1.date_input("📅 Ventana Temporal", [df_slots['fecha'].min(), df_slots['fecha'].max()])
                c1, c2, c3, c4 = st.columns(4)
                f_id = c1.multiselect("🆔 Asset ID", sorted(df_slots['asset_Id'].unique()))
                f_marca = c2.multiselect("🎰 Marca", sorted(df_slots['marca'].unique()))
                f_modelo = c3.multiselect("📦 Modelo", sorted(df_slots['modelo'].unique()))
                f_juego = c4.multiselect("🎮 Juego", sorted(df_slots['juego'].unique()))
            
            if len(f_rango) == 2:
                df_f_global = df_f_global[(df_f_global['fecha'] >= f_rango[0]) & (df_f_global['fecha'] <= f_rango[1])]
            if f_id: df_f_global = df_f_global[df_f_global['asset_Id'].isin(f_id)]
            if f_marca: df_f_global = df_f_global[df_f_global['marca'].isin(f_marca)]
            if f_modelo: df_f_global = df_f_global[df_f_global['modelo'].isin(f_modelo)]
            if f_juego: df_f_global = df_f_global[df_f_global['juego'].isin(f_juego)]
            
            # Guardar df_f_global en session_state para el bot
            st.session_state['filtered_df'] = df_f_global

            wt, ct = df_f_global['win'].sum(), df_f_global['coin_in'].sum()
            ht = (wt/ct*100) if ct > 0 else 0
            
            k1, k2, k3 = st.columns(3)
            with k1: st.markdown(f"<div class='main-kpi-label'>NET WIN TOTAL</div><div class='main-kpi-val'>{form_num(wt)}</div>", unsafe_allow_html=True)
            with k2: st.markdown(f"<div class='main-kpi-label'>COIN IN</div><div class='main-kpi-val'>{form_num(ct)}</div>", unsafe_allow_html=True)
            with k3: st.markdown(f"<div class='main-kpi-label'>HOLD REAL %</div><div class='main-kpi-val'>{ht:.2f}%</div>", unsafe_allow_html=True)

            st.plotly_chart(px.area(df_f_global.groupby('fecha')[['win', 'coin_in']].sum().reset_index(), x='fecha', y=['win', 'coin_in'], template="plotly_dark", color_discrete_sequence=['#00D1FF', '#FF4B4B']), use_container_width=True)

        elif nav == "🔄 Analista Comparativo":
            st.title("⚖️ Diagnóstico Comparativo")
            st.info("Compara dos periodos para identificar desviaciones.")

        elif nav == "🤖 Consultar al Bot":
            st.title("🤖 Analista de Sala Directo")
            st.markdown("### Consultas basadas en Datos Reales")
            st.caption("He desactivado la dependencia de servicios externos para garantizar respuestas inmediatas y gratuitas.")
            
            # Recuperar datos filtrados o usar todos si no hay
            df_analizar = st.session_state.get('filtered_df', df_slots)

            with st.container(border=True):
                with st.form("bot_form"):
                    pregunta = st.text_input("Haz una pregunta sobre los datos actuales:", placeholder="Ej: ¿Qué anomalías hay? o ¿Cuál es la mejor máquina?")
                    submit = st.form_submit_button("Analizar Ahora")
                    
                    if submit and pregunta:
                        with st.spinner("Procesando lógica de datos..."):
                            # Usamos el motor lógico local
                            respuesta_logica = get_logic_analysis(pregunta, df_analizar)
                            
                            # Guardar en Google Sheets para auditoría
                            enviar_consulta_automatica(st.session_state['name'], "Análisis Local", pregunta, respuesta_logica)
                            
                            st.markdown(f"<div class='bot-response'><b>🤖 Analista VDU:</b><br><br>{respuesta_logica}</div>", unsafe_allow_html=True)
                            st.cache_data.clear()

            st.divider()
            st.subheader("📋 Historial de Consultas")
            _, _, df_feedback_updated = load_all_data()
            if not df_feedback_updated.empty:
                st.dataframe(df_feedback_updated.sort_values("Fecha", ascending=False), use_container_width=True, hide_index=True)

        elif nav == "👤 Gestión Usuarios":
            st.title("👤 Configuración de Usuarios")
            st.dataframe(df_users[['nombre', 'usuario', 'rol']], use_container_width=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Usuario o Contraseña incorrectos')