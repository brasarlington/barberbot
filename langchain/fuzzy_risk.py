# langchain/fuzzy_risk.py

from datetime import datetime
from zoneinfo import ZoneInfo


ZONA_COLOMBIA = ZoneInfo("America/Bogota")


def limitar(valor, minimo=0.0, maximo=1.0):
    """
    Limita un valor numérico dentro de un rango.
    Por defecto, lo limita entre 0 y 1.
    """
    return max(minimo, min(maximo, valor))


def bajo(x, a, b):
    """
    Función de pertenencia difusa tipo 'bajo'.

    - Si x <= a, pertenece totalmente al conjunto bajo.
    - Si x >= b, no pertenece al conjunto bajo.
    - Entre a y b, baja linealmente.
    """
    if x <= a:
        return 1.0
    if x >= b:
        return 0.0
    return (b - x) / (b - a)


def alto(x, a, b):
    """
    Función de pertenencia difusa tipo 'alto'.

    - Si x <= a, no pertenece al conjunto alto.
    - Si x >= b, pertenece totalmente al conjunto alto.
    - Entre a y b, sube linealmente.
    """
    if x <= a:
        return 0.0
    if x >= b:
        return 1.0
    return (x - a) / (b - a)


def triangular(x, a, b, c):
    """
    Función de pertenencia triangular.

    - Vale 0 antes de a.
    - Vale 1 en b.
    - Vale 0 después de c.
    """
    if x <= a or x >= c:
        return 0.0
    if x == b:
        return 1.0
    if x < b:
        return (x - a) / (b - a)
    return (c - x) / (c - b)


def calcular_anticipacion_horas(fecha, hora, ahora=None):
    """
    Calcula cuántas horas faltan para la cita.

    fecha: formato YYYY-MM-DD
    hora: formato HH:mm
    """

    if not fecha or not hora:
        return 0

    ahora = ahora or datetime.now(ZONA_COLOMBIA)

    hora_limpia = str(hora).strip()[:5]

    try:
        inicio_cita = datetime.fromisoformat(f"{fecha}T{hora_limpia}:00")
        inicio_cita = inicio_cita.replace(tzinfo=ZONA_COLOMBIA)
    except ValueError:
        return 0

    diferencia = inicio_cita - ahora
    horas = round(diferencia.total_seconds() / 3600)

    return max(0, horas)


def obtener_hora_cita(hora):
    """
    Extrae la hora como número entero.
    Ejemplo:
    '15:30' -> 15
    """
    if not hora:
        return 0

    try:
        return int(str(hora).strip()[:2])
    except ValueError:
        return 0


def calcular_confirmacion_cliente(servicio, fecha, hora):
    """
    Calcula qué tan completa está la solicitud del cliente.

    No es una simulación: se calcula con los datos reales extraídos por el LLM.
    Mientras más completa esté la solicitud, mayor confirmación.
    """

    puntaje = 0.2

    if servicio:
        puntaje += 0.2

    if fecha:
        puntaje += 0.3

    if hora:
        puntaje += 0.3

    return round(limitar(puntaje), 2)


