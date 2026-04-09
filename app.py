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
    .main-kpi-val { font-size: 2.8rem; font-weight: 800; color: #FFFFFF; line-height: 1.1; }
    .main-kpi-label { font-size: 0.9rem; color: #A0A0A0; text-transform: uppercase; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

def form_num(valor):
    return f"$ {valor:,.0f}".replace(',', '.')

# --- 2. MOTOR DE DATOS ---
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
        
        return df_s, df_u
    except Exception as e:
        st.error(f"Error: {e}")
        return None, None

df_slots, df_users = load_all_data()

# --- 3. AUTENTICACIÓN ---
if df_users is not None:
    credentials = {"usernames": {u.lower(): {"name": r['nombre'], "password": str(r['password']), "role": r['rol']} 
                   for u, r in df_users.set_index('usuario').iterrows()}}
    authenticator = stauth.Authenticate(credentials, "vdu_app", "auth_key", 30)
    authenticator.login(location='main')

    if st.session_state.get("authentication_status"):
        # --- SIDEBAR ---
        with st.sidebar:
            st.title("🎰 VDU Dashboard")
            st.write(f"Operador: **{st.session_state['name']}**")
            nav = st.radio("Navegación", ["📊 Sala", "🔄 Comparativo"])
            authenticator.logout('Cerrar Sesión')

        if nav == "📊 Sala":
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
            if len(f_rango) == 2: df_f = df_f[(df_f['fecha'] >= f_rango[0]) & (df_f['fecha'] <= f_rango[1])]
            if f_id: df_f = df_f[df_f['asset_Id'].isin(f_id)]
            if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
            if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]
            if f_juego: df_f = df_f[df_f['juego'].isin(f_juego)]

            wt, ct = df_f['win'].sum(), df_f['coin_in'].sum()
            
            # --- KPIS PRINCIPALES ---
            k1, k2, k3 = st.columns(3)
            with k1: st.markdown(f"<div class='main-kpi-label'>NET WIN</div><div class='main-kpi-val'>{form_num(wt)}</div>", unsafe_allow_html=True)
            with k2: st.markdown(f"<div class='main-kpi-label'>COIN IN</div><div class='main-kpi-val'>{form_num(ct)}</div>", unsafe_allow_html=True)
            with k3: st.markdown(f"<div class='main-kpi-label'>HOLD REAL</div><div class='main-kpi-val'>{(wt/ct*100 if ct>0 else 0):.2f}%</div>", unsafe_allow_html=True)
            
            # --- TABS ---
            tab1, tab2 = st.tabs(["🤵 Hallazgos de Win & Eficiencia", "📈 Análisis de Tráfico (Coin In)"])

            with tab1:
                if not df_f.empty:
                    col_an = 'modelo' if f_marca else 'marca'
                    contexto = f"en {', '.join(f_marca)}" if f_marca else "del mercado"
                    
                    # Cálculos Win
                    lider_w = df_f.groupby(col_an)['win'].sum().idxmax()
                    share_w = (df_f.groupby(col_an)['win'].sum().max() / wt * 100) if wt > 0 else 0
                    
                    efi_df = df_f.groupby(col_an).agg({'win':'sum', 'coin_in':'sum'})
                    efi_df['yield'] = efi_df['win'] / efi_df['coin_in']
                    efi_lider = efi_df['yield'].idxmax()
                    mult_efi = efi_df['yield'].max() / (wt/ct) if ct > 0 else 0

                    h1, h2, h3, h4 = st.columns(4)
                    with h1: st.markdown(f"<div class='metric-card' style='border-left:5px solid #00D1FF;'><div class='metric-label'>💎 Dominio Win</div><div class='metric-value'>{lider_w}</div><div class='metric-sub'>Aporta el <b>{share_w:.1f}%</b> del Win total {contexto}.</div></div>", unsafe_allow_html=True)
                    with h2: st.markdown(f"<div class='metric-card' style='border-left:5px solid #00FF88;'><div class='metric-label'>🚀 Máxima Eficiencia</div><div class='metric-value'>{efi_lider}</div><div class='metric-sub'>Convierte <b>{mult_efi:.1f}x</b> mejor que el promedio.</div></div>", unsafe_allow_html=True)
                    with h3:
                        ociosas = df_f.groupby('asset_Id')['coin_in'].sum()
                        ociosas = ociosas[ociosas <= 0]
                        st.markdown(f"<div class='metric-card' style='border-left:5px solid #FF4B4B;'><div class='metric-label'>⚠️ Lucro Cesante</div><div class='metric-value'>{len(ociosas)} Assets</div><div class='metric-sub'>Máquinas con movimiento $0 en el período.</div></div>", unsafe_allow_html=True)
                    with h4:
                        avg_w = wt / df_f['asset_Id'].nunique() if not df_f.empty else 0
                        st.markdown(f"<div class='metric-card' style='border-left:5px solid #FFCC00;'><div class='metric-label'>📊 Promedio Win/ID</div><div class='metric-value'>{form_num(avg_w)}</div><div class='metric-sub'>Rendimiento medio por unidad física.</div></div>", unsafe_allow_html=True)

            with tab2:
                st.subheader("Análisis de Tráfico y Popularidad")
                if not df_f.empty:
                    col_an = 'modelo' if f_marca else 'marca'
                    
                    # Cálculos Coin In
                    lider_c = df_f.groupby(col_an)['coin_in'].sum().idxmax()
                    share_c = (df_f.groupby(col_an)['coin_in'].sum().max() / ct * 100) if ct > 0 else 0
                    avg_c_sala = ct / df_f['asset_Id'].nunique() if not df_f.empty else 0
                    
                    t1, t2 = st.columns(2)
                    with t1:
                        st.markdown(f"""
                            <div class='metric-card' style='border-left:5px solid #6200EE;'>
                                <div class='metric-label'>🔥 Imán de Tráfico (Coin In)</div>
                                <div class='metric-value'>{lider_c}</div>
                                <div class='metric-sub'>Mueve el <b>{share_c:.1f}%</b> de todo el dinero ingresado {contexto}.</div>
                            </div>
                        """, unsafe_allow_html=True)
                    with t2:
                        st.markdown(f"""
                            <div class='metric-card' style='border-left:5px solid #BB86FC;'>
                                <div class='metric-label'>📈 Tráfico Promedio por ID</div>
                                <div class='metric-value'>{form_num(avg_c_sala)}</div>
                                <div class='metric-sub'>Volumen de apuestas esperado por máquina.</div>
                            </div>
                        """, unsafe_allow_html=True)
                    
                    # Gráfico de Tráfico
                    df_tráfico = df_f.groupby(col_an)['coin_in'].sum().nlargest(10).reset_index()
                    st.plotly_chart(px.bar(df_tráfico, x='coin_in', y=col_an, orientation='h', 
                                          title=f"Top 10 {col_an.capitalize()} por Volumen de Coin In",
                                          template="plotly_dark", color_discrete_sequence=['#6200EE']), use_container_width=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Credenciales incorrectas')