## Workflow de N8n



El archivo público del flujo se encuentra en:



`n8n/barberbot_workflow_public.json`



Este archivo contiene la versión sanitizada del workflow de BarberBot en N8n. El flujo permite recibir mensajes desde Telegram, interpretar la intención del cliente con un modelo de lenguaje, consultar disponibilidad en Google Calendar, crear, cancelar o reprogramar citas, registrar resultados en Google Sheets y aplicar una lógica de riesgo para apoyar la toma de decisiones.



Por seguridad, no se incluye el workflow original exportado desde N8n, ya que puede contener credenciales, webhooks, correos, IDs de calendario, IDs de Google Sheets y URLs privadas.



Antes de importar el flujo, se deben reemplazar los siguientes placeholders:



\- `TELEGRAM_CREDENTIAL_HERE`

\- `OPENAI_CREDENTIAL_HERE`

\- `GOOGLE_CALENDAR_CREDENTIAL_HERE`

\- `GOOGLE_SHEETS_CREDENTIAL_HERE`

\- `CALENDAR_ID_HERE`

\- `GOOGLE_SHEET_ID_HERE`

\- `GOOGLE_SHEET_URL_HERE`

\- `WEBHOOK_ID_HERE`



Para más detalle sobre cómo reconstruir el flujo, revisar:



`docs/n8n_workflow.md`

