import json
import os
import time
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from agent import procesar_mensaje_barberbot


ZONA_COLOMBIA = ZoneInfo("America/Bogota")
CARPETA_LOGS = Path("logs")


def ahora_colombia():
    return datetime.now(ZONA_COLOMBIA).isoformat(timespec="seconds")


def crear_run_id():
    return datetime.now(ZONA_COLOMBIA).strftime("%Y%m%d_%H%M%S")


def log_paso(numero, mensaje):
    print(f"[LOG {numero:02d}] {mensaje}")


def guardar_log_local(run_id, datos):
    """
    Guarda el resultado completo en un archivo JSON local.
    Esto sirve para evidenciar logs.
    """

    CARPETA_LOGS.mkdir(exist_ok=True)

    ruta_log = CARPETA_LOGS / f"barberbot_run_{run_id}.json"

    with open(ruta_log, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2, default=str)

    return ruta_log


def validar_entorno():
    """
    Revisa variables mínimas del .env sin imprimir secretos.
    """

    errores = []
    advertencias = []

    if not os.getenv("OPENAI_API_KEY"):
        errores.append("Falta OPENAI_API_KEY en el archivo .env")

    if not os.getenv("OPENAI_MODEL"):
        advertencias.append("No se encontró OPENAI_MODEL. Se usará el modelo por defecto de agent.py")

    if not os.getenv("GOOGLE_SHEETS_CREDENTIALS"):
        advertencias.append("Falta GOOGLE_SHEETS_CREDENTIALS. Sheets puede fallar.")

    if not os.getenv("GOOGLE_SHEET_ID"):
        advertencias.append("Falta GOOGLE_SHEET_ID. Sheets puede fallar.")

    if not os.getenv("GOOGLE_SHEET_NAME"):
        advertencias.append("Falta GOOGLE_SHEET_NAME. Sheets puede fallar.")

    if not os.getenv("GOOGLE_CALENDAR_CREDENTIALS"):
        advertencias.append("Falta GOOGLE_CALENDAR_CREDENTIALS. Calendar usará GOOGLE_SHEETS_CREDENTIALS si existe.")

    if not os.getenv("GOOGLE_CALENDAR_ID"):
        advertencias.append("Falta GOOGLE_CALENDAR_ID. Reservas, cancelaciones y cambios pueden fallar.")

    credenciales_sheets = os.getenv("GOOGLE_SHEETS_CREDENTIALS")

    if credenciales_sheets and not Path(credenciales_sheets).exists():
        advertencias.append(f"No existe el archivo de credenciales: {credenciales_sheets}")

    return errores, advertencias


def imprimir_configuracion_segura():
    """
    Muestra configuración útil sin exponer claves privadas.
    """

    print("=== Configuración detectada ===")
    print(f"OPENAI_MODEL: {os.getenv('OPENAI_MODEL', 'no definido')}")
    print(f"GOOGLE_SHEET_NAME: {os.getenv('GOOGLE_SHEET_NAME', 'no definido')}")
    print(f"GOOGLE_CALENDAR_ID: {os.getenv('GOOGLE_CALENDAR_ID', 'no definido')}")
    print()


def imprimir_ejemplos():
    print("Ejemplos para probar:")
    print("- quiero un corte con barba mañana a las 3 pm")
    print("- cuánto cuesta el corte")
    print("- qué horarios manejan")
    print("- quiero cancelar mi cita")
    print("- quiero cambiar mi cita para mañana a las 4 pm")
    print()


