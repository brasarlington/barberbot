import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt

from fuzzy_risk import (
    bajo,
    alto,
    triangular,
    calcular_riesgo_difuso,
)


ZONA_COLOMBIA = ZoneInfo("America/Bogota")

CARPETA_OUTPUTS = Path("outputs")
CARPETA_OUTPUTS.mkdir(exist_ok=True)


def fecha_hora_en(horas_desde_ahora):
    """
    Crea una fecha y hora futura a partir de la hora actual en Colombia.
    """

    dt = datetime.now(ZONA_COLOMBIA) + timedelta(hours=horas_desde_ahora)

    # Redondeamos al inicio de la hora para que se vea más limpio.
    dt = dt.replace(minute=0, second=0, microsecond=0)

    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def generar_casos_prueba():
    """
    Casos diseñados para producir riesgos bajos, medios y altos.
    """

    casos_base = [
        {
            "caso": "Cliente confiable",
            "servicio": "corte",
            "duracion": 30,
            "horas_anticipacion": 120,
            "historial_cliente": 0.9,
            "historial_confianza": 1.0,
            "confirmacion_cliente": 1.0,
        },
        {
            "caso": "Cliente nuevo",
            "servicio": "corte",
            "duracion": 30,
            "horas_anticipacion": 48,
            "historial_cliente": 0.6,
            "historial_confianza": 0.0,
            "confirmacion_cliente": 1.0,
        },
        {
            "caso": "Mal historial",
            "servicio": "corte",
            "duracion": 30,
            "horas_anticipacion": 48,
            "historial_cliente": 0.25,
            "historial_confianza": 1.0,
            "confirmacion_cliente": 1.0,
        },
        {
            "caso": "Poca anticipación",
            "servicio": "corte",
            "duracion": 30,
            "horas_anticipacion": 3,
            "historial_cliente": 0.6,
            "historial_confianza": 0.4,
            "confirmacion_cliente": 1.0,
        },
        {
            "caso": "Servicio largo",
            "servicio": "color_cabello",
            "duracion": 90,
            "horas_anticipacion": 48,
            "historial_cliente": 0.6,
            "historial_confianza": 0.4,
            "confirmacion_cliente": 1.0,
        },
        {
            "caso": "Largo y mal historial",
            "servicio": "color_cabello",
            "duracion": 90,
            "horas_anticipacion": 12,
            "historial_cliente": 0.25,
            "historial_confianza": 1.0,
            "confirmacion_cliente": 0.7,
        },
        {
            "caso": "Alta demanda",
            "servicio": "corte_barba",
            "duracion": 45,
            "horas_anticipacion": 30,
            "historial_cliente": 0.55,
            "historial_confianza": 0.6,
            "confirmacion_cliente": 0.7,
        },
        {
            "caso": "Baja confirmación",
            "servicio": None,
            "duracion": 30,
            "horas_anticipacion": 24,
            "historial_cliente": 0.6,
            "historial_confianza": 0.2,
            "confirmacion_cliente": 0.3,
        },
        {
            "caso": "Buen cliente cita cercana",
            "servicio": "barba",
            "duracion": 15,
            "horas_anticipacion": 5,
            "historial_cliente": 0.9,
            "historial_confianza": 1.0,
            "confirmacion_cliente": 1.0,
        },
        {
            "caso": "Mal cliente anticipado",
            "servicio": "corte",
            "duracion": 30,
            "horas_anticipacion": 120,
            "historial_cliente": 0.25,
            "historial_confianza": 1.0,
            "confirmacion_cliente": 1.0,
        },
        {
            "caso": "Riesgo medio típico",
            "servicio": "corte_barba",
            "duracion": 45,
            "horas_anticipacion": 27,
            "historial_cliente": 0.6,
            "historial_confianza": 0.0,
            "confirmacion_cliente": 1.0,
        },
        {
            "caso": "Caso crítico",
            "servicio": "color_cabello",
            "duracion": 90,
            "horas_anticipacion": 2,
            "historial_cliente": 0.2,
            "historial_confianza": 1.0,
            "confirmacion_cliente": 0.3,
        },
    ]

    casos = []

    for caso in casos_base:
        fecha, hora = fecha_hora_en(caso["horas_anticipacion"])

        datos = {
            "caso": caso["caso"],
            "chat_id": "prueba",
            "nombre_cliente": caso["caso"],
            "mensaje_cliente": f"Prueba: {caso['caso']}",
            "intencion": "reservar",
            "servicio": caso["servicio"],
            "fecha": fecha,
            "hora": hora,
            "duracion": caso["duracion"],
            "historial_cliente": caso["historial_cliente"],
            "historial_confianza": caso["historial_confianza"],
            "confirmacion_cliente": caso["confirmacion_cliente"],
        }

        casos.append(datos)

    return casos


