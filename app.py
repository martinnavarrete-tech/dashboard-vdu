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
    """Formatea números al estilo contable: $ 1.250.000"""
    try:
        return f"$ {valor:,.0f}".replace(',', '.')
    except:
        return "$ 0"

# IDs de los Libros de Google Sheets proporcionados
ID_CONFIGURACION = "1W_68ToMyy_nu1oPH7ePFj74_vc1op5bGiFoP4KtaY0I"
ID_DATOS_2026 = "1ZYn6foApzeEeKg_qKzW9faQFjBPXHoc8ffB_CeZ3f_s"
ID_DATOS_2025 = "1aAl_PX1wpBWgTu9bLc81Wn57jSyt8Kqfwm4B4Fsa1W0"

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
        # Limpiar nombres de columnas en usuarios para evitar errores de llave
        df_u.columns = [str(c).strip() for c in df_u.columns]
        
        # 2. Función para extraer específicamente la hoja "Cubo"
        def get_cubo_data(book_id):
            try:
                sheet = client.open_by_key(book_id).worksheet("Cubo")
                data = sheet.get_all_values()
                if not data:
                    return pd.DataFrame()
                
                df = pd.DataFrame(data[1:], columns=data[0])
                # Limpiar nombres de columnas (espacios en blanco)
                df.columns = [str(c).strip() for c in df.columns]
                
                # Mapeo de seguridad para nombres de columnas asset_Id
                mapeo = {'asset_id': 'asset_Id', 'Asset ID': 'asset_Id', 'Asset id': 'asset_Id'}
                df = df.rename(columns=mapeo)
                
                # Limpiar columnas sin nombre o vacías
                df = df.loc[:, ~df.columns.str.contains('^$|Unnamed', case=False, na=False)]
                # Convertir fechas (formato esperado DD/MM/YYYY)
                df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=True, errors='coerce').dt.date
                return df.dropna(subset=['fecha'])
            except Exception as e:
                st.warning(f"Aviso: No se encontró la hoja 'Cubo' en el libro {book_id}. Error: {e}")
                return pd.DataFrame()

        # 3. Cargar y Unificar 2025 y 2026
        df_2025 = get_cubo_data(ID_DATOS_2025)
        df_2026 = get_cubo_data(ID_DATOS_2026)
        
        df_s = pd.concat([df_2025, df_2026], ignore_index=True)
        
        if df_s.empty:
            return pd.DataFrame(), df_u

        # 4. Limpieza de valores numéricos
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
        st.error(f"Error crítico de sincronización: {e}")
        return None, None

df_slots, df_users = load_all_data()

