"""Vista Cloud de solo lectura para Tuya. No almacena secretos ni datos privados."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st
from tuya_connector import TuyaOpenAPI

st.set_page_config(page_title="Microinversor Solar Monitor", page_icon="☀️", layout="wide")
st.title("☀️ Microinversor Solar Monitor")
st.caption("Vista Cloud · Tuya API · datos consultados bajo demanda. El historial de esta vista solo dura la sesión abierta.")

REQUIRED = ("TUYA_ACCESS_ID", "TUYA_ACCESS_SECRET", "TUYA_DEVICE_ID")
missing = [key for key in REQUIRED if not st.secrets.get(key)]
if missing:
    st.warning("Falta configurar los secretos de Tuya en Streamlit Cloud: " + ", ".join(missing))
    st.info("En la configuración de la aplicación, abre **Settings → Secrets**. Nunca agregues credenciales al repositorio.")
    st.stop()

ID = str(st.secrets["TUYA_ACCESS_ID"])
SECRET = str(st.secrets["TUYA_ACCESS_SECRET"])
DEVICE = str(st.secrets["TUYA_DEVICE_ID"])
ENDPOINT = str(st.secrets.get("TUYA_ENDPOINT", "https://openapi.tuyaus.com"))
TZ = ZoneInfo("America/Santiago")

@st.cache_resource(show_spinner=False)
def create_api(access_id: str, secret: str, endpoint: str):
    api = TuyaOpenAPI(endpoint, access_id, secret)
    auth = api.connect()
    if not isinstance(auth, dict) or not auth.get("success") or not api.is_connect():
        raise RuntimeError("No se pudo autenticar con Tuya; revisa credenciales, endpoint y restricciones de IP.")
    return api

def fetch_status() -> dict:
    api = create_api(ID, SECRET, ENDPOINT)
    url = f"/v1.0/iot-03/devices/{DEVICE}/status"
    response = api.get(url)
    if isinstance(response, dict) and response.get("code") in (1010, 1011, 1012):
        create_api.clear()
        api = create_api(ID, SECRET, ENDPOINT)
        response = api.get(url)
    if not isinstance(response, dict) or not response.get("success"):
        code = response.get("code") if isinstance(response, dict) else "?"
        raise RuntimeError(f"Consulta Tuya rechazada (código {code}). Revisa los permisos de la API.")
    values = response.get("result")
    if not isinstance(values, list):
        raise RuntimeError("Tuya no entregó datos de estado.")
    raw = {x["code"]: x.get("value") for x in values if isinstance(x, dict) and "code" in x}
    def val(key, scale):
        try:
            value = raw.get(key)
            return None if value is None or isinstance(value, bool) else float(value) / scale
        except (TypeError, ValueError):
            return None
    return {
        "hora": datetime.now(TZ).isoformat(),
        "potencia_w": val("cur_power", 10),
        "voltaje_v": val("cur_voltage", 10),
        "corriente_a": val("cur_current", 1000),
        "fault": raw.get("fault"),
        "energia_bruta": raw.get("add_ele"),
    }

if "historial" not in st.session_state:
    st.session_state.historial = []

@st.fragment(run_every="120s")
def mostrar():
    try:
        data = fetch_status()
    except Exception as exc:
        st.error(str(exc))
        st.caption("Si aparece un bloqueo IP, recuerda que Streamlit Cloud utiliza direcciones de salida distintas de tu hogar.")
        return

    st.success("Consulta Tuya correcta")
    st.caption("Lectura recibida: " + datetime.fromisoformat(data["hora"]).strftime("%d/%m/%Y %H:%M:%S") + " (Santiago)")
    a,b,c,d = st.columns(4)
    def fmt(v, digits=1):
        return "N/D" if v is None else f"{v:,.{digits}f}"
    a.metric("⚡ Potencia", fmt(data["potencia_w"]) + " W")
    b.metric("🔌 Voltaje", fmt(data["voltaje_v"]) + " V")
    c.metric("〰️ Corriente", fmt(data["corriente_a"], 3) + " A")
    d.metric("🛡️ Código de falla", str(data["fault"]))

    history = st.session_state.historial
    if not history or history[-1]["hora"] != data["hora"]:
        history.append(data)
        if len(history) > 2000:
            del history[:-2000]
    frame = pd.DataFrame(history)
    if len(frame) > 1:
        frame["fecha"] = pd.to_datetime(frame["hora"])
        fig = px.line(frame, x="fecha", y="potencia_w",
                      title="Potencia durante esta sesión", labels={"fecha":"Hora","potencia_w":"Potencia (W)"})
        st.plotly_chart(fig, use_container_width=True)
        st.download_button("Descargar lecturas de esta sesión", frame.to_csv(index=False).encode("utf-8"),
                           "lecturas_sesion.csv", mime="text/csv")
    st.caption("Los datos aquí no se guardan permanentemente. La vista no calcula ahorro ni energía diaria sin un historial persistente.")
mostrar()
