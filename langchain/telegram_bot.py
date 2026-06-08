import asyncio
import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agent import procesar_mensaje_barberbot


ZONA_COLOMBIA = ZoneInfo("America/Bogota")
CARPETA_LOGS = Path("logs")


def ahora_colombia():
    return datetime.now(ZONA_COLOMBIA).isoformat(timespec="seconds")


def crear_run_id():
    return datetime.now(ZONA_COLOMBIA).strftime("%Y%m%d_%H%M%S")


def guardar_log_telegram(run_id, datos):
    """
    Guarda un log local de cada mensaje recibido por Telegram.
    Sirve como evidencia para la defensa del proyecto.
    """

    CARPETA_LOGS.mkdir(exist_ok=True)

    ruta = CARPETA_LOGS / f"telegram_run_{run_id}.json"

    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2, default=str)

    return ruta


def dividir_mensaje(texto, limite=3900):
    """
    Telegram tiene límite de caracteres por mensaje.
    Esta función divide respuestas largas si fuera necesario.
    """

    if not texto:
        return [""]

    partes = []

    for i in range(0, len(texto), limite):
        partes.append(texto[i : i + limite])

    return partes


async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Responde al comando /start.
    """

    mensaje = """
Hola 👋 Soy BarberBot.

Puedo ayudarte con:
- Reservar una cita
- Consultar precios
- Consultar horarios
- Cancelar una cita
- Cambiar la hora de una cita

Ejemplo:
quiero un corte con barba mañana a las 3 pm
""".strip()

    await update.message.reply_text(mensaje)


async def comando_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Responde al comando /help.
    """

    mensaje = """
Ejemplos que puedes probar:

1. quiero un corte mañana a las 3 pm
2. quiero un corte con barba mañana a las 4
3. cuánto cuesta el corte
4. qué horarios manejan
5. quiero cancelar mi cita
6. quiero cambiar mi cita para mañana a las 5 pm
""".strip()

    await update.message.reply_text(mensaje)


async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Recibe un mensaje real de Telegram y lo procesa con agent.py.

    Flujo:
    Telegram -> procesar_mensaje_barberbot() -> respuesta_final -> Telegram
    """

    run_id = crear_run_id()

    chat_id = str(update.effective_chat.id)
    usuario = update.effective_user

    nombre_cliente = (
        usuario.first_name
        or usuario.full_name
        or update.effective_chat.first_name
        or "Cliente"
    )

    mensaje_cliente = update.message.text.strip()

    print("\n==========================================")
    print(" BarberBot | Mensaje recibido por Telegram")
    print("==========================================")
    print(f"Run ID: {run_id}")
    print(f"Fecha: {ahora_colombia()}")
    print(f"Chat ID: {chat_id}")
    print(f"Cliente: {nombre_cliente}")
    print(f"Mensaje: {mensaje_cliente}")
    print()

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )

    try:
        # procesar_mensaje_barberbot es síncrona.
        # asyncio.to_thread evita bloquear el bot mientras se ejecuta OpenAI,
        # Google Calendar y Google Sheets.
        resultado = await asyncio.to_thread(
            procesar_mensaje_barberbot,
            mensaje_cliente=mensaje_cliente,
            chat_id=chat_id,
            nombre_cliente=nombre_cliente,
        )

        respuesta_final = resultado.get(
            "respuesta_final",
            "Listo, procesé tu solicitud.",
        )

        resultado["run_id"] = run_id
        resultado["origen"] = "telegram"
        resultado["fecha_log_telegram"] = ahora_colombia()

        ruta_log = guardar_log_telegram(run_id, resultado)

        print("[OK] Mensaje procesado")
        print(f"Intención: {resultado.get('intencion')}")
        print(f"Estado operación: {resultado.get('estado_operacion')}")
        print(f"Evento ID: {resultado.get('evento_id')}")
        print(f"Riesgo: {resultado.get('riesgo_categoria')} ({resultado.get('riesgo_num')})")
        print(f"Log local: {ruta_log}")

        for parte in dividir_mensaje(respuesta_final):
            await update.message.reply_text(parte)

    except Exception as error:
        datos_error = {
            "run_id": run_id,
            "origen": "telegram",
            "fecha_error": ahora_colombia(),
            "chat_id": chat_id,
            "nombre_cliente": nombre_cliente,
            "mensaje_cliente": mensaje_cliente,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }

        ruta_log = guardar_log_telegram(run_id, datos_error)

        print("[ERROR] Falló BarberBot Telegram")
        print(error)
        print(traceback.format_exc())
        print(f"Log error: {ruta_log}")

        await update.message.reply_text(
            "Ocurrió un error procesando tu solicitud. "
            "Por favor intenta de nuevo en unos minutos."
        )


async def manejar_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Captura errores generales del bot.
    """

    print("\n[ERROR GLOBAL TELEGRAM]")
    print(context.error)
    print(traceback.format_exc())


def validar_entorno():
    """
    Revisa variables necesarias para ejecutar Telegram.
    """

    errores = []

    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        errores.append("Falta TELEGRAM_BOT_TOKEN en .env")

    if not os.getenv("OPENAI_API_KEY"):
        errores.append("Falta OPENAI_API_KEY en .env")

    return errores


def main():
    load_dotenv()

    print("==========================================")
    print(" BarberBot | Adaptador Telegram LangChain ")
    print("==========================================")
    print(f"Fecha actual Colombia: {ahora_colombia()}")
    print()

    errores = validar_entorno()

    if errores:
        print("[ERROR] No se puede iniciar el bot:")
        for error in errores:
            print(f"- {error}")
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", comando_start))
    app.add_handler(CommandHandler("help", comando_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))

    app.add_error_handler(manejar_error)

    print("Bot iniciado correctamente.")
    print("Abre Telegram y escríbele a tu bot.")
    print("Presiona CTRL + C para detenerlo.")
    print()

    app.run_polling()


if __name__ == "__main__":
    main()
