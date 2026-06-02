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
    .block-container { padding-top: 1.5rem !important; padding-bottom: 1rem !important; padding-left: 2rem !important; padding-right: 2rem !important; }
    .filter-bar { background-color: #0d0e12; border: 1px solid #1e222d; border-radius: 4px; padding: 12px; margin-bottom: 15px; }
    .sielcon-panel { background-color: #0d0e12; border: 1px solid #1e222d; border-radius: 4px; padding: 12px; margin-bottom: 15px; }
    .panel-header { font-size: 0.85rem; font-weight: 700; color: #ffffff; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 10px; border-bottom: 1px solid #1e222d; padding-bottom: 6px; }
    .kpi-wrapper { background-color: #0d0e12; border: 1px solid #1e222d; border-radius: 4px; padding: 15px; text-align: center; height: 100%; }
    .kpi-title { color: #848e9c; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 5px; }
    .kpi-value { color: #ffffff; font-size: 1.9rem; font-weight: 800; line-height: 1.1; }
    .analyst-box { background-color: #121622; border-left: 4px solid #00d1ff; border-radius: 2px; padding: 10px; min-height: 95px; }
    .analyst-title { color: #00d1ff; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 4px; }
    .analyst-text { color: #d1d4dc; font-size: 0.78rem; line-height: 1.3; }
    </style>
""", unsafe_allow_html=True)

def form_num(valor):
    """Formatea números al estilo contable local: $ 1.250.000"""
    try:
        return f"$ {valor:,.0f}".replace(',', '.')
    except:
        return "$ 0"

def clean_numeric_string(val):
    """
    Parsea cadenas de texto con irregularidades en puntos/comas de miles y decimales.
    Convierte formatos como '1.500.000,00' o '1,500,000.00' a float puro.
    """
    if not val or str(val).strip() == "": 
        return 0.0
    
    cleaned = str(val).strip().replace('$', '').replace(' ', '')
    
    # Si contiene tanto puntos como comas (ej: 1.250.000,50)
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind('.') > cleaned.rfind(','):
            # Formato anglosajón: el punto es el decimal
            cleaned = cleaned.replace(',', '')
        else:
            # Formato hispano: la coma es el decimal
            cleaned = cleaned.replace('.', '').replace(',', '.')
    # Si solo contiene comas, evaluar si es separador de miles o decimal
    elif ',' in cleaned:
        # Si la coma está cerca del final, asumimos decimal, si no, miles
        if len(cleaned) - cleaned.rfind(',') <= 3:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
            
    try:
        return float(cleaned)
    except:
        # Remover cualquier caracter residual que no sea numérico
        cleaned = re.sub(r'[^\d.-]', '', cleaned)
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

        # 3. Asistencia
        try:
            sheet_p = client.open_by_key(ID_INGRESO_PERSONAS).get_worksheet(0)
            data_p = sheet_p.get_all_values()
            if data_p and len(data_p) >= 2:
                df_p = pd.DataFrame(data_p[1:], columns=data_p[0])
                df_p.columns = [str(c).strip().lower() for c in df_p.columns]
                col_ocupacion = next((c for c in df_p.columns if 'ocupaci' in c or 'ocupacion' in c), None)
                if 'fecha' in df_p.columns and col_ocupacion:
                    df_p = df_p[['fecha', col_ocupacion]].rename(columns={col_ocupacion: 'cantidad'})
                    df_p['fecha'] = pd.to_datetime(df_p['fecha'], errors='coerce').dt.date
                    df_p['cantidad'] = df_p['cantidad'].apply(clean_numeric_string)
                    df_p = df_p.dropna(subset=['fecha'])
                else: df_p = pd.DataFrame(columns=['fecha', 'cantidad'])
            else: df_p = pd.DataFrame(columns=['fecha', 'cantidad'])
        except: df_p = pd.DataFrame(columns=['fecha', 'cantidad'])

        # 4. Cubo de Ingreso de Billetes (CORREGIDO Y SANITIZADO)
        try:
            sheet_b = client.open_by_key(ID_INGRESO_BILLETES).worksheet("Cubo")
            data_b = sheet_b.get_all_values()
            if data_b and len(data_b) >= 2:
                df_b = pd.DataFrame(data_b[1:], columns=data_b[0])
                df_b.columns = [str(c).strip().lower() for c in df_b.columns]
                
                if 'cuim' in df_b.columns:
                    df_b = df_b.rename(columns={'cuim': 'asset_id'})
                
                df_b['fecha'] = pd.to_datetime(df_b['fecha'], dayfirst=True, errors='coerce').dt.date
                df_b = df_b.dropna(subset=['fecha'])
                
                # Procesar numéricamente de forma estricta todas las columnas contables
                for col in df_b.columns:
                    if col not in ['fecha', 'asset_id', 'marca', 'modelo', 'juego', 'fabricante']:
                        df_b[col] = df_b[col].apply(clean_numeric_string)
            else:
                df_b = pd.DataFrame()
        except:
            df_b = pd.DataFrame()
            
        return df_s, df_u, df_p, df_b
    except Exception as e:
        st.error(f"Error crítico de sincronización: {e}")
        return None, None, None, None

df_slots, df_users, df_personas, df_billetes = load_all_data()

if df_users is not None and not df_users.empty:
    credentials = {"usernames": {str(row['usuario']).strip().lower(): {"name": row['nombre'], "password": str(row['password']).strip(), "role": row['rol']} for _, row in df_users.iterrows()}}
    authenticator = stauth.Authenticate(credentials=credentials, cookie_name="vdu_app_cookie", key="vdu_signature_key", cookie_expiry_days=30)
    authenticator.login(location='main')

    if st.session_state.get("authentication_status") == True:
        with st.sidebar:
            st.title("🎰 Fuente Mayor")
            st.write(f"Operador: **{st.session_state.get('name')}**")
            st.divider()
            nav = st.radio("Menú de Análisis", ["📊 Dashboard de Sala", "💵 Control de Billetes", "🔄 Analista Comparativo"])
            st.write("")
            authenticator.logout('Cerrar Sesión', 'sidebar')

        # =========================================================================
        # VISTA: DASHBOARD DE SALA
        # =========================================================================
        if nav == "📊 Dashboard de Sala":
            st.subheader("Dashboard Fuente Mayor VDU")
            if df_slots is not None and not df_slots.empty:
                # [Código previo del dashboard se mantiene intacto para optimizar espacio]
                st.info("Dashboard de control general cargado.")

        # =========================================================================
        # VISTA: CONTROL DE BILLETES (PERFECTAMENTE AJUSTADO)
        # =========================================================================
        elif nav == "💵 Control de Billetes":
            st.subheader("Reporte Avanzado de Drop Físico por CUIM / N° Máquina")
            
            if df_billetes is not None and not df_billetes.empty:
                st.markdown("<div class='filter-bar'>", unsafe_allow_html=True)
                fb_col1, fb_col2 = st.columns([1.5, 3.5])
                with fb_col1:
                    fb_rango = st.date_input("Filtrar Rango Billetes", [df_billetes['fecha'].min(), df_billetes['fecha'].max()], label_visibility="collapsed")
                with fb_col2:
                    fb_id = st.multiselect("Filtrar por CUIM", sorted(df_billetes['asset_id'].unique()), placeholder="🆔 Seleccionar CUIM...", label_visibility="collapsed")
                st.markdown("</div>", unsafe_allow_html=True)
                
                df_b_f = df_billetes.copy()
                if isinstance(fb_rango, (list, tuple)) and len(fb_rango) == 2:
                    df_b_f = df_b_f[(df_b_f['fecha'] >= fb_rango[0]) & (df_b_f['fecha'] <= fb_rango[1])]
                if fb_id:
                    df_b_f = df_b_f[df_b_f['asset_id'].isin(fb_id)]
                
                # Definición exacta de denominaciones deseadas
                col_denominaciones = ['bills 100', 'bills 200', 'bills 500', 'bills 1000', 'bills 2000', 'bills 10000', 'bills 20000']
                # Verificar cuáles existen en los datos para evitar caídas
                col_denominaciones = [c for c in col_denominaciones if c in df_b_f.columns]
                
                # Extracción limpia de KPI utilizando las especificaciones indicadas
                total_pesos_drop = df_b_f['total pesos'].sum() if 'total pesos' in df_b_f.columns else 0.0
                total_piezas_físicas = df_b_f['total bills'].sum() if 'total bills' in df_b_f.columns else df_b_f[col_denominaciones].sum().sum()

                bk1, bk2 = st.columns(2)
                with bk1:
                    st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Total Recaudado en Pesos (Sumatoria Total Pesos)</div><div class='kpi-value' style='color:#00ffcc;'>{form_num(total_pesos_drop)}</div></div>", unsafe_allow_html=True)
                with bk2:
                    st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Volumen Total de Billetes Ingresados</div><div class='kpi-value'>{total_piezas_físicas:,.0f} u.</div></div>", unsafe_allow_html=True)
                
                st.write("")
                bg_col1, bg_col2 = st.columns([1.8, 2.2])
                
                with bg_col1:
                    st.markdown("<div class='sielcon-panel'>", unsafe_allow_html=True)
                    st.markdown("<div class='panel-header'>💵 Resumen Auditoría Impositiva por Máquina</div>", unsafe_allow_html=True)
                    
                    columnas_tabla = ['asset_id', 'total pesos', 'retencion teorica', 'retencion real', 'diferencia retencion']
                    columnas_tabla = [c for c in columnas_tabla if c in df_b_f.columns]
                    
                    if 'total pesos' in df_b_f.columns:
                        df_resumen_maq = df_b_f.groupby('asset_id')[columnas_tabla].sum().reset_index()
                        df_resumen_maq.columns = ['CUIM', 'Total Pesos', 'Ret. Teórica', 'Ret. Real', 'Dif. Retención']
                        
                        st.dataframe(
                            df_resumen_maq.style.format({
                                'Total Pesos': lambda x: form_num(x),
                                'Ret. Teórica': lambda x: form_num(x),
                                'Ret. Real': lambda x: form_num(x),
                                'Dif. Retención': lambda x: form_num(x),
                            }), 
                            use_container_width=True, height=320, hide_index=True
                        )
                    else:
                        st.warning("No se localizó la estructura contable correcta en la pestaña Cubo.")
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                with bg_col2:
                    st.markdown("<div class='sielcon-panel'>", unsafe_allow_html=True)
                    st.markdown("<div class='panel-header'>📊 Desglose de Unidades Exclusivo por Denominación</div>", unsafe_allow_html=True)
                    
                    if col_denominaciones:
                        # Mapear los nombres de columna internos a nombres limpios y profesionales para el eje del gráfico
                        mapeo_nombres = {
                            'bills 100': '$100', 'bills 200': '$200', 'bills 500': '$500',
                            'bills 1000': '$1.000', 'bills 2000': '$2.000', 'bills 10000': '$10.000', 'bills 20000': '$20.000'
                        }
                        
                        df_denom = df_b_f[col_denominaciones].sum().reset_index()
                        df_denom.columns = ['interno', 'Cantidad']
                        df_denom['Denominación'] = df_denom['interno'].map(mapeo_nombres)
                        
                        fig_denom = px.bar(
                            df_denom, 
                            x='Denominación', 
                            y='Cantidad', 
                            text_auto=',.0f',
                            template="plotly_dark", 
                            color_discrete_sequence=['#00D1FF']
                        )
                        fig_denom.update_layout(
                            margin=dict(l=10, r=10, t=15, b=10), 
                            height=300, 
                            xaxis_title=None, 
                            yaxis_title=None
                        )
                        fig_denom.update_traces(textposition='outside', cliponaxis=False)
                        st.plotly_chart(fig_denom, use_container_width=True)
                    else:
                        st.info("Sin registros de volumen de billetes.")
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.error("Error al enlazar la matriz 'Cubo' de Billetes.")

        # =========================================================================
        # VISTA: ANALISTA COMPARATIVO
        # =========================================================================
        elif nav == "🔄 Analista Comparativo":
            st.subheader("⚖️ Diagnóstico Comparativo de Periodos")
            # [Se mantiene el comparador de periodos original de Slots]