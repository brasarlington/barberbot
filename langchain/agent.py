import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from prompts import crear_cadena_interpretacion
from fuzzy_risk import calcular_riesgo_difuso
from tools_sheets import obtener_historial_desde_sheets, registrar_resultado_final
from tools_calendar import (
    crear_intervalo,
    crear_cita_calendar,
    cancelar_cita_calendar,
    cambiar_hora_cita_calendar,
)


ZONA_COLOMBIA = ZoneInfo("America/Bogota")


PRECIOS_BARBERIA = {
    "corte": 25000,
    "barba": 15000,
    "corte_barba": 35000,
    "cejas": 5000,
    "corte_cejas": 30000,
    "corte_barba_cejas": 40000,
    "mechas": 60000,
    "color_cabello": 80000,
}


HORARIOS_BARBERIA = """
Nuestros horarios de atención son:

Lunes a sábado: 9:00 a.m. a 7:00 p.m.
Domingos: cerrado.
""".strip()


def obtener_fecha_actual_colombia():
    return datetime.now(ZONA_COLOMBIA).isoformat(timespec="seconds")


def obtener_timestamp_ms():
    return int(time.time() * 1000)


def crear_llm():
    """
    Crea el modelo de lenguaje usando variables del archivo .env.
    """

    modelo = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    return ChatOpenAI(
        model=modelo,
        temperature=0,
    )


def limpiar_null(valor):
    """
    Convierte strings como 'null', 'None' o '' a None real de Python.
    """

    if valor is None:
        return None

    if isinstance(valor, str):
        texto = valor.strip()

        if texto == "":
            return None

        if texto.lower() in ["null", "none", "ninguno", "no aplica"]:
            return None

        return texto

    return valor


def normalizar_interpretacion(interpretacion):
    """
    Normaliza la salida del LLM para evitar errores posteriores.
    """

    intencion = limpiar_null(interpretacion.get("intencion")) or "desconocido"

    if intencion not in [
        "reservar",
        "precios",
        "horarios",
        "cancelar",
        "cambiar_hora",
        "desconocido",
    ]:
        intencion = "desconocido"

    servicio = limpiar_null(interpretacion.get("servicio"))
    fecha = limpiar_null(interpretacion.get("fecha"))
    hora = limpiar_null(interpretacion.get("hora"))
    nueva_fecha = limpiar_null(interpretacion.get("nueva_fecha"))
    nueva_hora = limpiar_null(interpretacion.get("nueva_hora"))

    try:
        duracion = int(interpretacion.get("duracion") or 30)
    except ValueError:
        duracion = 30

    respuesta_sugerida = (
        limpiar_null(interpretacion.get("respuesta_sugerida"))
        or "Claro, puedo ayudarte. ¿Me das más detalles?"
    )

    return {
        "intencion": intencion,
        "servicio": servicio,
        "fecha": fecha,
        "hora": hora,
        "nueva_fecha": nueva_fecha,
        "nueva_hora": nueva_hora,
        "duracion": duracion,
        "respuesta_sugerida": respuesta_sugerida,
    }


def preparar_datos_base(chat_id, nombre_cliente, mensaje_cliente, interpretacion, inicio_ms):
    """
    Une los datos de entrada del cliente con la interpretación del LLM.
    """

    datos = {
        "fecha_recepcion": obtener_fecha_actual_colombia(),
        "chat_id": str(chat_id),
        "nombre_cliente": nombre_cliente or "Cliente",
        "mensaje_cliente": mensaje_cliente,
        "inicio_ms": inicio_ms,
        **interpretacion,
    }

    intervalo = crear_intervalo(
        datos.get("fecha"),
        datos.get("hora"),
        datos.get("duracion"),
    )

    datos["start_datetime"] = intervalo.get("start_datetime")
    datos["end_datetime"] = intervalo.get("end_datetime")
    datos["tiene_fecha_y_hora"] = bool(
        datos.get("fecha") and datos.get("hora")
    )

    return datos


