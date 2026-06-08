import json
import os
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from langchain_core.tools import tool


ZONA_COLOMBIA = ZoneInfo("America/Bogota")

CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]


def obtener_fecha_actual_colombia():
    return datetime.now(ZONA_COLOMBIA)


def obtener_config_calendar():
    """
    Lee configuración desde .env.
    """

    load_dotenv()

    credenciales = (
        os.getenv("GOOGLE_CALENDAR_CREDENTIALS")
        or os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    )

    calendar_id = os.getenv("GOOGLE_CALENDAR_ID")

    if not credenciales:
        raise ValueError(
            "Falta GOOGLE_CALENDAR_CREDENTIALS o GOOGLE_SHEETS_CREDENTIALS en .env"
        )

    if not calendar_id:
        raise ValueError("Falta GOOGLE_CALENDAR_ID en .env")

    return credenciales, calendar_id


def obtener_servicio_calendar():
    """
    Crea el cliente real de Google Calendar usando cuenta de servicio.

    Importante:
    Se debe compartir el calendario con el client_email del JSON,
    dándole permiso para modificar eventos.
    """

    credenciales_path, _ = obtener_config_calendar()

    credenciales = Credentials.from_service_account_file(
        credenciales_path,
        scopes=CALENDAR_SCOPES,
    )

    servicio = build("calendar", "v3", credentials=credenciales)

    return servicio


def crear_datetime_colombia(fecha, hora):
    """
    Convierte fecha YYYY-MM-DD y hora HH:mm a datetime ISO con zona Colombia.

    Ejemplo:
    fecha = "2026-06-08"
    hora = "15:00"

    Retorna:
    "2026-06-08T15:00:00-05:00"
    """

    if not fecha or not hora:
        return None

    hora_limpia = str(hora).strip()[:5]
    texto = f"{fecha}T{hora_limpia}:00"

    dt = datetime.fromisoformat(texto)
    dt = dt.replace(tzinfo=ZONA_COLOMBIA)

    return dt.isoformat()


def sumar_minutos(datetime_iso, minutos):
    """
    Suma minutos a un datetime ISO.
    """

    dt = datetime.fromisoformat(datetime_iso)
    dt_final = dt + timedelta(minutes=int(minutos))

    return dt_final.isoformat()


def crear_intervalo(fecha, hora, duracion):
    """
    Crea start_datetime y end_datetime para Calendar.
    """

    start_datetime = crear_datetime_colombia(fecha, hora)

    if not start_datetime:
        return {
            "start_datetime": None,
            "end_datetime": None,
        }

    end_datetime = sumar_minutos(start_datetime, duracion)

    return {
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
    }


def obtener_inicio_evento(evento):
    return (
        evento.get("start", {}).get("dateTime")
        or evento.get("start", {}).get("date")
        or None
    )


def obtener_fin_evento(evento):
    return (
        evento.get("end", {}).get("dateTime")
        or evento.get("end", {}).get("date")
        or None
    )


def extraer_duracion_desde_descripcion(descripcion):
    """
    Busca una duración guardada en la descripción del evento.

    Ejemplo:
    Duración: 45 minutos
    """

    if not descripcion:
        return None

    match = re.search(r"Duraci[oó]n:\s*(\d+)\s*minutos?", descripcion, re.IGNORECASE)

    if not match:
        return None

    return int(match.group(1))


def calcular_duracion_evento(evento):
    """
    Calcula la duración original de un evento.

    Primero intenta leerla desde la descripción.
    Si no existe, la calcula usando inicio y fin.
    """

    descripcion = evento.get("description", "")
    duracion = extraer_duracion_desde_descripcion(descripcion)

    if duracion:
        return duracion

    inicio = obtener_inicio_evento(evento)
    fin = obtener_fin_evento(evento)

    if not inicio or not fin:
        return 30

    try:
        inicio_dt = datetime.fromisoformat(inicio.replace("Z", "+00:00"))
        fin_dt = datetime.fromisoformat(fin.replace("Z", "+00:00"))
        diferencia = fin_dt - inicio_dt
        return max(1, round(diferencia.total_seconds() / 60))
    except Exception:
        return 30


