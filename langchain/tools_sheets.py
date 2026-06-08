import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from dotenv import load_dotenv
from langchain_core.tools import tool

from fuzzy_risk import calcular_historial_cliente


ZONA_COLOMBIA = ZoneInfo("America/Bogota")


COLUMNAS_FASE_2 = [
    "fecha_recepcion",
    "chat_id",
    "nombre_cliente",
    "mensaje_cliente",
    "intencion",
    "servicio",
    "fecha",
    "hora",
    "duracion",
    "respuesta_sugerida",
    "nueva_fecha",
    "nueva_hora",
    "disponibilidad",
    "estado_operacion",
    "evento_id",
    "riesgo_num",
    "riesgo_categoria",
    "accion_racional",
    "tiempo_respuesta_ms",
    "respuesta_final",
    "fecha_finalizacion",
    "resultado_cita",
    "estado_cita",
    "historial_cliente",
    "historial_confianza",
    "historial_eventos_evaluables",
    "anticipacion_horas",
    "confirmacion_cliente",
]


def obtener_fecha_actual_colombia():
    return datetime.now(ZONA_COLOMBIA).isoformat(timespec="seconds")


def limpiar_valor(valor):
    """
    Convierte valores de Python a valores seguros para Google Sheets.
    """
    if valor is None:
        return ""

    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False)

    return valor


def obtener_config_sheets():
    """
    Lee la configuración de Google Sheets desde el archivo .env.
    """

    load_dotenv()

    credenciales = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Fase 2")

    if not credenciales:
        raise ValueError("Falta GOOGLE_SHEETS_CREDENTIALS en el archivo .env")

    if not sheet_id:
        raise ValueError("Falta GOOGLE_SHEET_ID en el archivo .env")

    return credenciales, sheet_id, sheet_name


def obtener_worksheet():
    """
    Abre la hoja de Google Sheets usando una cuenta de servicio.

    Requisito:
    - Crear una cuenta de servicio en Google Cloud.
    - Descargar el JSON de credenciales.
    - Compartir el Google Sheet con el correo client_email del JSON.
    """

    credenciales, sheet_id, sheet_name = obtener_config_sheets()

    cliente = gspread.service_account(filename=credenciales)
    documento = cliente.open_by_key(sheet_id)
    hoja = documento.worksheet(sheet_name)

    return hoja


def asegurar_encabezados():
    """
    Revisa si la primera fila tiene encabezados.
    Si la hoja está vacía, escribe los encabezados esperados.
    """

    hoja = obtener_worksheet()

    valores = hoja.get_all_values()

    if not valores:
        hoja.append_row(COLUMNAS_FASE_2)
        return

    primera_fila = valores[0]

    if primera_fila != COLUMNAS_FASE_2:
        print("Aviso: los encabezados actuales no son iguales a COLUMNAS_FASE_2.")
        print("No se modificaron automáticamente para evitar dañar tu hoja.")


def obtener_todas_las_filas():
    """
    Lee todas las filas como lista de diccionarios.
    Cada fila queda así:
    {
        "chat_id": "...",
        "mensaje_cliente": "...",
        ...
    }
    """

    hoja = obtener_worksheet()
    filas = hoja.get_all_records()

    return filas


def obtener_filas_por_chat(chat_id):
    """
    Filtra las filas de Google Sheets por chat_id.
    Esto replica la idea del nodo de N8n que busca historial del cliente.
    """

    chat_id = str(chat_id).strip()

    filas = obtener_todas_las_filas()

    filas_cliente = [
        fila
        for fila in filas
        if str(fila.get("chat_id", "")).strip() == chat_id
    ]

    return filas_cliente


def obtener_historial_desde_sheets(chat_id):
    """
    Obtiene filas reales desde Google Sheets y calcula el historial del cliente
    usando fuzzy_risk.calcular_historial_cliente().
    """

    filas_cliente = obtener_filas_por_chat(chat_id)

    historial = calcular_historial_cliente(filas_cliente)

    return {
        "chat_id": str(chat_id),
        "total_filas_cliente": len(filas_cliente),
        **historial,
    }