def calcular_tiempo_respuesta(inicio_ms):
    return obtener_timestamp_ms() - int(inicio_ms)


def registrar_log_seguro(datos):
    """
    Registra en Google Sheets.

    Si Sheets falla, no detiene todo el agente.
    Esto ayuda durante pruebas y video.
    """

    try:
        registrar_resultado_final(datos)
        datos["log_sheets"] = "registrado"
    except Exception as error:
        datos["log_sheets"] = "error"
        datos["error_sheets"] = str(error)

    return datos


def construir_respuesta_precios(datos):
    respuesta = f"""
Estos son nuestros precios:

- Corte: $25.000
- Barba: $15.000
- Corte + barba: $35.000
- Cejas: $5.000
- Corte + cejas: $30.000
- Corte + barba + cejas: $40.000
- Mechas: $60.000
- Color de cabello: $80.000

¿Quieres que te agende una cita?
""".strip()

    return {
        **datos,
        "disponibilidad": "no_consultada",
        "estado_operacion": "consulta_precios",
        "evento_id": None,
        "riesgo_num": 0,
        "riesgo_categoria": "no_aplica",
        "accion_racional": "responder precios",
        "respuesta_final": respuesta,
        "fecha_finalizacion": obtener_fecha_actual_colombia(),
        "resultado_cita": "no_aplica",
        "estado_cita": "no_aplica",
        "tiempo_respuesta_ms": calcular_tiempo_respuesta(datos["inicio_ms"]),
    }


def construir_respuesta_horarios(datos):
    respuesta = f"""
{HORARIOS_BARBERIA}

Puedes escribirme, por ejemplo:
"quiero un corte mañana a las 3 pm".
""".strip()

    return {
        **datos,
        "disponibilidad": "no_consultada",
        "estado_operacion": "consulta_horarios",
        "evento_id": None,
        "riesgo_num": 0,
        "riesgo_categoria": "no_aplica",
        "accion_racional": "responder horarios",
        "respuesta_final": respuesta,
        "fecha_finalizacion": obtener_fecha_actual_colombia(),
        "resultado_cita": "no_aplica",
        "estado_cita": "no_aplica",
        "tiempo_respuesta_ms": calcular_tiempo_respuesta(datos["inicio_ms"]),
    }


def construir_respuesta_desconocido(datos):
    respuesta = (
        datos.get("respuesta_sugerida")
        or 'No entendí bien tu solicitud. Puedes escribir algo como: "quiero un corte mañana a las 3 pm".'
    )

    return {
        **datos,
        "disponibilidad": "no_consultada",
        "estado_operacion": "desconocido",
        "evento_id": None,
        "riesgo_num": 0,
        "riesgo_categoria": "no_aplica",
        "accion_racional": "pedir reformulacion",
        "respuesta_final": respuesta,
        "fecha_finalizacion": obtener_fecha_actual_colombia(),
        "resultado_cita": "no_aplica",
        "estado_cita": "no_aplica",
        "tiempo_respuesta_ms": calcular_tiempo_respuesta(datos["inicio_ms"]),
    }