def verificar_disponibilidad(start_datetime, end_datetime, excluir_evento_id=None):
    """
    Revisa si hay eventos en el intervalo dado.

    Retorna:
    {
        "available": True/False,
        "eventos_encontrados": [...]
    }
    """

    _, calendar_id = obtener_config_calendar()
    servicio = obtener_servicio_calendar()

    respuesta = (
        servicio.events()
        .list(
            calendarId=calendar_id,
            timeMin=start_datetime,
            timeMax=end_datetime,
            singleEvents=True,
            orderBy="startTime",
            timeZone="America/Bogota",
        )
        .execute()
    )

    eventos = respuesta.get("items", [])

    eventos_activos = []

    for evento in eventos:
        if evento.get("status") == "cancelled":
            continue

        if excluir_evento_id and evento.get("id") == excluir_evento_id:
            continue

        eventos_activos.append(evento)

    return {
        "available": len(eventos_activos) == 0,
        "eventos_encontrados": eventos_activos,
        "cantidad_eventos": len(eventos_activos),
    }


def crear_descripcion_cita(datos):
    """
    Descripción del evento de Calendar.
    Mantiene el mismo estilo que usabamos en N8n.
    """

    descripcion = f"""Cliente: {datos.get("nombre_cliente", "Cliente")}
Chat ID: {datos.get("chat_id", "")}
Servicio: {datos.get("servicio", "No especificado")}
Duración: {datos.get("duracion", 30)} minutos
Estado: activa

Riesgo operativo: {datos.get("riesgo_categoria", "no_calculado")}
Puntaje de riesgo: {datos.get("riesgo_num", "")}
Acción recomendada: {datos.get("accion_racional", "")}

Mensaje original:
{datos.get("mensaje_cliente", "")}
"""

    return descripcion


def crear_cita_calendar(datos):
    """
    Crea una cita real en Google Calendar.

    datos debe traer:
    - chat_id
    - nombre_cliente
    - mensaje_cliente
    - servicio
    - fecha
    - hora
    - duracion
    - riesgo_num
    - riesgo_categoria
    - accion_racional
    """

    _, calendar_id = obtener_config_calendar()
    servicio = obtener_servicio_calendar()

    fecha = datos.get("fecha")
    hora = datos.get("hora")
    duracion = int(datos.get("duracion") or 30)

    intervalo = crear_intervalo(fecha, hora, duracion)

    if not intervalo["start_datetime"]:
        return {
            "ok": False,
            "error": "Falta fecha u hora para crear la cita.",
        }

    disponibilidad = verificar_disponibilidad(
        intervalo["start_datetime"],
        intervalo["end_datetime"],
    )

    if not disponibilidad["available"]:
        return {
            "ok": False,
            "disponibilidad": "ocupado",
            "error": "El horario no está disponible.",
            "cantidad_eventos": disponibilidad["cantidad_eventos"],
        }

    evento = {
        "summary": (
            f"BarberBot - {datos.get('servicio', 'servicio')} - "
            f"{datos.get('nombre_cliente', 'Cliente')} - "
            f"Riesgo {datos.get('riesgo_categoria', 'no_calculado')}"
        ),
        "description": crear_descripcion_cita(datos),
        "start": {
            "dateTime": intervalo["start_datetime"],
            "timeZone": "America/Bogota",
        },
        "end": {
            "dateTime": intervalo["end_datetime"],
            "timeZone": "America/Bogota",
        },
    }

    evento_creado = (
        servicio.events()
        .insert(calendarId=calendar_id, body=evento)
        .execute()
    )

    return {
        "ok": True,
        "disponibilidad": "disponible",
        "estado_operacion": "creada",
        "evento_id": evento_creado.get("id"),
        "html_link": evento_creado.get("htmlLink"),
        "start_datetime": intervalo["start_datetime"],
        "end_datetime": intervalo["end_datetime"],
    }


