import csv
from datetime import datetime

ARCHIVO_ENTRADA = "inventario_cd.csv"
UMBRAL_EXTREMA_URGENCIA = 5


def validar_tipos(registro):
    """
    Convierte los campos numéricos de un producto.

    Retorna:
        es_valido: True si todas las conversiones funcionan.
        registro_convertido: Diccionario con valores convertidos.
        errores: Lista de errores encontrados.
    """

    registro_convertido = registro.copy()
    errores = []

    campos_enteros = [
        "stock_actual",
        "stock_minimo",
        "stock_maximo",
        "demanda_semanal",
        "lead_time_dias"
    ]

    for campo in campos_enteros:
        try:
            registro_convertido[campo] = int(registro[campo])

        except (ValueError, TypeError, KeyError) as error:
            errores.append(
                f"Producto {registro.get('id_producto', 'DESCONOCIDO')}: "
                f"campo '{campo}', valor '{registro.get(campo)}'. "
                f"Error: {error}"
            )

    try:
        registro_convertido["costo_unitario"] = float(
            registro["costo_unitario"]
        )

    except (ValueError, TypeError, KeyError) as error:
        errores.append(
            f"Producto {registro.get('id_producto', 'DESCONOCIDO')}: "
            f"campo 'costo_unitario', valor "
            f"'{registro.get('costo_unitario')}'. Error: {error}"
        )

    es_valido = len(errores) == 0

    return es_valido, registro_convertido, errores


def validar_reglas_negocio(registro):
    """
    Comprueba las reglas operacionales del inventario.

    Retorna:
        es_valido: True si cumple todas las reglas.
        errores: Lista de incumplimientos encontrados.
    """

    errores = []
    id_producto = registro.get("id_producto", "DESCONOCIDO")

    campos_no_negativos = [
        "stock_actual",
        "stock_minimo",
        "stock_maximo",
        "demanda_semanal",
        "lead_time_dias"
    ]

    # RN01: Los campos enteros no pueden ser negativos.
    for campo in campos_no_negativos:
        if registro[campo] < 0:
            errores.append(
                f"{id_producto} - RN01: {campo} no puede ser negativo. "
                f"Valor: {registro[campo]}"
            )

    # RN02: El costo debe ser mayor que cero.
    if registro["costo_unitario"] <= 0:
        errores.append(
            f"{id_producto} - RN02: costo_unitario debe ser positivo."
        )

    # RN03: El stock mínimo no puede superar al máximo.
    if registro["stock_minimo"] > registro["stock_maximo"]:
        errores.append(
            f"{id_producto} - RN03: stock_minimo supera stock_maximo."
        )

    # RN04: El plazo de reposición debe estar entre 1 y 30 días.
    if not 1 <= registro["lead_time_dias"] <= 30:
        errores.append(
            f"{id_producto} - RN04: lead_time_dias fuera de rango."
        )

    # RN05: Categorías permitidas.
    categorias_validas = {
        "Alimentos",
        "Bebestibles",
        "Limpieza",
        "Higiene Personal",
        "Cuidado Mascotas",
        "Lácteos"
    }

    if registro["categoria"] not in categorias_validas:
        errores.append(
            f"{id_producto} - RN05: categoría no permitida: "
            f"{registro['categoria']}"
        )

    # RN06: El proveedor no puede estar vacío.
    if not registro["proveedor"].strip():
        errores.append(
            f"{id_producto} - RN06: proveedor vacío."
        )

    # RN07: Identificador con una letra mayúscula y tres números.
    import re

    if not re.fullmatch(r"[A-Z]\d{3}", registro["id_producto"]):
        errores.append(
            f"{id_producto} - RN07: formato de identificador incorrecto."
        )

    es_valido = len(errores) == 0

    return es_valido, errores