# --- 3. INTERFAZ PRINCIPAL ---
if df_users is not None:
    # Preparar credenciales asegurando que los nombres de columna coincidan con el Sheet
    try:
        credentials = {"usernames": {str(u).lower(): {"name": r['nombre'], "password": str(r['password']), "role": r['rol']} 
                       for u, r in df_users.set_index('usuario').iterrows()}}
    except KeyError as e:
        st.error(f"Error: No se encuentra la columna {e} en la hoja de Usuarios.")
        st.stop()

    authenticator = stauth.Authenticate(credentials, "vdu_app", "auth_key", 30)
    
    # Login en la página principal
    authenticator.login(location='main')

    if st.session_state.get("authentication_status"):
        # Captura segura del username para evitar KeyError
        curr_user = st.session_state.get('username')
        if curr_user:
            curr_user = curr_user.lower()
            user_role = credentials["usernames"][curr_user]["role"]
        else:
            user_role = "Usuario"

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
                with st.container(border=True):
                    r1, r2 = st.columns([1, 3])
                    # Verificación de rango de fechas
                    safe_min = df_slots['fecha'].min()
                    safe_max = df_slots['fecha'].max()
                    f_rango = r1.date_input("📅 Ventana Temporal", [safe_min, safe_max])
                    
                    c1, c2, c3, c4 = st.columns(4)
                    f_id = c1.multiselect("🆔 Asset ID", sorted(df_slots['asset_Id'].unique())) if 'asset_Id' in df_slots.columns else []
                    f_marca = c2.multiselect("🎰 Marca", sorted(df_slots['marca'].unique())) if 'marca' in df_slots.columns else []
                    f_modelo = c3.multiselect("📦 Modelo", sorted(df_slots['modelo'].unique())) if 'modelo' in df_slots.columns else []
                    f_juego = c4.multiselect("🎮 Juego", sorted(df_slots['juego'].unique())) if 'juego' in df_slots.columns else []
                
                df_f = df_slots.copy()
                if isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
                    df_f = df_f[(df_f['fecha'] >= f_rango[0]) & (df_f['fecha'] <= f_rango[1])]
                
                if f_id: df_f = df_f[df_f['asset_Id'].isin(f_id)]
                if f_marca: df_f = df_f[df_f['marca'].isin(f_marca)]
                if f_modelo: df_f = df_f[df_f['modelo'].isin(f_modelo)]
                if f_juego: df_f = df_f[df_f['juego'].isin(f_juego)]

                # Cálculos de KPIs
                wt = df_f['win'].sum() if 'win' in df_f.columns else 0
                ct = df_f['coin_in'].sum() if 'coin_in' in df_f.columns else 0
                ht = (wt/ct*100) if ct > 0 else 0
                
                k1, k2, k3 = st.columns(3)
                with k1: st.markdown(f"<div class='main-kpi-label'>NET WIN TOTAL</div><div class='main-kpi-val'>{form_num(wt)}</div>", unsafe_allow_html=True)
                with k2: st.markdown(f"<div class='main-kpi-label'>COIN IN</div><div class='main-kpi-val'>{form_num(ct)}</div>", unsafe_allow_html=True)
                with k3: st.markdown(f"<div class='main-kpi-label'>HOLD REAL %</div><div class='main-kpi-val'>{ht:.2f}%</div>", unsafe_allow_html=True)

                # Gráfico de Evolución
                df_daily = df_f.groupby('fecha')[['win', 'coin_in']].sum().reset_index()
                st.plotly_chart(px.area(df_daily, x='fecha', y=['win', 'coin_in'], 
                                        template="plotly_dark", 
                                        color_discrete_sequence=['#00D1FF', '#FF4B4B'],
                                        title="Evolución Win vs Coin In"), use_container_width=True)
                
                # Desglose Visual (Marca y Modelo)
                col_a, col_b = st.columns(2)
                with col_a:
                    if 'marca' in df_f.columns:
                        df_m = df_f.groupby('marca')['win'].sum().reset_index()
                        st.plotly_chart(px.pie(df_m, names='marca', values='win', title="Distribución Win por Marca", hole=0.4, template="plotly_dark"), use_container_width=True)
                with col_b:
                    if 'modelo' in df_f.columns:
                        df_mod = df_f.groupby('modelo')['win'].sum().reset_index().sort_values('win', ascending=False).head(10)
                        st.plotly_chart(px.bar(df_mod, x='modelo', y='win', title="Top 10 Modelos por Win", template="plotly_dark"), use_container_width=True)
            else:
                st.error("Error: No hay datos disponibles para procesar. Verifique las hojas 'Cubo'.")

        elif nav == "🔄 Analista Comparativo":
            st.title("⚖️ Diagnóstico Comparativo")
            st.info("Compare variaciones de rendimiento entre periodos de tiempo.")
            
            if not df_slots.empty:
                with st.container(border=True):
                    col1, col2 = st.columns(2)
                    max_f = df_slots['fecha'].max()
                    r_actual = col1.date_input("Periodo A (Actual)", [max_f - timedelta(days=7), max_f])
                    r_previo = col2.date_input("Periodo B (Anterior)", [max_f - timedelta(days=15), max_f - timedelta(days=8)])
                
                if len(r_actual) == 2 and len(r_previo) == 2:
                    df_a = df_slots[(df_slots['fecha'] >= r_actual[0]) & (df_slots['fecha'] <= r_actual[1])]
                    df_b = df_slots[(df_slots['fecha'] >= r_previo[0]) & (df_slots['fecha'] <= r_previo[1])]
                    
                    wa, wb = df_a['win'].sum(), df_b['win'].sum()
                    ca, cb = df_a['coin_in'].sum(), df_b['coin_in'].sum()
                    
                    diff = wa - wb
                    pct = (diff / wb * 100) if wb != 0 else 0
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Variación Win", form_num(diff), f"{pct:.2f}%")
                    m2.metric("Variación Coin In", form_num(ca - cb), f"{((ca-cb)/cb*100 if cb!=0 else 0):.2f}%")
                    
                    st.divider()
                    st.subheader("Diferencia Detallada por Activo (Asset)")
                    if 'asset_Id' in df_a.columns:
                        df_diff_a = df_a.groupby('asset_Id')['win'].sum().reset_index()
                        df_diff_b = df_b.groupby('asset_Id')['win'].sum().reset_index()
                        df_merged = pd.merge(df_diff_a, df_diff_b, on='asset_Id', suffixes=('_Actual', '_Anterior'), how='outer').fillna(0)
                        df_merged['Diferencia'] = df_merged['win_Actual'] - df_merged['win_Anterior']
                        st.dataframe(df_merged.sort_values('Diferencia', ascending=False), use_container_width=True)

        elif nav == "👤 Gestión Usuarios":
            st.title("👤 Administración")
            st.dataframe(df_users[['nombre', 'usuario', 'rol']], use_container_width=True)

    elif st.session_state.get("authentication_status") is False:
        st.error('Usuario o Contraseña incorrectos')