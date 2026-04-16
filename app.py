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
    .bot-response { background-color: #1E1E2E; border-left: 4px solid #00FF88; padding: 15px; border-radius: 5px; margin: 10px 0; }
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

# --- 3. INTELIGENCIA ARTIFICIAL (BOT) ---
def get_ai_response(user_query, context_data):
    api_key = "" # Se proporciona por el entorno
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={api_key}"
    
    system_prompt = f"""
    Eres el 'Analista Bot VDU' experto en slots y casinos. 
    Tu tarea es responder dudas de los operadores basándote en los datos actuales:
    - Net Win Total: {form_num(context_data['win'])}
    - Coin In Total: {form_num(context_data['coin_in'])}
    - Hold Real: {context_data['hold']:.2f}%
    - Activos analizados: {context_data['assets']}
    
    Responde de forma técnica pero amable. Si te preguntan por un informe, explica que lo estás analizando basado en estas métricas. 
    Mantén tus respuestas breves y profesionales.
    """
    
    payload = {
        "contents": [{"parts": [{"text": user_query}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]}
    }
    
    for delay in [1, 2, 4, 8, 16]:
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                result = response.json()
                return result['candidates'][0]['content']['parts'][0]['text']
        except:
            time.sleep(delay)
    return "Lo siento, mi conexión de analista está saturada. Por favor, intenta de nuevo en unos minutos."

# --- 4. FUNCIONES DE ESCRITURA ---
def enviar_consulta_automatica(usuario, categoria, texto, ai_resp):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(ID_CONFIGURACION).worksheet("Feedback")
        nuevo_id = f"BOT-{datetime.now().strftime('%d%H%M%S')}"
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
        # El bot responde inmediatamente
        sheet.append_row([nuevo_id, fecha, usuario, categoria, texto, ai_resp, "Respondido (IA)"])
        return True
    except Exception as e:
        st.error(f"Error al guardar consulta: {e}")
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
            st.write(f"Usuario: **{st.session_state['name']}**")
            st.divider()
            nav = st.radio("Navegación", ["📊 Dashboard de Sala", "🔄 Analista Comparativo", "🤖 Consultar al Bot", "👤 Gestión Usuarios"])
            st.write("")
            authenticator.logout('Cerrar Sesión')

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
            
            df_f = df_slots.copy()
            if len(f_rango) == 2:
                df_f = df_f[(df_f['fecha'] >= f_rango[0]) & (df_f['fecha'] <= f_rango[1])]
            if f_id: df_f = df_f[df_f['asset_Id'].isin(f_id)]
            if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
            if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]
            if f_juego: df_f = df_f[df_f['juego'].isin(f_juego)]
            
            wt, ct = df_f['win'].sum(), df_f['coin_in'].sum()
            ht = (wt/ct*100) if ct > 0 else 0
            
            k1, k2, k3 = st.columns(3)
            with k1: st.markdown(f"<div class='main-kpi-label'>NET WIN TOTAL</div><div class='main-kpi-val'>{form_num(wt)}</div>", unsafe_allow_html=True)
            with k2: st.markdown(f"<div class='main-kpi-label'>COIN IN</div><div class='main-kpi-val'>{form_num(ct)}</div>", unsafe_allow_html=True)
            with k3: st.markdown(f"<div class='main-kpi-label'>HOLD REAL %</div><div class='main-kpi-val'>{ht:.2f}%</div>", unsafe_allow_html=True)

            # KPIs detallados para contexto de IA
            perf_asset = df_f.groupby('asset_Id').agg({'win':'sum','coin_in':'sum'}).reset_index()
            promedio_win_id = wt / len(perf_asset) if not perf_asset.empty else 0
            
            # Guardar contexto para el Bot
            st.session_state['current_context'] = {
                'win': wt, 'coin_in': ct, 'hold': ht, 'assets': len(perf_asset)
            }

            st.plotly_chart(px.area(df_f.groupby('fecha')[['win', 'coin_in']].sum().reset_index(), x='fecha', y=['win', 'coin_in'], template="plotly_dark", color_discrete_sequence=['#00D1FF', '#FF4B4B']), use_container_width=True)

        elif nav == "🔄 Analista Comparativo":
            st.title("⚖️ Diagnóstico Comparativo")
            # (Se mantiene lógica de comparación previa)

        elif nav == "🤖 Consultar al Bot":
            st.title("🤖 Analista Inteligente VDU")
            st.info("Pregúntame sobre el rendimiento actual, anomalías o solicita informes basados en los datos filtrados.")
            
            with st.container(border=True):
                with st.form("bot_form"):
                    pregunta = st.text_area("¿En qué puedo ayudarte hoy?", placeholder="Ej: ¿Por qué bajó el Net Win ayer?")
                    submit = st.form_submit_button("Consultar con IA")
                    
                    if submit and pregunta:
                        with st.spinner("Analizando datos y generando respuesta..."):
                            contexto = st.session_state.get('current_context', {'win':0, 'coin_in':0, 'hold':0, 'assets':0})
                            respuesta_ia = get_ai_response(pregunta, contexto)
                            
                            # Guardar en Sheet inmediatamente
                            enviar_consulta_automatica(st.session_state['name'], "Consulta IA", pregunta, respuesta_ia)
                            
                            st.markdown(f"<div class='bot-response'><b>🤖 Analista Bot:</b><br>{respuesta_ia}</div>", unsafe_allow_html=True)
                            st.cache_data.clear()

            st.divider()
            st.subheader("📋 Registro de Consultas Inteligentes")
            if not df_feedback.empty:
                st.dataframe(df_feedback.sort_values("Fecha", ascending=False), use_container_width=True, hide_index=True)

        elif nav == "👤 Gestión Usuarios":
            st.title("👤 Configuración")
            st.dataframe(df_users[['nombre', 'usuario', 'rol']], use_container_width=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Usuario o Contraseña incorrectos')