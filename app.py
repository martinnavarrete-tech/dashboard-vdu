import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit_authenticator as stauth
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re
from datetime import datetime, timedelta

# =============================================================================
# 1. CONFIGURACIÓN Y ESTILOS
# =============================================================================
st.set_page_config(page_title="Dashboard VDU", layout="wide", page_icon="🎰")

st.markdown("""
    <style>
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 1rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
    .filter-bar {
        background-color: #0d0e12;
        border: 1px solid #1e222d;
        border-radius: 4px;
        padding: 10px 14px;
        margin-bottom: 12px;
    }
    .sielcon-panel {
        background-color: #0d0e12;
        border: 1px solid #1e222d;
        border-radius: 4px;
        padding: 12px;
        margin-bottom: 12px;
    }
    .panel-header {
        font-size: 0.82rem;
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
        padding: 14px;
        text-align: center;
        height: 100%;
    }
    .kpi-title {
        color: #848e9c;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 5px;
    }
    .kpi-value {
        color: #ffffff;
        font-size: 1.65rem;
        font-weight: 800;
        line-height: 1.1;
    }
    .kpi-subtext {
        color: #ff9f43;
        font-size: 0.72rem;
        font-weight: bold;
        margin-top: 5px;
    }
    .analyst-box {
        background-color: #121622;
        border-left: 4px solid #00d1ff;
        border-radius: 2px;
        padding: 10px;
        min-height: 90px;
    }
    .analyst-title {
        color: #00d1ff;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        margin-bottom: 4px;
    }
    .analyst-text {
        color: #d1d4dc;
        font-size: 0.76rem;
        line-height: 1.35;
    }
    .alert-crit { border-left-color: #ef5350 !important; }
    </style>
""", unsafe_allow_html=True)

# =============================================================================
# 2. UTILIDADES DE CONVERSIÓN (CORREGIDAS PARA TEXTO SIN FORMATO)
# =============================================================================

def form_num(valor):
    """Formatea números al estilo contable local: $ 1.250.000"""
    try:
        if pd.isna(valor):
            return "$ 0"
        return f"$ {valor:,.0f}".replace(",", ".")
    except:
        return "$ 0"

def clean_col_vectorized(series: pd.Series) -> pd.Series:
    """
    Parsea de forma segura strings de 'Texto sin formato' de Google Sheets.
    Elimina signos $, espacios y maneja puntos como separadores de miles y comas como decimales.
    """
    s = series.astype(str).str.strip().str.replace(r"[$\s]", "", regex=True)
    s = s.str.replace(r"\.", "", regex=True).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce").fillna(0.0)