def manejar_reserva(datos):
    """
    Maneja la intención reservar.

    Flujo:
    1. Verifica si hay fecha y hora.
    2. Lee historial real desde Google Sheets.
    3. Calcula riesgo difuso.
    4. Crea cita real en Google Calendar.
    5. Registra resultado final en Sheets.
    """

    if not datos.get("tiene_fecha_y_hora"):
        respuesta = (
            datos.get("respuesta_sugerida")
            or "Claro, puedo ayudarte a reservar. ¿Qué fecha y hora prefieres?"
        )

        resultado = {
            **datos,
            "disponibilidad": "no_consultada",
            "estado_operacion": "datos_incompletos",
            "evento_id": None,
            "riesgo_num": 0,
            "riesgo_categoria": "no_aplica",
            "accion_racional": "pedir fecha y hora",
            "respuesta_final": respuesta,
            "fecha_finalizacion": obtener_fecha_actual_colombia(),
            "resultado_cita": "pendiente",
            "estado_cita": "sin_agendar",
            "tiempo_respuesta_ms": calcular_tiempo_respuesta(datos["inicio_ms"]),
        }

        return resultado

    historial = obtener_historial_desde_sheets(datos["chat_id"])

    datos_con_historial = {
        **datos,
        "historial_cliente": historial.get("historial_cliente", 0.6),
        "historial_confianza": historial.get("historial_confianza", 0.0),
        "historial_eventos_evaluables": historial.get(
            "historial_eventos_evaluables",
            0,
        ),
    }

    datos_con_riesgo = calcular_riesgo_difuso(datos_con_historial)

    resultado_calendar = crear_cita_calendar(datos_con_riesgo)

    if resultado_calendar.get("ok"):
        respuesta = f"""
Listo ✅ Tu cita quedó agendada.

Servicio: {datos_con_riesgo.get("servicio")}
Fecha: {datos_con_riesgo.get("fecha")}
Hora: {datos_con_riesgo.get("hora")}

¡Te esperamos en la barbería!
""".strip()

        resultado = {
            **datos_con_riesgo,
            "disponibilidad": "disponible",
            "estado_operacion": "creada",
            "evento_id": resultado_calendar.get("evento_id"),
            "respuesta_final": respuesta,
            "fecha_finalizacion": obtener_fecha_actual_colombia(),
            "resultado_cita": "pendiente",
            "estado_cita": "activa",
            "tiempo_respuesta_ms": calcular_tiempo_respuesta(datos["inicio_ms"]),
        }

        return resultado

    respuesta = """
Lo siento, ese horario ya está ocupado 😕.

Por favor dime otra fecha u otra hora para revisar disponibilidad.
""".strip()

    resultado = {
        **datos_con_riesgo,
        "disponibilidad": "ocupado",
        "estado_operacion": "no_creada_horario_ocupado",
        "evento_id": None,
        "respuesta_final": respuesta,
        "fecha_finalizacion": obtener_fecha_actual_colombia(),
        "resultado_cita": "pendiente",
        "estado_cita": "sin_agendar",
        "tiempo_respuesta_ms": calcular_tiempo_respuesta(datos["inicio_ms"]),
    }

    return resultado


def manejar_cancelacion(datos):
    """
    Maneja la intención cancelar.
    Busca una cita activa por chat_id y elimina el evento real en Google Calendar.
    El historial de la operación se conserva en Google Sheets.
    """

    resultado_calendar = cancelar_cita_calendar(
        chat_id=datos["chat_id"],
        mensaje_cliente=datos.get("mensaje_cliente", ""),
    )

    if resultado_calendar.get("ok"):
        respuesta = "Listo ✅ Tu cita fue cancelada correctamente."

        resultado = {
            **datos,
            "disponibilidad": "no_aplica",
            "estado_operacion": resultado_calendar.get(
                "estado_operacion",
                "cancelada_eliminada_calendar",
            ),
            "evento_id": resultado_calendar.get("evento_id"),
            "riesgo_num": 0,
            "riesgo_categoria": "no_aplica",
            "accion_racional": "eliminar cita activa en calendar",
            "respuesta_final": respuesta,
            "fecha_finalizacion": obtener_fecha_actual_colombia(),
            "resultado_cita": "cancelada",
            "estado_cita": "cancelada",
            "tiempo_respuesta_ms": calcular_tiempo_respuesta(datos["inicio_ms"]),
        }

        return resultado

    respuesta = (
        "No encontré una cita activa asociada a tu chat. "
        "Si quieres, puedes enviarme fecha y hora de la cita para revisarlo."
    )

    resultado = {
        **datos,
        "disponibilidad": "no_aplica",
        "estado_operacion": resultado_calendar.get(
            "estado_operacion",
            "no_existe_cita",
        ),
        "evento_id": None,
        "riesgo_num": 0,
        "riesgo_categoria": "no_aplica",
        "accion_racional": "informar que no existe cita activa",
        "respuesta_final": respuesta,
        "fecha_finalizacion": obtener_fecha_actual_colombia(),
        "resultado_cita": "no_aplica",
        "estado_cita": "no_encontrada",
        "tiempo_respuesta_ms": calcular_tiempo_respuesta(datos["inicio_ms"]),
    }

    return resultado