def buscar_cita_activa_por_chat(chat_id):
    """
    Busca la próxima cita activa y futura asociada a un chat_id.

    Se basa en la descripción:
    Chat ID: <chat_id>
    Estado: activa
    """

    _, calendar_id = obtener_config_calendar()
    servicio = obtener_servicio_calendar()

    ahora = obtener_fecha_actual_colombia().isoformat()

    respuesta = (
        servicio.events()
        .list(
            calendarId=calendar_id,
            timeMin=ahora,
            maxResults=20,
            singleEvents=True,
            orderBy="startTime",
            q=f"Chat ID: {chat_id}",
            timeZone="America/Bogota",
        )
        .execute()
    )

    eventos = respuesta.get("items", [])

    eventos_validos = []

    for evento in eventos:
        descripcion = evento.get("description", "")
        inicio = obtener_inicio_evento(evento)

        tiene_chat = f"Chat ID: {chat_id}" in descripcion
        esta_cancelada = "estado: cancelada" in descripcion.lower()
        es_activa = not esta_cancelada
        es_futura = True

        if inicio:
            try:
                inicio_dt = datetime.fromisoformat(inicio.replace("Z", "+00:00"))
                es_futura = inicio_dt >= obtener_fecha_actual_colombia()
            except Exception:
                es_futura = True

        if tiene_chat and es_activa and es_futura:
            eventos_validos.append(evento)

    eventos_validos.sort(key=lambda e: obtener_inicio_evento(e) or "")

    if not eventos_validos:
        return {
            "evento_encontrado": False,
            "event_id": None,
            "debug_eventos_recibidos": len(eventos),
        }

    evento = eventos_validos[0]

    return {
        "evento_encontrado": True,
        "event_id": evento.get("id"),
        "summary": evento.get("summary"),
        "description": evento.get("description", ""),
        "inicio": obtener_inicio_evento(evento),
        "fin": obtener_fin_evento(evento),
        "duracion_original_minutos": calcular_duracion_evento(evento),
        "evento": evento,
        "debug_eventos_recibidos": len(eventos),
    }


def cancelar_cita_calendar(chat_id, mensaje_cliente=""):
    """
    Cancela una cita eliminando el evento real de Google Calendar.

    El historial de la cancelación se conserva en Google Sheets desde agent.py
    """

    _, calendar_id = obtener_config_calendar()
    servicio = obtener_servicio_calendar()

    busqueda = buscar_cita_activa_por_chat(chat_id)

    if not busqueda["evento_encontrado"]:
        return {
            "ok": False,
            "estado_operacion": "no_existe_cita",
            "error": "No se encontró una cita activa para cancelar.",
        }

    evento_id = busqueda["event_id"]

    servicio.events().delete(
        calendarId=calendar_id,
        eventId=evento_id,
    ).execute()

    return {
        "ok": True,
        "estado_operacion": "cancelada_eliminada_calendar",
        "evento_id": evento_id,
        "html_link": None,
    }