def df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Convierte un DataFrame a CSV con BOM para compatibilidad directa con Excel."""
    return df.to_csv(index=False).encode("utf-8-sig")

# =============================================================================
# 3. IDs DE GOOGLE SHEETS
# =============================================================================
ID_CONFIGURACION   = "1W_68ToMyy_nu1oPH7ePFj74_vc1op5bGiFoP4KtaY0I"
ID_DATOS_2026      = "1ZYn6foApzeEeKg_qKzW9faQFjBPXHoc8ffB_CeZ3f_s"
ID_DATOS_2025      = "1aAl_PX1wpBWgTu9bLc81Wn57jSyt8Kqfwm4B4Fsa1W0"
ID_INGRESO_PERSONAS = "1H-j4-gudnexcxnbk0oFMHBJNovDOyWOIWZCLaprEdYw"
ID_INGRESO_BILLETES = "17c6P1pY21SC_xFoLulC7FgvUBz8zj8xz-61gsC-vsaI"

# =============================================================================
# 4. MOTOR DE DATOS EN CACHÉ
# =============================================================================

@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)
def load_historical_data():
    try:
        client = get_gspread_client()
        return _get_cubo_data(client, ID_DATOS_2025)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_current_data():
    try:
        client = get_gspread_client()
        df_2026 = _get_cubo_data(client, ID_DATOS_2026)

        # Asistencia
        df_p = pd.DataFrame(columns=["fecha", "cantidad"])
        try:
            sheet_p = client.open_by_key(ID_INGRESO_PERSONAS).get_worksheet(0)
            data_p = sheet_p.get_all_values()
            if data_p and len(data_p) >= 2:
                df_p = pd.DataFrame(data_p[1:], columns=data_p[0])
                df_p.columns = [str(c).strip().lower() for c in df_p.columns]
                col_oc = next((c for c in df_p.columns if "ocupaci" in c or "ocupacion" in c), None)
                if "fecha" in df_p.columns and col_oc:
                    df_p = df_p[["fecha", col_oc]].rename(columns={col_oc: "cantidad"})
                    df_p["fecha"] = pd.to_datetime(df_p["fecha"], errors="coerce").dt.date
                    df_p["cantidad"] = clean_col_vectorized(df_p["cantidad"])
                    df_p = df_p.dropna(subset=["fecha"])
        except:
            pass

        # Billetes
        df_b = pd.DataFrame()
        try:
            sheet_b = client.open_by_key(ID_INGRESO_BILLETES).worksheet("Cubo")
            data_b = sheet_b.get_all_values()
            if data_b and len(data_b) >= 2:
                df_b = pd.DataFrame(data_b[1:], columns=data_b[0])
                df_b.columns = [str(c).strip().lower().replace("\n", " ") for c in df_b.columns]
                col_maq = next((c for c in df_b.columns if "cuim" in c or "asset" in c or "maq" in c), df_b.columns[0])
                df_b = df_b.rename(columns={col_maq: "asset_id"})
                df_b["fecha"] = pd.to_datetime(df_b["fecha"], dayfirst=True, errors="coerce").dt.date
                df_b = df_b.dropna(subset=["fecha"])
                non_numeric_cols = {"fecha", "asset_id", "marca", "modelo", "juego", "fabricante"}
                for col in df_b.columns:
                    if col not in non_numeric_cols:
                        df_b[col] = clean_col_vectorized(df_b[col])
        except:
            pass

        return df_2026, df_p, df_b
    except:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=600)
def load_users():
    try:
        client = get_gspread_client()
        sheet_u = client.open_by_key(ID_CONFIGURACION).worksheet("Usuarios")
        df_u = pd.DataFrame(sheet_u.get_all_records())
        df_u.columns = [str(c).strip() for c in df_u.columns]
        return df_u
    except:
        return pd.DataFrame()

def _get_cubo_data(client, book_id: str) -> pd.DataFrame:
    try:
        sheet = client.open_by_key(book_id).worksheet("Cubo")
        data = sheet.get_all_values()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = [str(c).strip().lower() for c in df.columns]
        if "cuim" in df.columns:
            df = df.rename(columns={"cuim": "asset_id"})
        df = df.loc[:, ~df.columns.str.contains(r"^$|Unnamed", case=False, na=False)]
        df["fecha"] = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce").dt.date
        df = df.dropna(subset=["fecha"])
        for col in ["coin_in", "win", "jackpot"]:
            if col in df.columns:
                df[col] = clean_col_vectorized(df[col])
        return df
    except:
        return pd.DataFrame()

# =============================================================================
# 5. CARGA INICIAL
# =============================================================================
df_users = load_users()
df_2025 = load_historical_data()
df_2026, df_personas, df_billetes = load_current_data()

df_slots = pd.concat([df_2025, df_2026], ignore_index=True) if not df_2025.empty or not df_2026.empty else pd.DataFrame()

# =============================================================================
# 6. AUTENTICACIÓN
# =============================================================================
if df_users is not None and not df_users.empty:

    def _prepare_password(raw: str) -> str:
        if str(raw).startswith("$2b$") or str(raw).startswith("$2a$"):
            return raw
        import bcrypt
        return bcrypt.hashpw(str(raw).encode(), bcrypt.gensalt()).decode()

    credentials = {
        "usernames": {
            str(row["usuario"]).strip().lower(): {
                "name": row["nombre"],
                "password": _prepare_password(str(row["password"]).strip()),
                "role": row.get("rol", "operador"),
            }
            for _, row in df_users.iterrows()
        }
    }

    authenticator = stauth.Authenticate(
        credentials=credentials, cookie_name="vdu_app_cookie", key="vdu_signature_key", cookie_expiry_days=30
    )
    authenticator.login(location="main")

    auth_status = st.session_state.get("authentication_status")
    current_role = credentials["usernames"].get(str(st.session_state.get("username", "")).lower(), {}).get("role", "operador")

    if auth_status is False:
        st.error("Usuario o contraseña incorrectos.")
        st.stop()
    if auth_status is None:
        st.warning("Ingresá tus credenciales para continuar.")
        st.stop()

    with st.sidebar:
        st.title("🎰 Fuente Mayor")
        st.write(f"Operador: **{st.session_state.get('name')}**")
        st.caption(f"Rol: `{current_role}`")
        st.divider()

        menu_options = ["📊 Dashboard de Sala", "💵 Control de Billetes", "🔄 Analista Comparativo"]
        if current_role == "admin":
            menu_options.append("👤 Gestión Usuarios")

        nav = st.radio("Menú de Análisis", menu_options)
        authenticator.logout("Cerrar Sesión", "sidebar")

    safe_min = df_slots["fecha"].min() if not df_slots.empty else datetime.now().date()
    safe_max = df_slots["fecha"].max() if not df_slots.empty else datetime.now().date()

    # =========================================================================
    # VISTA 1: DASHBOARD DE SALA
    # =========================================================================
    if nav == "📊 Dashboard de Sala":
        st.subheader("Dashboard Fuente Mayor VDU")

        if df_slots is None or df_slots.empty:
            st.warning("No hay datos de slots disponibles.")
            st.stop()

        # --- FILTROS DE SALA ---
        st.markdown("<div class='filter-bar'>", unsafe_allow_html=True)
        fc1, fc2, fc3, fc4, fc5 = st.columns([1.4, 1, 1, 1, 1])

        with fc1: f_rango = st.date_input("Período", [safe_min, safe_max], label_visibility="collapsed")
        with fc2: f_id = st.multiselect("CUIM", sorted(df_slots["asset_id"].dropna().unique()), placeholder="🆔 CUIM / Máquina", label_visibility="collapsed")
        with fc3: f_marca = st.multiselect("Marca", sorted(df_slots["marca"].dropna().unique()) if "marca" in df_slots.columns else [], placeholder="🎰 Marca", label_visibility="collapsed")
        
        df_para_modelo = df_slots.copy()
        if f_marca: df_para_modelo = df_para_modelo[df_para_modelo["marca"].isin(f_marca)]
        with fc4: f_modelo = st.multiselect("Modelo", sorted(df_para_modelo["modelo"].dropna().unique()) if "modelo" in df_para_modelo.columns else [], placeholder="📦 Modelo", label_visibility="collapsed")

        df_para_juego = df_para_modelo.copy()
        if f_modelo: df_para_juego = df_para_juego[df_para_juego["modelo"].isin(f_modelo)]
        with fc5: f_juego = st.multiselect("Juego", sorted(df_para_juego["juego"].dropna().unique()) if "juego" in df_para_juego.columns else [], placeholder="🎮 Juego", label_visibility="collapsed")
        st.markdown("</div>", unsafe_allow_html=True)

        # --- FILTRADO DE DATAFRAMES ---
        df_f = df_slots.copy()
        if isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
            df_f = df_f.loc[(df_f["fecha"] >= f_rango[0]) & (df_f["fecha"] <= f_rango[1])]
        if f_id: df_f = df_f.loc[df_f["asset_id"].isin(f_id)]
        if f_marca: df_f = df_f.loc[df_f["marca"].isin(f_marca)]
        if f_modelo: df_f = df_f.loc[df_f["modelo"].isin(f_modelo)]
        if f_juego: df_f = df_f.loc[df_f["juego"].isin(f_juego)]

        df_p_f = df_personas.copy() if df_personas is not None else pd.DataFrame()
        if not df_p_f.empty and isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
            df_p_f = df_p_f.loc[(df_p_f["fecha"] >= f_rango[0]) & (df_p_f["fecha"] <= f_rango[1])]

        drop_periodo_pesos = 0.0
        if df_billetes is not None and not df_billetes.empty and "total pesos" in df_billetes.columns:
            df_b_f = df_billetes.copy()
            if isinstance(f_rango, (list, tuple)) and len(f_rango) == 2:
                df_b_f = df_b_f.loc[(df_b_f["fecha"] >= f_rango[0]) & (df_b_f["fecha"] <= f_rango[1])]
            if f_id:
                df_b_f = df_b_f.loc[df_b_f["asset_id"].isin(f_id)]
            drop_periodo_pesos = df_b_f["total pesos"].sum()

        # --- CÁLCULOS KPI ---
        wt = df_f["win"].sum()
        ct = df_f["coin_in"].sum()
        ht = (wt / ct * 100) if ct > 0 else 0
        asistencia = df_p_f["cantidad"].sum() if not df_p_f.empty else 0
        win_persona = (wt / asistencia) if asistencia > 0 else 0
        n_maquinas = df_f["asset_id"].nunique()
        eficiencia_media = wt / n_maquinas if n_maquinas > 0 else 0

        # RENDER KPIs
        k1, k2, k3, k4, k5 = st.columns(5)
        with k1: st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Net Win Total</div><div class='kpi-value'>{form_num(wt)}</div></div>", unsafe_allow_html=True)
        with k2: st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Coin In</div><div class='kpi-value'>{form_num(ct)}</div></div>", unsafe_allow_html=True)
        with k3:
            hold_color = "#00ffcc" if 6.5 <= ht <= 8.5 else "#ef5350"
            st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Hold Real %</div><div class='kpi-value' style='color:{hold_color};'>{ht:.2f}%</div><div class='kpi-subtext'>Target: 6.5 – 8.5%</div></div>", unsafe_allow_html=True)
        with k4: st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>💵 Drop Físico (Billetes)</div><div class='kpi-value' style='color:#00d1ff;'>{form_num(drop_periodo_pesos)}</div></div>", unsafe_allow_html=True)
        with k5: st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Ocupación / Tráfico</div><div class='kpi-value' style='color:#ff9f43;'>{asistencia:,.0f}</div><div class='kpi-subtext'>EFF: {form_num(win_persona)} x PAX</div></div>", unsafe_allow_html=True)

        st.write("")

        # --- CUADROS DEL ANALISTA ---
        st.markdown("<div class='sielcon-panel'>", unsafe_allow_html=True)
        st.markdown("<div class='panel-header'>🤖 Monitoreo Algorítmico de Sala</div>", unsafe_allow_html=True)
        a1, a2, a3, a4 = st.columns(4)
        with a1:
            top_m = df_f.groupby("marca")["win"].sum().idxmax() if not df_f.empty and "marca" in df_f.columns else "N/A"
            st.markdown(f"<div class='analyst-box'><div class='analyst-title'>Líder del Mercado</div><div class='analyst-text'><b>{top_m}</b> lidera el profit de sala general.</div></div>", unsafe_allow_html=True)
        with a2:
            avg_hold = df_f.groupby("asset_id").apply(lambda x: (x["win"].sum() / x["coin_in"].sum() * 100) if x["coin_in"].sum() > 0 else 0) if not df_f.empty else pd.Series(dtype=float)
            outliers = int((avg_hold > 15).sum())
            border_color = "#ef5350" if outliers > 0 else "#00d1ff"
            st.markdown(f"<div class='analyst-box alert-crit' style='border-left-color:{border_color};'><div class='analyst-title' style='color:{border_color};'>Alerta de Hold</div><div class='analyst-text'><b>{outliers} terminal{'es' if outliers != 1 else ''}</b> superan el 15% de Hold Real.</div></div>", unsafe_allow_html=True)
        with a3:
            jackpot_total = df_f["jackpot"].sum() if "jackpot" in df_f.columns else 0
            jackpot_count = int((df_f["jackpot"] > 0).sum()) if "jackpot" in df_f.columns else 0
            st.markdown(f"<div class='analyst-box' style='border-left-color:#ff9f43;'><div class='analyst-title' style='color:#ff9f43;'>Acumulado Jackpots</div><div class='analyst-text'>Se entregaron <b>{form_num(jackpot_total)}</b> en <b>{jackpot_count}</b> premios mayores.</div></div>", unsafe_allow_html=True)
        with a4: st.markdown(f"<div class='analyst-box'><div class='analyst-title'>Eficiencia Media</div><div class='analyst-text'>Rendimiento medio por terminal: <b>{form_num(eficiencia_media)}</b> ({n_maquinas} activas).</div></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # --- SECCIÓN GRÁFICOS ---
        g1, g2 = st.columns(2)
        with g1:
            st.caption("📈 Evolución del Rendimiento Diario de Sala (Slots)")
            if not df_f.empty:
                df_time = df_f.groupby("fecha")[["win", "coin_in"]].sum().reset_index()
                fig_slots = make_subplots(specs=[[{"secondary_y": True}]])
                fig_slots.add_trace(go.Scatter(x=df_time["fecha"], y=df_time["coin_in"], name="Coin In", fill="tozeroy", line=dict(color="#FF4B4B", width=1.5), fillcolor="rgba(255,75,75,0.15)"), secondary_y=False)
                fig_slots.add_trace(go.Scatter(x=df_time["fecha"], y=df_time["win"], name="Win", fill="tozeroy", line=dict(color="#00D1FF", width=2), fillcolor="rgba(0,209,255,0.12)"), secondary_y=True)
                fig_slots.update_layout(template="plotly_dark", height=230, margin=dict(l=10, r=10, t=5, b=5), legend=dict(orientation="h", y=1.1, x=0), xaxis_title=None)
                fig_slots.update_yaxes(showgrid=False, secondary_y=False)
                fig_slots.update_yaxes(showgrid=True, gridcolor="#1e222d", secondary_y=True)
                st.plotly_chart(fig_slots, use_container_width=True)
        with g2:
            st.caption("👥 Curva de Asistencia Diaria (Tráfico)")
            if not df_p_f.empty:
                fig_pers = px.bar(df_p_f.groupby("fecha")["cantidad"].sum().reset_index(), x="fecha", y="cantidad", template="plotly_dark", color_discrete_sequence=["#FF9F43"])
                fig_pers.update_layout(margin=dict(l=10, r=10, t=5, b=5), height=230, xaxis_title=None, yaxis_title=None)
                st.plotly_chart(fig_pers, use_container_width=True)

        st.write("")

        # --- TABLAS OPERATIVAS DENTRO DE EXPANDERS DESPLEGABLES ---
        st.markdown("### 📋 Desglose Técnico y Reportes Auditables de Sala")

        with st.expander("🏆 Ranking de Terminales por Net Win", expanded=False):
            if not df_f.empty:
                group_cols = ["asset_id"]
                for extra in ["marca", "modelo"]:
                    if extra in df_f.columns: group_cols.append(extra)
                df_rank = df_f.groupby(group_cols).agg(win=("win", "sum"), coin_in=("coin_in", "sum")).reset_index()
                
                # División segura nativa (Evita pd.NA y sus fallas de redondeo)
                df_rank["Hold %"] = (df_rank["win"] / df_rank["coin_in"] * 100).fillna(0).round(2)
                
                df_rank = df_rank.sort_values("win", ascending=False).head(15)
                df_rank["Alerta"] = df_rank["Hold %"].apply(lambda h: "🔴 Alto" if h > 15 else ("🟡 Revisar" if h > 10 else "✅ OK"))
                df_rank_display = df_rank.rename(columns={"asset_id": "CUIM", "win": "Net Win", "coin_in": "Coin In"})
                df_rank_display["Net Win"] = df_rank_display["Net Win"].apply(form_num)
                df_rank_display["Coin In"] = df_rank_display["Coin In"].apply(form_num)
                df_rank_display["Hold %"] = df_rank_display["Hold %"].apply(lambda x: f"{x:.2f}%")
                st.dataframe(df_rank_display, use_container_width=True, height=240, hide_index=True)

        with st.expander("📊 Gráfico Analítico de Hold % por Terminal (Outliers)", expanded=False):
            if not df_f.empty:
                df_hold_chart = df_f.groupby("asset_id").apply(lambda x: (x["win"].sum() / x["coin_in"].sum() * 100) if x["coin_in"].sum() > 0 else 0).reset_index(name="Hold %").sort_values("Hold %", ascending=True)
                df_hold_chart["color"] = df_hold_chart["Hold %"].apply(lambda h: "#ef5350" if h > 15 else ("#ff9f43" if h > 10 else "#00d1ff"))
                fig_hold = go.Figure(go.Bar(x=df_hold_chart["Hold %"], y=df_hold_chart["asset_id"], orientation="h", marker_color=df_hold_chart["color"], text=df_hold_chart["Hold %"].apply(lambda h: f"{h:.1f}%"), textposition="outside"))
                fig_hold.add_vline(x=15, line_dash="dash", line_color="#ef5350")
                fig_hold.update_layout(template="plotly_dark", height=400, margin=dict(l=10, r=60, t=10, b=10), showlegend=False)
                st.plotly_chart(fig_hold, use_container_width=True)

        with st.expander("🚫 Máquinas sin Actividad / Rendimiento Cero", expanded=False):
            if not df_f.empty:
                sin_juego_ids = df_f.groupby("asset_id")["coin_in"].sum()
                sin_juego_ids = sin_juego_ids[sin_juego_ids == 0].index.tolist()
                if sin_juego_ids:
                    df_sj = df_f[df_f["asset_id"].isin(sin_juego_ids)][["asset_id"] + [c for c in ["marca", "modelo", "juego"] if c in df_f.columns]].drop_duplicates()
                    st.dataframe(df_sj.rename(columns={"asset_id": "CUIM"}), use_container_width=True, height=200, hide_index=True)
                else:
                    st.success("Operación óptima: 0 máquinas inactivas registradas en este período.")

        with st.expander("💎 Jackpots Mayores a $ 1.000.000", expanded=False):
            if not df_f.empty and "jackpot" in df_f.columns:
                altos = df_f[df_f["jackpot"] >= 1000000][["fecha", "asset_id", "jackpot"]]
                if not altos.empty:
                    altos_display = altos.rename(columns={"asset_id": "CUIM"}).sort_values("jackpot", ascending=False)
                    altos_display["jackpot"] = altos_display["jackpot"].apply(form_num)
                    st.dataframe(altos_display, use_container_width=True, height=200, hide_index=True)

        with st.expander("🏬 Resumen General Rendimiento por Fabricante", expanded=False):
            if not df_f.empty and "marca" in df_f.columns:
                df_comp = df_f.groupby("marca").agg(win=("win", "sum"), coin_in=("coin_in", "sum"), maquinas=("asset_id", "nunique")).reset_index()
                
                # División segura vectorizada con fillna(0) que corrige el bug de image_a441c3.png
                df_comp["Hold %"] = (df_comp["win"] / df_comp["coin_in"] * 100).fillna(0).round(2)
                
                df_comp["win_fmt"] = df_comp["win"].apply(form_num)
                df_comp["Hold %"] = df_comp["Hold %"].apply(lambda x: f"{x:.2f}%")
                
                st.dataframe(df_comp[["marca", "maquinas", "win_fmt", "Hold %"]].rename(columns={"marca": "Marca", "maquinas": "Máquinas Total", "win_fmt": "Net Win"}), use_container_width=True, height=200, hide_index=True)

    # =========================================================================
    # VISTA 2: CONTROL DE BILLETES
    # =========================================================================
    elif nav == "💵 Control de Billetes":
        st.subheader("Reporte Avanzado de Drop Físico por CUIM / N° Máquina")

        if df_billetes is None or df_billetes.empty:
            st.warning("No hay datos de billetes disponibles.")
            st.stop()

        st.markdown("<div class='filter-bar'>", unsafe_allow_html=True)
        fb1, fb2, fb3 = st.columns([1.4, 1.5, 2.1])
        with fb1: fb_rango = st.date_input("Rango", [df_billetes["fecha"].min(), df_billetes["fecha"].max()], label_visibility="collapsed")
        with fb2: fb_id = st.multiselect("CUIM", sorted(df_billetes["asset_id"].dropna().unique()), placeholder="🆔 Filtrar por CUIM...", label_visibility="collapsed")
        with fb3:
            col_denom_all = [c for c in df_billetes.columns if c.startswith("bills") or "denom" in c]
            fb_denom = st.multiselect("Denominaciones", col_denom_all, placeholder="💵 Filtrar denominaciones...", label_visibility="collapsed")
        st.markdown("</div>", unsafe_allow_html=True)

        df_bf = df_billetes.copy()
        if isinstance(fb_rango, (list, tuple)) and len(fb_rango) == 2:
            df_bf = df_bf.loc[(df_bf["fecha"] >= fb_rango[0]) & (df_bf["fecha"] <= fb_rango[1])]
        if fb_id: df_bf = df_bf.loc[df_bf["asset_id"].isin(fb_id)]

        total_pesos = df_bf["total pesos"].sum() if "total pesos" in df_bf.columns else 0.0
        total_bills = df_bf["total bills"].sum() if "total pesos" in df_bf.columns else 0.0

        bk1, bk2 = st.columns(2)
        with bk1: st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Total Recaudado en Pesos (Drop Físico)</div><div class='kpi-value' style='color:#00ffcc;'>{form_num(total_pesos)}</div></div>", unsafe_allow_html=True)
        with bk2: st.markdown(f"<div class='kpi-wrapper'><div class='kpi-title'>Cantidad Total de Billetes Físicos</div><div class='kpi-value'>{total_bills:,.0f} u.</div></div>", unsafe_allow_html=True)

        st.write("")
        bg1, bg2 = st.columns([2.1, 1.9])

        with bg1:
            st.markdown("<div class='sielcon-panel'>", unsafe_allow_html=True)
            st.markdown("<div class='panel-header'>💵 Resumen Contable y Retenciones</div>", unsafe_allow_html=True)
            cols_fin = [c for c in ["total pesos", "retencion teorica", "retencion real", "diferencia retencion"] if c in df_bf.columns]
            if cols_fin:
                df_res = df_bf.groupby("asset_id")[cols_fin].sum().reset_index()
                df_res_fmt = df_res.copy()
                for c in cols_fin: df_res_fmt[c] = df_res_fmt[c].apply(form_num)
                st.dataframe(df_res_fmt.rename(columns={"asset_id": "CUIM"}), use_container_width=True, height=300, hide_index=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with bg2:
            st.markdown("<div class='sielcon-panel'>", unsafe_allow_html=True)
            st.markdown("<div class='panel-header'>📊 Unidades por Denominación</div>", unsafe_allow_html=True)
            col_denom_existentes = [c for c in (fb_denom if fb_denom else col_denom_all) if c in df_bf.columns]
            if col_denom_existentes:
                nombre_denom = {"bills 100": "$100", "bills 200": "$200", "bills 500": "$500", "bills 1000": "$1.000", "bills 2000": "$2.000", "bills 10000": "$10.000", "bills 20000": "$20.000"}
                df_denom = df_bf[col_denom_existentes].sum().reset_index()
                df_denom.columns = ["interno", "Cantidad"]
                df_denom["Denominación"] = df_denom["interno"].map(nombre_denom).fillna(df_denom["interno"])
                fig_denom = px.bar(df_denom, x="Denominación", y="Cantidad", text_auto=",", template="plotly_dark", color_discrete_sequence=["#00D1FF"])
                fig_denom.update_layout(margin=dict(l=10, r=10, t=15, b=10), height=280, xaxis_title=None, yaxis_title=None)
                st.plotly_chart(fig_denom, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

    # =========================================================================
    # VISTA 3: ANALISTA COMPARATIVO
    # =========================================================================
    elif nav == "🔄 Analista Comparativo":
        st.subheader("⚖️ Diagnóstico Comparativo de Períodos")
        if df_slots is None or df_slots.empty:
            st.warning("No hay datos disponibles.")
            st.stop()

        with st.container(border=True):
            col1, col2 = st.columns(2)
            max_f = df_slots["fecha"].max()
            r_act = col1.date_input("📅 Período A (actual)", [max_f - timedelta(days=7), max_f])
            r_ant = col2.date_input("📅 Período B (comparación)", [max_f - timedelta(days=15), max_f - timedelta(days=8)])

        if len(r_act) == 2 and len(r_ant) == 2:
            df_a = df_slots.loc[(df_slots["fecha"] >= r_act[0]) & (df_slots["fecha"] <= r_act[1])]
            df_b = df_slots.loc[(df_slots["fecha"] >= r_ant[0]) & (df_slots["fecha"] <= r_ant[1])]

            wa, wb = df_a["win"].sum(), df_b["win"].sum()
            ca, cb = df_a["coin_in"].sum(), df_b["coin_in"].sum()
            ha = (wa / ca * 100) if ca > 0 else 0
            hb = (wb / cb * 100) if cb > 0 else 0

            m1, m2, m3 = st.columns(3)
            m1.metric("WIN — Var. A vs B", form_num(wa - wb), f"{((wa - wb)/wb*100 if wb else 0):.1f}%")
            m2.metric("COIN IN — Var. A vs B", form_num(ca - cb), f"{((ca - cb)/cb*100 if cb else 0):.1f}%")
            m3.metric("HOLD % — Período A", f"{ha:.2f}%", f"{ha - hb:+.2f}pp vs B")

            st.write("")
            df_diff = pd.merge(df_a.groupby("asset_id")["win"].sum().reset_index(), df_b.groupby("asset_id")["win"].sum().reset_index(), on="asset_id", suffixes=("_A", "_B"), how="outer").fillna(0)
            df_diff["Var. $"] = df_diff["win_A"] - df_diff["win_B"]
            df_diff_disp = df_diff.rename(columns={"asset_id": "CUIM", "win_A": "Win A", "win_B": "Win B"})
            for c in ["Win A", "Win B", "Var. $"]: df_diff_disp[c] = df_diff_disp[c].apply(form_num)
            st.dataframe(df_diff_disp.sort_values("Var. $", ascending=False), use_container_width=True, hide_index=True)

    # =========================================================================
    # VISTA 4: GESTIÓN DE USUARIOS
    # =========================================================================
    elif nav == "👤 Gestión Usuarios" and current_role == "admin":
        st.subheader("👤 Auditoría de Accesos")
        if df_users is not None and not df_users.empty:
            st.dataframe(df_users[[c for c in ["nombre", "usuario", "rol"] if c in df_users.columns]], use_container_width=True, hide_index=True)
else:
    st.error("Error al conectar con la base de datos de usuarios.")