def manejar_cambio_hora(datos):
    """
    Maneja la intención cambiar_hora.
    Busca cita activa por chat_id y la mueve a nueva_fecha/nueva_hora.
    """

    nueva_fecha = datos.get("nueva_fecha") or datos.get("fecha")
    nueva_hora = datos.get("nueva_hora") or datos.get("hora")

    if not nueva_fecha or not nueva_hora:
        respuesta = (
            datos.get("respuesta_sugerida")
            or "Claro, puedo cambiar tu cita. ¿Para qué fecha y hora quieres moverla?"
        )

        resultado = {
            **datos,
            "nueva_fecha": nueva_fecha,
            "nueva_hora": nueva_hora,
            "disponibilidad": "no_consultada",
            "estado_operacion": "datos_incompletos_cambio",
            "evento_id": None,
            "riesgo_num": 0,
            "riesgo_categoria": "no_aplica",
            "accion_racional": "pedir nueva fecha y hora",
            "respuesta_final": respuesta,
            "fecha_finalizacion": obtener_fecha_actual_colombia(),
            "resultado_cita": "pendiente",
            "estado_cita": "activa",
            "tiempo_respuesta_ms": calcular_tiempo_respuesta(datos["inicio_ms"]),
        }

        return resultado

    resultado_calendar = cambiar_hora_cita_calendar(
        chat_id=datos["chat_id"],
        nueva_fecha=nueva_fecha,
        nueva_hora=nueva_hora,
        mensaje_cliente=datos.get("mensaje_cliente", ""),
    )

    if resultado_calendar.get("ok"):
        respuesta = f"""
Listo ✅ Tu cita fue cambiada.

Nueva fecha: {nueva_fecha}
Nueva hora: {nueva_hora}

¡Te esperamos!
""".strip()

        resultado = {
            **datos,
            "nueva_fecha": nueva_fecha,
            "nueva_hora": nueva_hora,
            "disponibilidad": resultado_calendar.get("disponibilidad", "disponible"),
            "estado_operacion": resultado_calendar.get(
                    "estado_operacion",
                    "actualizada_calendar",
            ),
            "evento_id": resultado_calendar.get("evento_id"),
            "riesgo_num": 0,
            "riesgo_categoria": "no_aplica",
            "accion_racional": "actualizar cita en calendar si hay disponibilidad",
            "respuesta_final": respuesta,
            "fecha_finalizacion": obtener_fecha_actual_colombia(),
            "resultado_cita": "reprogramada",
            "estado_cita": "activa",
            "tiempo_respuesta_ms": calcular_tiempo_respuesta(datos["inicio_ms"]),
        }

        return resultado

    estado = resultado_calendar.get("estado_operacion")

    if estado == "no_cambiada_horario_ocupado":
        respuesta = (
            "Lo siento, ese nuevo horario ya está ocupado 😕. "
            "Dime otra fecha u hora para revisar disponibilidad."
        )
    elif estado == "no_existe_cita":
        respuesta = (
            "No encontré una cita activa asociada a tu chat. "
            "Primero debes tener una cita agendada."
        )
    else:
        respuesta = (
            "No pude cambiar la cita. "
            "Por favor verifica la fecha y hora e inténtalo de nuevo."
        )

    resultado = {
        **datos,
        "nueva_fecha": nueva_fecha,
        "nueva_hora": nueva_hora,
        "disponibilidad": resultado_calendar.get("disponibilidad", "no_aplica"),
        "estado_operacion": estado or "error_cambio_hora",
        "evento_id": resultado_calendar.get("evento_id"),
        "riesgo_num": 0,
        "riesgo_categoria": "no_aplica",
        "accion_racional": "informar que no se pudo cambiar la cita",
        "respuesta_final": respuesta,
        "fecha_finalizacion": obtener_fecha_actual_colombia(),
        "resultado_cita": "pendiente",
        "estado_cita": "activa",
        "tiempo_respuesta_ms": calcular_tiempo_respuesta(datos["inicio_ms"]),
    }

    return resultado