def cambiar_hora_cita_calendar(chat_id, nueva_fecha, nueva_hora, mensaje_cliente=""):
    """
    Cambia la hora de una cita existente.

    Pasos:
    1. Busca cita activa por chat_id.
    2. Toma duración original.
    3. Calcula nuevo inicio y fin.
    4. Verifica disponibilidad excluyendo la cita actual.
    5. Actualiza el evento.
    """

    _, calendar_id = obtener_config_calendar()
    servicio = obtener_servicio_calendar()

    busqueda = buscar_cita_activa_por_chat(chat_id)

    if not busqueda["evento_encontrado"]:
        return {
            "ok": False,
            "estado_operacion": "no_existe_cita",
            "error": "No se encontró una cita activa para cambiar.",
        }

    if not nueva_fecha or not nueva_hora:
        return {
            "ok": False,
            "estado_operacion": "datos_incompletos_cambio",
            "error": "Falta nueva fecha u hora para cambiar la cita.",
        }

    evento_id = busqueda["event_id"]
    duracion_original = busqueda.get("duracion_original_minutos") or 30

    intervalo = crear_intervalo(nueva_fecha, nueva_hora, duracion_original)

    disponibilidad = verificar_disponibilidad(
        intervalo["start_datetime"],
        intervalo["end_datetime"],
        excluir_evento_id=evento_id,
    )

    if not disponibilidad["available"]:
        return {
            "ok": False,
            "estado_operacion": "no_cambiada_horario_ocupado",
            "disponibilidad": "ocupado",
            "evento_id": evento_id,
            "error": "El nuevo horario no está disponible.",
            "cantidad_eventos": disponibilidad["cantidad_eventos"],
        }

    descripcion_anterior = busqueda.get("description", "")

    nueva_descripcion = f"""{descripcion_anterior}

Estado: activa
Última acción: cambio de hora
Nueva fecha: {nueva_fecha}
Nueva hora: {nueva_hora}
Mensaje de cambio:
{mensaje_cliente}
Fecha de cambio: {obtener_fecha_actual_colombia().isoformat()}
"""

    evento_actualizado = (
        servicio.events()
        .patch(
            calendarId=calendar_id,
            eventId=evento_id,
            body={
                "start": {
                    "dateTime": intervalo["start_datetime"],
                    "timeZone": "America/Bogota",
                },
                "end": {
                    "dateTime": intervalo["end_datetime"],
                    "timeZone": "America/Bogota",
                },
                "description": nueva_descripcion,
                "summary": busqueda.get("summary") or "Cita BarberBot",
            },
        )
        .execute()
    )
    return {
        "ok": True,
        "estado_operacion": "actualizada_calendar",
        "disponibilidad": "disponible",
        "evento_id": evento_actualizado.get("id"),
        "html_link": evento_actualizado.get("htmlLink"),
        "nueva_fecha": nueva_fecha,
        "nueva_hora": nueva_hora,
        "nueva_start_datetime": intervalo["start_datetime"],
        "nueva_end_datetime": intervalo["end_datetime"],
        "duracion_usada_para_cambio": duracion_original,
    }


def verificar_disponibilidad_tool(datos_json: str) -> str:
    """
    Verifica disponibilidad en Google Calendar.

    Recibe JSON en texto:
    {
      "fecha": "2026-06-08",
      "hora": "15:00",
      "duracion": 30
    }
    """

    try:
        datos = json.loads(datos_json)
        intervalo = crear_intervalo(
            datos.get("fecha"),
            datos.get("hora"),
            int(datos.get("duracion") or 30),
        )

        resultado = verificar_disponibilidad(
            intervalo["start_datetime"],
            intervalo["end_datetime"],
        )

        return json.dumps(
            {
                "ok": True,
                "fecha": datos.get("fecha"),
                "hora": datos.get("hora"),
                "duracion": datos.get("duracion") or 30,
                "start_datetime": intervalo["start_datetime"],
                "end_datetime": intervalo["end_datetime"],
                **resultado,
            },
            ensure_ascii=False,
        )

    except Exception as error:
        return json.dumps(
            {
                "ok": False,
                "error": str(error),
            },
            ensure_ascii=False,
        )

def crear_cita_calendar_tool(datos_json: str) -> str:
    """
    Crea una cita en Google Calendar.

    Recibe un JSON en texto con los datos completos de la cita.
    """

    try:
        datos = json.loads(datos_json)
        resultado = crear_cita_calendar(datos)
        return json.dumps(resultado, ensure_ascii=False)

    except Exception as error:
        return json.dumps(
            {
                "ok": False,
                "error": str(error),
            },
            ensure_ascii=False,
        )