def calcular_historial_cliente(registros_cliente):
    """
    Calcula el historial del cliente usando registros reales de Google Sheets.

    Esta función todavía no se conecta a Sheets directamente.
    Eso lo hacemos en tools_sheets.py.

    Aquí solo recibe una lista de filas ya leídas desde Sheets.

    Cada registro puede tener campos como:
    - resultado_cita
    - estado_cita

    Valores esperados:
    - asistio
    - no_show
    - cancelada_tarde
    - cancelada_a_tiempo
    - reprogramada
    - pendiente
    """

    valor_neutral = 0.6

    asistencias = 0
    no_shows = 0
    canceladas_tarde = 0
    canceladas_a_tiempo = 0
    reprogramadas = 0
    pendientes = 0

    puntaje_total = 0.0
    eventos_evaluables = 0

    for registro in registros_cliente:
        resultado = str(registro.get("resultado_cita", "")).strip().lower()
        estado = str(registro.get("estado_cita", "")).strip().lower()

        texto = f"{resultado} {estado}"

        if "pendiente" in texto:
            pendientes += 1
            continue

        if "no_show" in texto or "no show" in texto or "no_asistio" in texto:
            no_shows += 1
            puntaje_total += 0.0
            eventos_evaluables += 1

        elif "cancelada_tarde" in texto or "cancelada tarde" in texto:
            canceladas_tarde += 1
            puntaje_total += 0.3
            eventos_evaluables += 1

        elif "cancelada_a_tiempo" in texto or "cancelada a tiempo" in texto:
            canceladas_a_tiempo += 1
            puntaje_total += 0.7
            eventos_evaluables += 1

        elif "reprogramada" in texto or "cambiada" in texto:
            reprogramadas += 1
            puntaje_total += 0.8
            eventos_evaluables += 1

        elif "asistio" in texto or "asistió" in texto or "cumplida" in texto:
            asistencias += 1
            puntaje_total += 1.0
            eventos_evaluables += 1

        else:
            pendientes += 1

    if eventos_evaluables == 0:
        cumplimiento_observado = None
    else:
        cumplimiento_observado = puntaje_total / eventos_evaluables

    # Igual que en N8n: si hay pocas citas evaluables,
    # no se confía totalmente en el historial.
    confianza_historial = min(1.0, eventos_evaluables / 5)

    if cumplimiento_observado is None:
        historial_cliente = valor_neutral
    else:
        historial_cliente = (
            valor_neutral * (1 - confianza_historial)
            + cumplimiento_observado * confianza_historial
        )

    historial_cliente = round(limitar(historial_cliente), 2)

    return {
        "historial_cliente": historial_cliente,
        "historial_confianza": round(confianza_historial, 2),
        "historial_eventos_evaluables": eventos_evaluables,
        "historial_asistencias": asistencias,
        "historial_no_shows": no_shows,
        "historial_canceladas_tarde": canceladas_tarde,
        "historial_canceladas_a_tiempo": canceladas_a_tiempo,
        "historial_reprogramadas": reprogramadas,
        "historial_pendientes": pendientes,
    }


