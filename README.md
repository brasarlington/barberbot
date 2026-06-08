## Workflow de N8n



El archivo público del flujo se encuentra en:



`n8n/barberbot\_workflow\_public.json`



Este archivo contiene la versión sanitizada del workflow de BarberBot en N8n. El flujo permite recibir mensajes desde Telegram, interpretar la intención del cliente con un modelo de lenguaje, consultar disponibilidad en Google Calendar, crear, cancelar o reprogramar citas, registrar resultados en Google Sheets y aplicar una lógica de riesgo para apoyar la toma de decisiones.



Por seguridad, no se incluye el workflow original exportado desde N8n, ya que puede contener credenciales, webhooks, correos, IDs de calendario, IDs de Google Sheets y URLs privadas.



Antes de importar el flujo, se deben reemplazar los siguientes placeholders:



\- `TELEGRAM\_CREDENTIAL\_HERE`

\- `OPENAI\_CREDENTIAL\_HERE`

\- `GOOGLE\_CALENDAR\_CREDENTIAL\_HERE`

\- `GOOGLE\_SHEETS\_CREDENTIAL\_HERE`

\- `CALENDAR\_ID\_HERE`

\- `GOOGLE\_SHEET\_ID\_HERE`

\- `GOOGLE\_SHEET\_URL\_HERE`

\- `WEBHOOK\_ID\_HERE`



Para más detalle sobre cómo reconstruir el flujo, revisar:



`docs/n8n\_workflow.md`