def procesar_mensaje_barberbot(
    mensaje_cliente,
    chat_id="123456789",
    nombre_cliente="Cliente",
):
    """
    Función principal del agente BarberBot.

    Esta función representa el flujo completo:

    1. Recibe mensaje del cliente.
    2. Usa ChatOpenAI + ChatPromptTemplate + JsonOutputParser.
    3. Interpreta intención.
    4. Ejecuta herramientas según la intención.
    5. Integra lógica difusa.
    6. Registra en Google Sheets.
    7. Devuelve respuesta final.
    """

    load_dotenv()

    inicio_ms = obtener_timestamp_ms()

    llm = crear_llm()
    cadena_interpretacion = crear_cadena_interpretacion(llm)

    interpretacion_llm = cadena_interpretacion.invoke(
        {
            "mensaje_cliente": mensaje_cliente,
            "fecha_actual_colombia": obtener_fecha_actual_colombia(),
        }
    )

    interpretacion = normalizar_interpretacion(interpretacion_llm)

    datos = preparar_datos_base(
        chat_id=chat_id,
        nombre_cliente=nombre_cliente,
        mensaje_cliente=mensaje_cliente,
        interpretacion=interpretacion,
        inicio_ms=inicio_ms,
    )

    intencion = datos.get("intencion")

    if intencion == "reservar":
        resultado = manejar_reserva(datos)

    elif intencion == "precios":
        resultado = construir_respuesta_precios(datos)

    elif intencion == "horarios":
        resultado = construir_respuesta_horarios(datos)

    elif intencion == "cancelar":
        resultado = manejar_cancelacion(datos)

    elif intencion == "cambiar_hora":
        resultado = manejar_cambio_hora(datos)

    else:
        resultado = construir_respuesta_desconocido(datos)

    resultado = registrar_log_seguro(resultado)

    return resultado


def imprimir_resultado(resultado):
    """
    Muestra en consola el resultado completo y la respuesta al cliente.
    """

    print("\n=== Respuesta para el cliente ===")
    print(resultado.get("respuesta_final"))

    print("\n=== JSON final del agente ===")
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    load_dotenv()

    print("=== BarberBot | Agente LangChain ===")
    print("Ejemplos:")
    print("- quiero un corte con barba mañana a las 3 pm")
    print("- cuánto cuesta el corte")
    print("- qué horarios manejan")
    print("- quiero cancelar mi cita")
    print("- quiero cambiar mi cita para mañana a las 4 pm")
    print()

    mensaje = input("Cliente: ").strip()

    if not mensaje:
        print("Error: el mensaje no puede estar vacío.")
        raise SystemExit(1)

    chat_id = input("Chat ID de prueba: ").strip() or "123456789"
    nombre = input("Nombre cliente: ").strip() or "Cliente prueba"

    try:
        resultado_final = procesar_mensaje_barberbot(
            mensaje_cliente=mensaje,
            chat_id=chat_id,
            nombre_cliente=nombre,
        )

        imprimir_resultado(resultado_final)

    except Exception as error:
        print("\nError ejecutando BarberBot:")
        print(error)