def calcular_riesgo_difuso(datos_cita):
    """
    Calcula el riesgo operativo de no asistencia.

    Entrada esperada:
    {
        "fecha": "2026-06-08",
        "hora": "15:00",
        "servicio": "corte_barba",
        "duracion": 45,
        "historial_cliente": 0.8,
        "historial_confianza": 0.6
    }

    Retorna los mismos datos originales + los campos de riesgo.
    """

    fecha = datos_cita.get("fecha")
    hora = datos_cita.get("hora")
    servicio = datos_cita.get("servicio")
    duracion = int(datos_cita.get("duracion") or 30)

    anticipacion_horas = calcular_anticipacion_horas(fecha, hora)
    hora_cita = obtener_hora_cita(hora)

    historial_cliente = datos_cita.get("historial_cliente", 0.6)
    historial_cliente = float(historial_cliente or 0.6)
    historial_cliente = limitar(historial_cliente)

    historial_confianza = datos_cita.get("historial_confianza", 0.0)
    historial_confianza = float(historial_confianza or 0.0)
    historial_confianza = limitar(historial_confianza)

    confirmacion_cliente = datos_cita.get("confirmacion_cliente")

    if confirmacion_cliente is None:
        confirmacion_cliente = calcular_confirmacion_cliente(servicio, fecha, hora)
    else:
        confirmacion_cliente = float(confirmacion_cliente)

    confirmacion_cliente = limitar(confirmacion_cliente)

    # Variable 1: anticipación de la cita
    anticipacion_baja = bajo(anticipacion_horas, 6, 24)
    anticipacion_media = triangular(anticipacion_horas, 12, 48, 96)
    anticipacion_alta = alto(anticipacion_horas, 48, 120)

    # Variable 2: historial del cliente
    historial_malo = bajo(historial_cliente, 0.3, 0.6)
    historial_regular = triangular(historial_cliente, 0.4, 0.6, 0.8)
    historial_bueno = alto(historial_cliente, 0.6, 0.9)

    # Variable 3: confirmación del cliente
    confirmacion_baja = bajo(confirmacion_cliente, 0.3, 0.6)
    confirmacion_media = triangular(confirmacion_cliente, 0.4, 0.6, 0.8)
    confirmacion_alta = alto(confirmacion_cliente, 0.6, 0.9)

    # Variable 4: hora de la cita
    # Desde las 4 p.m. empieza a considerarse de alta demanda.
    hora_alta_demanda = alto(hora_cita, 16, 19)

    # Variable 5: duración
    # Citas largas bloquean más tiempo.
    duracion_larga = alto(duracion, 45, 90)

    # Reglas de riesgo alto
    regla_riesgo_alto_1 = min(anticipacion_baja, historial_malo)
    regla_riesgo_alto_2 = min(confirmacion_baja, duracion_larga)
    regla_riesgo_alto_3 = min(hora_alta_demanda, confirmacion_baja)
    regla_riesgo_alto_4 = min(historial_malo, duracion_larga)

    # Reglas de riesgo medio
    regla_riesgo_medio_1 = min(anticipacion_media, historial_regular)
    regla_riesgo_medio_2 = min(confirmacion_media, duracion_larga)
    regla_riesgo_medio_3 = min(hora_alta_demanda, historial_regular)

    # Reglas de riesgo bajo
    regla_riesgo_bajo_1 = min(anticipacion_alta, historial_bueno)
    regla_riesgo_bajo_2 = min(confirmacion_alta, historial_bueno)
    regla_riesgo_bajo_3 = min(anticipacion_alta, confirmacion_alta)

    # Agregación de reglas
    riesgo_bajo = max(
        regla_riesgo_bajo_1,
        regla_riesgo_bajo_2,
        regla_riesgo_bajo_3,
    )

    riesgo_medio = max(
        regla_riesgo_medio_1,
        regla_riesgo_medio_2,
        regla_riesgo_medio_3,
    )

    riesgo_alto = max(
        regla_riesgo_alto_1,
        regla_riesgo_alto_2,
        regla_riesgo_alto_3,
        regla_riesgo_alto_4,
    )

    # Defuzzificación por promedio ponderado
    # Bajo = 0.20
    # Medio = 0.50
    # Alto = 0.85
    numerador = (
        riesgo_bajo * 0.20
        + riesgo_medio * 0.50
        + riesgo_alto * 0.85
    )

    denominador = riesgo_bajo + riesgo_medio + riesgo_alto

    if denominador == 0:
        riesgo_num = 0.30
    else:
        riesgo_num = numerador / denominador

    riesgo_num = round(riesgo_num, 2)

    if riesgo_num < 0.35:
        riesgo_categoria = "bajo"
        accion_racional = "crear cita normalmente"
    elif riesgo_num < 0.65:
        riesgo_categoria = "medio"
        accion_racional = "crear cita y enviar recordatorio"
    else:
        riesgo_categoria = "alto"
        accion_racional = "pedir doble confirmacion o alertar administrador"

    return {
        **datos_cita,

        "anticipacion_horas": anticipacion_horas,
        "historial_cliente": round(historial_cliente, 2),
        "historial_confianza": round(historial_confianza, 2),
        "confirmacion_cliente": round(confirmacion_cliente, 2),
        "hora_cita": hora_cita,
        "duracion": duracion,

        "anticipacion_baja": round(anticipacion_baja, 2),
        "anticipacion_media": round(anticipacion_media, 2),
        "anticipacion_alta": round(anticipacion_alta, 2),

        "historial_malo": round(historial_malo, 2),
        "historial_regular": round(historial_regular, 2),
        "historial_bueno": round(historial_bueno, 2),

        "confirmacion_baja": round(confirmacion_baja, 2),
        "confirmacion_media": round(confirmacion_media, 2),
        "confirmacion_alta": round(confirmacion_alta, 2),

        "hora_alta_demanda": round(hora_alta_demanda, 2),
        "duracion_larga": round(duracion_larga, 2),

        "riesgo_bajo": round(riesgo_bajo, 2),
        "riesgo_medio": round(riesgo_medio, 2),
        "riesgo_alto": round(riesgo_alto, 2),

        "riesgo_num": riesgo_num,
        "riesgo_categoria": riesgo_categoria,
        "accion_racional": accion_racional,
    }


if __name__ == "__main__":
    datos_prueba = {
        "chat_id": 123456,
        "nombre_cliente": "Cliente prueba",
        "mensaje_cliente": "Quiero un corte con barba mañana a las 3 pm",
        "intencion": "reservar",
        "servicio": "corte_barba",
        "fecha": "2026-06-08",
        "hora": "15:00",
        "duracion": 45,
        "historial_cliente": 0.8,
        "historial_confianza": 0.6,
    }

    resultado = calcular_riesgo_difuso(datos_prueba)

    print("Riesgo numérico:", resultado["riesgo_num"])
    print("Categoría:", resultado["riesgo_categoria"])
    print("Acción racional:", resultado["accion_racional"])