def registrar_errores(errores, archivo="errores.log"):
    """
    Guarda los errores detectados en un archivo de registro.

    Args:
        errores: Lista de mensajes.
        archivo: Nombre del archivo de salida.
    """

    if not errores:
        return 0

    with open(archivo, mode="a", encoding="utf-8") as log:
        for error in errores:
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log.write(f"{fecha} | ERROR | {error}\n")

    return len(errores)


def escribir_csv_salida(ordenes, columnas, archivo_salida="ordenes_compra_urgente_v3.csv"):
    """Guarda las órdenes de compra en un archivo CSV."""

    with open(archivo_salida, mode="w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows(ordenes)

    return len(ordenes)


def calcular_reposicion(stock_actual, stock_maximo, costo_unitario):
    """Calcula las unidades y el costo de reposición."""

    cantidad = stock_maximo - stock_actual
    costo = cantidad * costo_unitario

    return cantidad, costo

def leer_csv(archivo):
    """Prepara la lectura de los registros de un archivo CSV."""
    return csv.DictReader(archivo)

def generar_reporte_consola(validos, invalidos, bajo_stock, sobrestock,
                           normales, unidades, costo):
    """Presenta los indicadores principales del inventario."""

    print("\n===== REPORTE EJECUTIVO V3 =====")
    print(f"Productos válidos: {validos}")
    print(f"Registros descartados: {invalidos}")
    print(f"Productos bajo stock: {bajo_stock}")
    print(f"Productos con sobrestock: {sobrestock}")
    print(f"Productos normales: {normales}")
    print(f"Unidades a reponer: {unidades}")
    print(f"Costo estimado: ${costo:,.0f}")

    return validos
def main():
    """Coordina la validación, el procesamiento y los reportes."""
    # Inicialización de contadores
    total_productos = 0
    total_bajo_stock = 0
    total_sobrestock = 0
    total_stock_normal = 0
    total_registros_invalidos = 0
    errores_detectados = []
    # Acumuladores de reposición
    total_unidades_reponer = 0
    costo_total_reposicion = 0.0
    # Agrupación de resultados
    bajo_stock_por_categoria = {}
    alertas_por_proveedor = {}
    casos_extrema_urgencia = []
    ordenes_compra = []
    registros_inventario = []

    # Lectura del archivo CSV
    with open(ARCHIVO_ENTRADA, mode="r", encoding="utf-8") as archivo:
        lector = leer_csv(archivo)

        for fila in lector:
                    # Validar los tipos de datos
            es_valido, registro_convertido, errores = validar_tipos(fila)

            if not es_valido:
                total_registros_invalidos += 1
                errores_detectados.extend(errores)
                continue

            # Validar las reglas de negocio
            es_valido_negocio, errores_negocio = validar_reglas_negocio(
                registro_convertido
            )

            if not es_valido_negocio:
                total_registros_invalidos += 1
                errores_detectados.extend(errores_negocio)
                continue

            # Utilizar el registro validado
            fila = registro_convertido
            # Conversión de datos
            stock_actual = fila["stock_actual"]
            stock_minimo = fila["stock_minimo"]
            stock_maximo = fila["stock_maximo"]
            demanda_semanal = fila["demanda_semanal"]
            costo_unitario = fila["costo_unitario"]
            categoria = fila["categoria"]
            proveedor = fila["proveedor"]
            lead_time_dias = fila["lead_time_dias"]

            # Almacenar registro del inventario
            registros_inventario.append(fila.copy())

            # Contar cada producto procesado
            total_productos += 1

            # Clasificar el inventario
            if stock_actual < stock_minimo:
                total_bajo_stock += 1

                    # Calcular cantidad necesaria para reponer
                cantidad_a_reponer, costo_reposicion = calcular_reposicion(
                    stock_actual, stock_maximo, costo_unitario
                )

                # Acumular resultados
                total_unidades_reponer += cantidad_a_reponer
                costo_total_reposicion += costo_reposicion
                # Registrar orden de compra
                ordenes_compra.append({
                    "id_producto": fila["id_producto"],
                    "producto": fila["producto"],
                    "cantidad_a_reponer": cantidad_a_reponer,
                    "costo_total_reposicion": round(costo_reposicion, 0),
                    "proveedor": proveedor,
                    "dias_estimados_reposicion": lead_time_dias

                })
                            # Contabilizar productos bajo stock por categoria
                if categoria not in bajo_stock_por_categoria:
                    bajo_stock_por_categoria[categoria] = 0

                bajo_stock_por_categoria[categoria] += 1

                # Contabilizar productos bajo stock por proveedor
                if proveedor not in alertas_por_proveedor:
                    alertas_por_proveedor[proveedor] = 0

                alertas_por_proveedor[proveedor] += 1

                # Identificar productos de extrema urgencia
                if lead_time_dias > UMBRAL_EXTREMA_URGENCIA:
                    casos_extrema_urgencia.append({
                        "id_producto": fila["id_producto"],
                        "producto": fila["producto"]
                        })
            elif stock_actual > stock_maximo:
                total_sobrestock += 1

            else:
                total_stock_normal += 1
    # Guardar los errores detectados
    total_errores_registrados = registrar_errores(errores_detectados)
    # Mostrar resultados
    print("===== RESUMEN DE INVENTARIO =====")
    print(f"Registros inválidos descartados: {total_registros_invalidos}")
    print(f"Total de errores detectados: {len(errores_detectados)}")
    print(f"Productos procesados: {total_productos}")
    print(f"Productos bajo stock: {total_bajo_stock}")
    print(f"Productos con sobrestock: {total_sobrestock}")
    print(f"Productos con stock normal: {total_stock_normal}")
    print(f"Total de unidades a reponer: {total_unidades_reponer}")
    print(f"Costo total de reposición: ${costo_total_reposicion:,.0f}")

    # Identificar categoria mas critica
    categoria_mas_critica = max(
        bajo_stock_por_categoria,
        key=bajo_stock_por_categoria.get
    )

    print(f"Categoria mas critica: {categoria_mas_critica}")

    # Mostrar alertas por proveedor
    print("\n===== ALERTAS POR PROVEEDOR =====")

    for proveedor, cantidad in alertas_por_proveedor.items():
        print(f"{proveedor}: {cantidad} productos")

    # Resumen de extrema urgencia
    print("\n===== EXTREMA URGENCIA =====")
    print(f"Total de productos de extrema urgencia: {len(casos_extrema_urgencia)}")

    for caso in casos_extrema_urgencia:
        print(f"{caso['id_producto']} - {caso['producto']}")
        # Generar archivo de ordenes de compra
    ARCHIVO_SALIDA = "ordenes_compra_urgente_v3.csv"

    columnas_salida = [
        "id_producto",
        "producto",
        "cantidad_a_reponer",
        "costo_total_reposicion",
        "proveedor",
        "dias_estimados_reposicion"
    ]

    escribir_csv_salida(ordenes_compra, columnas_salida, ARCHIVO_SALIDA)

    print("\nArchivo de ordenes de compra generado correctamente.")
    print(f"Total de ordenes registradas: {len(ordenes_compra)}")
    generar_reporte_consola(
        total_productos,
        total_registros_invalidos,
        total_bajo_stock,
        total_sobrestock,
        total_stock_normal,
        total_unidades_reponer,
        costo_total_reposicion
    )


if __name__ == "__main__":
    try:
        main()

    except FileNotFoundError as error:
        mensaje = f"Archivo no encontrado: {error}"
        print(f"ERROR: {mensaje}")
        registrar_errores([mensaje])

    except PermissionError as error:
        mensaje = f"Permiso denegado: {error}"
        print(f"ERROR: {mensaje}")
        try:
            registrar_errores([mensaje])
        except PermissionError:
            print("No fue posible escribir en errores.log")

    except (ValueError, TypeError) as error:
        mensaje = f"Error de datos: {type(error).__name__}: {error}"
        print(f"ERROR: {mensaje}")
        registrar_errores([mensaje])

    finally:
        print("\nProceso finalizado.")