def construir_fila_resultado(datos):
    """
    Construye una fila en el mismo orden de COLUMNAS_FASE_2.
    """

    datos = dict(datos)

    if not datos.get("fecha_finalizacion"):
        datos["fecha_finalizacion"] = obtener_fecha_actual_colombia()

    if not datos.get("resultado_cita"):
        datos["resultado_cita"] = "pendiente"

    if not datos.get("estado_cita"):
        datos["estado_cita"] = "activa"

    fila = [limpiar_valor(datos.get(columna)) for columna in COLUMNAS_FASE_2]

    return fila


def registrar_resultado_final(datos):
    """
    Registra una fila final en Google Sheets.

    Entrada esperada:
    {
        "fecha_recepcion": "...",
        "chat_id": "...",
        "nombre_cliente": "...",
        "mensaje_cliente": "...",
        "intencion": "reservar",
        "servicio": "corte",
        "fecha": "2026-06-08",
        "hora": "15:00",
        "duracion": 30,
        "respuesta_sugerida": "...",
        "disponibilidad": "disponible",
        "estado_operacion": "creada",
        "evento_id": "...",
        "riesgo_num": 0.3,
        "riesgo_categoria": "bajo",
        "accion_racional": "crear cita normalmente",
        "respuesta_final": "Listo, tu cita quedó agendada."
    }
    """

    hoja = obtener_worksheet()
    fila = construir_fila_resultado(datos)

    hoja.append_row(fila, value_input_option="USER_ENTERED")

    return {
        "ok": True,
        "mensaje": "Resultado registrado en Google Sheets",
        "chat_id": str(datos.get("chat_id", "")),
        "estado_operacion": datos.get("estado_operacion", ""),
        "fecha_finalizacion": datos.get("fecha_finalizacion") or obtener_fecha_actual_colombia(),
    }


@tool
def obtener_historial_cliente_tool(chat_id: str) -> str:
    """
    Busca en Google Sheets el historial de un cliente usando su chat_id.
    Devuelve estadísticas como historial_cliente, historial_confianza
    e historial_eventos_evaluables.
    """

    resultado = obtener_historial_desde_sheets(chat_id)

    return json.dumps(resultado, ensure_ascii=False)


@tool
def registrar_resultado_final_tool(datos_json: str) -> str:
    """
    Registra en Google Sheets el resultado final de una operación de BarberBot.

    Recibe un JSON en texto con los datos de la cita o respuesta.
    """

    try:
        datos = json.loads(datos_json)
    except json.JSONDecodeError:
        return json.dumps(
            {
                "ok": False,
                "error": "El argumento datos_json no es un JSON válido",
            },
            ensure_ascii=False,
        )

    resultado = registrar_resultado_final(datos)

    return json.dumps(resultado, ensure_ascii=False)


def crear_tools_sheets():
    """
    Retorna las tools personalizadas de Google Sheets para usarlas en agent.py.
    """

    return [
        obtener_historial_cliente_tool,
        registrar_resultado_final_tool,
    ]


if __name__ == "__main__":
    load_dotenv()

    if len(sys.argv) < 2:
        print("Uso:")
        print("python tools_sheets.py TU_CHAT_ID")
        print()
        print("Ejemplo:")
        print("python tools_sheets.py 123456789")
        sys.exit(0)

    chat_id_prueba = sys.argv[1]

    print("Probando conexión con Google Sheets...")
    print(f"Buscando historial para chat_id: {chat_id_prueba}")
    print()

    try:
        historial = obtener_historial_desde_sheets(chat_id_prueba)
        print(json.dumps(historial, ensure_ascii=False, indent=2))

    except Exception as error:
        print("Error conectando con Google Sheets:")
        print(error)