def imprimir_resumen_resultado(resultado):
    """
    Muestra un resumen legible.
    """

    print("\n=== Respuesta para el cliente ===")
    print(resultado.get("respuesta_final", "Sin respuesta_final"))

    print("\n=== Resumen operativo ===")
    print(f"Intención: {resultado.get('intencion')}")
    print(f"Servicio: {resultado.get('servicio')}")
    print(f"Fecha: {resultado.get('fecha')}")
    print(f"Hora: {resultado.get('hora')}")
    print(f"Nueva fecha: {resultado.get('nueva_fecha')}")
    print(f"Nueva hora: {resultado.get('nueva_hora')}")
    print(f"Disponibilidad: {resultado.get('disponibilidad')}")
    print(f"Estado operación: {resultado.get('estado_operacion')}")
    print(f"Evento ID: {resultado.get('evento_id')}")
    print(f"Riesgo numérico: {resultado.get('riesgo_num')}")
    print(f"Riesgo categoría: {resultado.get('riesgo_categoria')}")
    print(f"Acción racional: {resultado.get('accion_racional')}")
    print(f"Tiempo respuesta ms: {resultado.get('tiempo_respuesta_ms')}")
    print(f"Log Sheets: {resultado.get('log_sheets')}")


def main():
    load_dotenv()

    run_id = crear_run_id()
    inicio = time.perf_counter()

    print("==========================================")
    print(" BarberBot | LangChain Nivel 2 - Demo CLI ")
    print("==========================================")
    print(f"Run ID: {run_id}")
    print(f"Fecha actual Colombia: {ahora_colombia()}")
    print()

    log_paso(1, "Cargando variables de entorno desde .env")
    errores, advertencias = validar_entorno()

    for advertencia in advertencias:
        print(f"[ADVERTENCIA] {advertencia}")

    if errores:
        print("\n[ERROR] No se puede continuar:")
        for error in errores:
            print(f"- {error}")
        return

    log_paso(2, "Variables mínimas verificadas")
    imprimir_configuracion_segura()

    imprimir_ejemplos()

    mensaje_cliente = input("Cliente: ").strip()

    if not mensaje_cliente:
        print("[ERROR] El mensaje del cliente no puede estar vacío.")
        return

    chat_id = input("Chat ID de prueba: ").strip() or "123456789"
    nombre_cliente = input("Nombre del cliente: ").strip() or "Cliente prueba"

    print()
    log_paso(3, "Mensaje recibido")
    print(f"Cliente: {nombre_cliente}")
    print(f"Chat ID: {chat_id}")
    print(f"Mensaje: {mensaje_cliente}")

    try:
        log_paso(4, "Ejecutando agente BarberBot")
        log_paso(5, "El agente usará LLM, prompt, parser, lógica difusa, Calendar y Sheets según la intención")

        resultado = procesar_mensaje_barberbot(
            mensaje_cliente=mensaje_cliente,
            chat_id=chat_id,
            nombre_cliente=nombre_cliente,
        )

        duracion_total = round((time.perf_counter() - inicio) * 1000)

        resultado["run_id"] = run_id
        resultado["duracion_total_main_ms"] = duracion_total
        resultado["fecha_log_local"] = ahora_colombia()

        log_paso(6, "Agente finalizado correctamente")
        imprimir_resumen_resultado(resultado)

        log_paso(7, "Guardando log local JSON")
        ruta_log = guardar_log_local(run_id, resultado)

        print("\n=== Log local guardado ===")
        print(ruta_log)

        print("\n=== JSON final completo ===")
        print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))

    except Exception as error:
        duracion_total = round((time.perf_counter() - inicio) * 1000)

        datos_error = {
            "run_id": run_id,
            "fecha_error": ahora_colombia(),
            "mensaje_cliente": mensaje_cliente,
            "chat_id": chat_id,
            "nombre_cliente": nombre_cliente,
            "error": str(error),
            "traceback": traceback.format_exc(),
            "duracion_total_main_ms": duracion_total,
        }

        print("\n[ERROR] Falló la ejecución de BarberBot")
        print(error)

        print("\n=== Detalle técnico ===")
        print(traceback.format_exc())

        ruta_log = guardar_log_local(run_id, datos_error)

        print("\n=== Log de error guardado ===")
        print(ruta_log)


if __name__ == "__main__":
    main()