def ejecutar_pruebas():
    resultados = []

    for datos in generar_casos_prueba():
        resultado = calcular_riesgo_difuso(datos)
        resultados.append(resultado)

    return resultados


def guardar_csv(resultados):
    ruta = CARPETA_OUTPUTS / "resultados_pruebas_fuzzy.csv"

    columnas = [
        "caso",
        "servicio",
        "fecha",
        "hora",
        "duracion",
        "anticipacion_horas",
        "historial_cliente",
        "historial_confianza",
        "confirmacion_cliente",
        "riesgo_num",
        "riesgo_categoria",
        "accion_racional",
    ]

    with open(ruta, "w", newline="", encoding="utf-8") as archivo:
        writer = csv.DictWriter(archivo, fieldnames=columnas)
        writer.writeheader()

        for resultado in resultados:
            writer.writerow(
                {columna: resultado.get(columna) for columna in columnas}
            )

    return ruta


def grafica_membresia_anticipacion():
    """
    Gráfica de funciones de membresía para anticipación.
    """

    xs = list(range(0, 145))

    anticipacion_baja = [bajo(x, 6, 24) for x in xs]
    anticipacion_media = [triangular(x, 12, 48, 96) for x in xs]
    anticipacion_alta = [alto(x, 48, 120) for x in xs]

    plt.figure(figsize=(9, 5))
    plt.plot(xs, anticipacion_baja, label="Baja")
    plt.plot(xs, anticipacion_media, label="Media")
    plt.plot(xs, anticipacion_alta, label="Alta")

    plt.title("Funciones de membresía para anticipación de la cita")
    plt.xlabel("Horas de anticipación")
    plt.ylabel("Grado de pertenencia")
    plt.legend()
    plt.grid(True, alpha=0.3)

    ruta = CARPETA_OUTPUTS / "grafica_membresia_anticipacion.png"
    plt.savefig(ruta, dpi=300, bbox_inches="tight")
    plt.close()

    return ruta


def grafica_riesgo_por_caso(resultados):
    """
    Gráfico de barras con el riesgo numérico de cada caso.
    """

    casos = [r["caso"] for r in resultados]
    riesgos = [r["riesgo_num"] for r in resultados]

    plt.figure(figsize=(11, 6))
    plt.bar(casos, riesgos)

    plt.title("Riesgo operativo por caso de prueba")
    plt.xlabel("Caso de prueba")
    plt.ylabel("Riesgo numérico")
    plt.ylim(0, 1)
    plt.xticks(rotation=45, ha="right")
    plt.grid(axis="y", alpha=0.3)

    ruta = CARPETA_OUTPUTS / "grafica_riesgo_por_caso.png"
    plt.savefig(ruta, dpi=300, bbox_inches="tight")
    plt.close()

    return ruta


def grafica_distribucion_categorias(resultados):
    """
    Gráfico de barras con cuántos casos quedaron en bajo, medio y alto.
    """

    conteo = {
        "bajo": 0,
        "medio": 0,
        "alto": 0,
    }

    for resultado in resultados:
        categoria = resultado.get("riesgo_categoria", "medio")
        conteo[categoria] = conteo.get(categoria, 0) + 1

    categorias = list(conteo.keys())
    valores = list(conteo.values())

    plt.figure(figsize=(7, 5))
    plt.bar(categorias, valores)

    plt.title("Distribución de categorías de riesgo")
    plt.xlabel("Categoría de riesgo")
    plt.ylabel("Número de casos")
    plt.grid(axis="y", alpha=0.3)

    ruta = CARPETA_OUTPUTS / "grafica_distribucion_riesgo.png"
    plt.savefig(ruta, dpi=300, bbox_inches="tight")
    plt.close()

    return ruta


def main():
    print("Ejecutando pruebas de lógica difusa...")

    resultados = ejecutar_pruebas()

    ruta_csv = guardar_csv(resultados)
    ruta_membresia = grafica_membresia_anticipacion()
    ruta_riesgo = grafica_riesgo_por_caso(resultados)
    ruta_distribucion = grafica_distribucion_categorias(resultados)

    print("\nResultados por caso:")
    for r in resultados:
        print(
            f"- {r['caso']}: riesgo={r['riesgo_num']} "
            f"categoria={r['riesgo_categoria']} "
            f"accion={r['accion_racional']}"
        )

    print("\nArchivos generados:")
    print(ruta_csv)
    print(ruta_membresia)
    print(ruta_riesgo)
    print(ruta_distribucion)


if __name__ == "__main__":
    main()