def cancelar_cita_calendar_tool(datos_json: str) -> str:
    """
    Cancela una cita activa buscando por chat_id.

    Recibe JSON:
    {
      "chat_id": "123456789",
      "mensaje_cliente": "quiero cancelar mi cita"
    }
    """

    try:
        datos = json.loads(datos_json)
        resultado = cancelar_cita_calendar(
            chat_id=datos.get("chat_id"),
            mensaje_cliente=datos.get("mensaje_cliente", ""),
        )
        return json.dumps(resultado, ensure_ascii=False)

    except Exception as error:
        return json.dumps(
            {
                "ok": False,
                "error": str(error),
            },
            ensure_ascii=False,
        )


def cambiar_hora_cita_calendar_tool(datos_json: str) -> str:
    """
    Cambia la hora de una cita activa buscando por chat_id.

    Recibe JSON:
    {
      "chat_id": "123456789",
      "nueva_fecha": "2026-06-09",
      "nueva_hora": "16:00",
      "mensaje_cliente": "quiero cambiar mi cita para mañana a las 4"
    }
    """

    try:
        datos = json.loads(datos_json)
        resultado = cambiar_hora_cita_calendar(
            chat_id=datos.get("chat_id"),
            nueva_fecha=datos.get("nueva_fecha"),
            nueva_hora=datos.get("nueva_hora"),
            mensaje_cliente=datos.get("mensaje_cliente", ""),
        )
        return json.dumps(resultado, ensure_ascii=False)

    except Exception as error:
        return json.dumps(
            {
                "ok": False,
                "error": str(error),
            },
            ensure_ascii=False,
        )



if __name__ == "__main__":
    load_dotenv()

    if len(sys.argv) < 2:
        print("Uso:")
        print("python tools_calendar.py verificar")
        print("python tools_calendar.py crear")
        print("python tools_calendar.py buscar CHAT_ID")
        print("python tools_calendar.py cancelar CHAT_ID")
        print()
        sys.exit(0)

    accion = sys.argv[1]

    try:
        if accion == "verificar":
            datos_prueba = {
                "fecha": "2026-06-10",
                "hora": "15:00",
                "duracion": 30,
            }

            intervalo = crear_intervalo(
                datos_prueba["fecha"],
                datos_prueba["hora"],
                datos_prueba["duracion"],
            )

            resultado = verificar_disponibilidad(
                intervalo["start_datetime"],
                intervalo["end_datetime"],
            )

            print(json.dumps(resultado, ensure_ascii=False, indent=2))

        elif accion == "crear":
            datos_prueba = {
                "chat_id": "123456789",
                "nombre_cliente": "Cliente prueba",
                "mensaje_cliente": "Quiero un corte mañana a las 3 pm",
                "servicio": "corte",
                "fecha": "2026-06-10",
                "hora": "15:00",
                "duracion": 30,
                "riesgo_num": 0.3,
                "riesgo_categoria": "bajo",
                "accion_racional": "crear cita normalmente",
            }

            resultado = crear_cita_calendar(datos_prueba)
            print(json.dumps(resultado, ensure_ascii=False, indent=2))

        elif accion == "buscar":
            if len(sys.argv) < 3:
                print("Falta CHAT_ID")
                sys.exit(1)

            chat_id = sys.argv[2]
            resultado = buscar_cita_activa_por_chat(chat_id)
            print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))

        elif accion == "cancelar":
            if len(sys.argv) < 3:
                print("Falta CHAT_ID")
                sys.exit(1)

            chat_id = sys.argv[2]
            resultado = cancelar_cita_calendar(
                chat_id=chat_id,
                mensaje_cliente="Cancelación de prueba desde LangChain",
            )
            print(json.dumps(resultado, ensure_ascii=False, indent=2))

        else:
            print("Acción no reconocida.")

    except Exception as error:
        print("Error probando Calendar:")
        print(error)
