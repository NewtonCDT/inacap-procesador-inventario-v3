"""DIMAULE SpA - Procesador de inventario V3, Unidad 3 INACAP.

Lee inventario_cd.csv, valida cada registro (tipos y reglas RN-01 a RN-07)
sin detenerse ante datos sucios, calcula la reposicion, genera
ordenes_compra_urgente_v3.csv y registra los eventos en errores.log.
Solo biblioteca estandar.

Codigos de salida:
    0 -> proceso completado correctamente.
    1 -> error critico: no se pudo leer el archivo de entrada.
    2 -> proceso completado, pero fallo la escritura del CSV de salida.
    3 -> proceso completado, pero con descartes sobre el umbral permitido.
"""
import csv
import logging
import math
import re
import sys
from pathlib import Path


# =====================================================================
# 1. CONFIGURACION GLOBAL (scope global)
# ---------------------------------------------------------------------
# Estas constantes estan en scope global porque son reglas de negocio y
# parametros fijos, de solo lectura, que usan varias funciones. Asi una
# regla (p. ej. el umbral de urgencia o las categorias) se cambia en un
# solo lugar. Ninguna funcion las modifica: los resultados viajan entre
# funciones mediante parametros y return.
# =====================================================================
BASE = Path(__file__).resolve().parent

# El archivo de entrada puede estar en data/ o junto al script.
_RUTAS_ENTRADA = (BASE / "data" / "inventario_cd.csv", BASE / "inventario_cd.csv")
ARCHIVO_ENTRADA = next((r for r in _RUTAS_ENTRADA if r.exists()), _RUTAS_ENTRADA[0])
ARCHIVO_SALIDA = BASE / "ordenes_compra_urgente_v3.csv"
ARCHIVO_LOG = BASE / "errores.log"
LOGGER = logging.getLogger("dimaule_v3")

UMBRAL_EXTREMA_URGENCIA = 5     # dias de lead time
UMBRAL_DESCARTE = 0.25          # sobre 25 % de descartes -> codigo de salida 3
SOLO_EXTREMA_URGENCIA = False    # True: el CSV lleva solo extrema urgencia;
                                # False: todos los productos bajo stock minimo

CATEGORIAS_VALIDAS = frozenset({
    "Alimentos", "Bebestibles", "Limpieza", "Higiene Personal",
    "Cuidado Mascotas", "Lácteos"
})
# El CSV y el esqueleto de la pauta usan "Mascotas"; RN-05 dice "Cuidado Mascotas".
ALIAS_CATEGORIAS = {"mascotas": "Cuidado Mascotas"}

CAMPOS_ENTEROS = ("stock_actual", "stock_minimo", "stock_maximo", "demanda_semanal", "lead_time_dias")
CAMPOS_TEXTO = ("id_producto", "producto", "categoria", "proveedor")
COLUMNAS_ENTRADA = ("id_producto", "producto", "categoria", *CAMPOS_ENTEROS, "costo_unitario", "proveedor")
COLUMNAS_SALIDA = ("id_producto", "producto", "cantidad_a_reponer", "costo_total_reposicion", "proveedor", "dias_estimados_reposicion")
PATRON_ID = re.compile(r"[A-Z][0-9]{3}")

DESCRIPCION_REGLAS = {
    "TIPO": "dato no convertible al tipo numerico esperado",
    "PROCESAMIENTO": "error inesperado al procesar la fila",
    "RN-01": "valor numerico negativo",
    "RN-02": "costo unitario menor o igual a cero",
    "RN-03": "stock minimo mayor que stock maximo",
    "RN-04": "lead time fuera del rango 1-30 dias",
    "RN-05": "categoria fuera del catalogo permitido",
    "RN-06": "proveedor vacio",
    "RN-07": "formato de id_producto invalido",
}


# =====================================================================
# 2. CONFIGURACION DE LOG
# =====================================================================
def configurar_log(ruta=ARCHIVO_LOG):
    """Configura el registro de eventos (fecha, hora, nivel y mensaje).

    Si el archivo de log no se puede abrir, el programa no se detiene:
    el log pasa a la consola.

    Args:
        ruta (Path): archivo de log. Default: errores.log junto al script.

    Returns:
        str | None: ruta del log, o None si se uso la consola.
    """
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    LOGGER.handlers.clear()
    try:
        handler = logging.FileHandler(ruta, encoding="utf-8")
        destino = str(ruta)
    except OSError as exc:      # sin permisos, ruta invalida, disco lleno
        print(f"ADVERTENCIA: no se pudo abrir {ruta} ({exc}). El log ira a consola.")
        handler = logging.StreamHandler()
        destino = None
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s",
                                           datefmt="%Y-%m-%d %H:%M:%S"))
    LOGGER.addHandler(handler)
    return destino


# =====================================================================
# 3. VALIDACIONES
# =====================================================================
def crear_error(ident, regla, campo, valor, esperado):
    """Arma un mensaje claro: producto, regla, columna, valor recibido y que se esperaba.

    Args:
        ident (str): id_producto afectado.
        regla (str): codigo de la regla (TIPO, RN-01 ... RN-07).
        campo (str): columna involucrada.
        valor: valor recibido.
        esperado (str): descripcion de lo que se esperaba.

    Returns:
        str: mensaje con formato 'id | regla | columna=... | valor recibido=... | esperado'.
    """
    return f"{ident} | {regla} | columna={campo} | valor recibido={valor!r} | {esperado}"


def normalizar_categoria(valor):
    """Normaliza una categoria: quita espacios, ignora mayusculas y corrige alias.

    Args:
        valor (str): categoria tal como viene en el CSV.

    Returns:
        str: nombre oficial si se reconoce; si no, el texto limpio.
    """
    limpio = " ".join(str(valor or "").split())
    clave = limpio.casefold()
    for oficial in CATEGORIAS_VALIDAS:
        if oficial.casefold() == clave:
            return oficial
    return ALIAS_CATEGORIAS.get(clave, limpio)


def validar_tipos(registro):
    """Convierte los campos numericos de una fila cruda.

    ValueError (texto, 'N/A', celda vacia) y TypeError (dato ausente por
    fila incompleta) se capturan por separado y se reportan distinto.

    Args:
        registro (dict): valores leidos del CSV como texto.

    Returns:
        tuple: (es_valido, registro_convertido, errores).
    """
    convertido = registro.copy()
    errores = []
    ident = str(registro.get("id_producto") or "DESCONOCIDO").strip()
    for campo in CAMPOS_ENTEROS:
        valor = registro.get(campo)
        try:
            convertido[campo] = int(valor)
        except ValueError:
            errores.append(crear_error(ident, "TIPO", campo, valor,
                                       "se esperaba un entero (texto no numerico o celda vacia)"))
        except TypeError:
            errores.append(crear_error(ident, "TIPO", campo, valor,
                                       "falta el dato (fila incompleta)"))
    valor = registro.get("costo_unitario")
    try:
        convertido["costo_unitario"] = float(valor)
    except ValueError:
        errores.append(crear_error(ident, "TIPO", "costo_unitario", valor,
                                   "se esperaba un numero (texto no numerico o celda vacia)"))
    except TypeError:
        errores.append(crear_error(ident, "TIPO", "costo_unitario", valor,
                                   "falta el dato (fila incompleta)"))
    return not errores, convertido, errores


def normalizar_registro(registro):
    """Corrige formato en los campos de texto (espacios y alias de categoria).

    Args:
        registro (dict): fila con tipos ya convertidos.

    Returns:
        tuple: (registro_normalizado, correcciones), donde correcciones es
        una lista de mensajes de lo que se corrigio.
    """
    limpio = registro.copy()
    correcciones = []
    ident = str(registro.get("id_producto") or "DESCONOCIDO").strip()
    for campo in CAMPOS_TEXTO:
        original = registro.get(campo)
        if not isinstance(original, str):
            continue
        nuevo = normalizar_categoria(original) if campo == "categoria" else original.strip()
        if nuevo != original:
            limpio[campo] = nuevo
            correcciones.append(f"{ident} | CORRECCION | columna={campo} | {original!r} -> {nuevo!r}")
    return limpio, correcciones


def validar_reglas_negocio(registro):
    """Verifica RN-01 a RN-07 y reporta TODAS las reglas incumplidas.

    Precondicion: el registro ya paso por validar_tipos y normalizar_registro.

    Args:
        registro (dict): fila con tipos convertidos.

    Returns:
        tuple: (es_valido, errores), con codigo de regla, columna y valor recibido.
    """
    ident = str(registro.get("id_producto") or "DESCONOCIDO").strip()
    errores = []
    for campo in CAMPOS_ENTEROS:
        if registro[campo] < 0:
            errores.append(crear_error(ident, "RN-01", campo, registro[campo],
                                       "se esperaba un entero mayor o igual a 0"))
    costo = registro["costo_unitario"]
    if not math.isfinite(costo) or costo <= 0:
        errores.append(crear_error(ident, "RN-02", "costo_unitario", costo,
                                   "se esperaba un costo finito y mayor que 0 (revision manual)"))
    if registro["stock_minimo"] > registro["stock_maximo"]:
        errores.append(crear_error(ident, "RN-03", "stock_minimo", registro["stock_minimo"],
                                   f"se esperaba un valor menor o igual a stock_maximo={registro['stock_maximo']}"))
    if not 1 <= registro["lead_time_dias"] <= 30:
        errores.append(crear_error(ident, "RN-04", "lead_time_dias", registro["lead_time_dias"],
                                   "se esperaba un valor entre 1 y 30 dias"))
    if registro.get("categoria") not in CATEGORIAS_VALIDAS:
        errores.append(crear_error(ident, "RN-05", "categoria", registro.get("categoria"),
                                   f"se esperaba una de: {', '.join(sorted(CATEGORIAS_VALIDAS))}"))
    if not isinstance(registro.get("proveedor"), str) or not registro["proveedor"].strip():
        errores.append(crear_error(ident, "RN-06", "proveedor", registro.get("proveedor"),
                                   "se esperaba el nombre del proveedor (no vacio)"))
    if not isinstance(registro.get("id_producto"), str) or not PATRON_ID.fullmatch(registro["id_producto"]):
        errores.append(crear_error(ident, "RN-07", "id_producto", registro.get("id_producto"),
                                   "se esperaba una mayuscula seguida de 3 digitos (ej. P001)"))
    return not errores, errores


def validar_lote(filas):
    """Valida todas las filas sin detenerse ante errores.

    Aplica validar_tipos, normalizar_registro y validar_reglas_negocio. Los
    descartes se registran en el log (WARNING) y las correcciones (INFO).
    Un fallo inesperado en una fila tambien la descarta y el flujo continua.

    Args:
        filas (list[dict]): filas crudas del CSV.

    Returns:
        tuple: (validos, descartados, correcciones). Cada descartado es un
        dict con fila (linea del archivo, cabecera = 1), id y errores.
    """
    validos, descartados, correcciones = [], [], []
    for numero, fila in enumerate(filas, start=2):
        ident = str(fila.get("id_producto") or "DESCONOCIDO").strip()
        cambios = []
        try:
            ok, registro, errores = validar_tipos(fila)
            if ok:
                registro, cambios = normalizar_registro(registro)
                ok, errores = validar_reglas_negocio(registro)
        except (TypeError, ValueError, KeyError) as exc:
            ok = False
            errores = [crear_error(ident, "PROCESAMIENTO", "indeterminada", "indeterminado",
                                   f"{type(exc).__name__}: {exc}")]
        if ok:
            validos.append(registro)
            correcciones.extend(cambios)
            for cambio in cambios:
                LOGGER.info(cambio)
        else:
            descartados.append({"fila": numero, "id": ident, "errores": errores})
            for mensaje in errores:
                LOGGER.warning("Fila %d descartada | %s", numero, mensaje)
    return validos, descartados, correcciones


# =====================================================================
# 4. CALCULOS
# =====================================================================
def calcular_reposicion(registro, umbral_urgencia=UMBRAL_EXTREMA_URGENCIA):
    """Calcula la reposicion de un producto bajo el stock minimo.

    Args:
        registro (dict): producto validado.
        umbral_urgencia (int): dias de lead time sobre los cuales es extrema
            urgencia. Default: UMBRAL_EXTREMA_URGENCIA (5).

    Returns:
        tuple: (orden, es_extrema_urgencia). orden es None si el producto
        no esta bajo el stock minimo.
    """
    if registro["stock_actual"] >= registro["stock_minimo"]:
        return None, False
    cantidad = registro["stock_maximo"] - registro["stock_actual"]
    costo = cantidad * registro["costo_unitario"]
    orden = {"id_producto": registro["id_producto"], "producto": registro["producto"],
             "cantidad_a_reponer": cantidad, "costo_total_reposicion": round(costo, 2),
             "proveedor": registro["proveedor"].strip(),
             "dias_estimados_reposicion": registro["lead_time_dias"]}
    return orden, registro["lead_time_dias"] > umbral_urgencia


def analizar_inventario(validos, umbral_urgencia=UMBRAL_EXTREMA_URGENCIA):
    """Clasifica el inventario valido y acumula ordenes, costos y agrupaciones.

    Args:
        validos (list[dict]): registros validos.
        umbral_urgencia (int): umbral de extrema urgencia. Default: 5 dias.

    Returns:
        dict: ordenes, urgentes, conteos por estado, unidades, costo y
        conteos de bajo stock por categoria y por proveedor.
    """
    a = {"ordenes": [], "urgentes": [], "bajo_stock": 0, "sobrestock": 0, "normal": 0,
         "unidades": 0, "costo": 0.0, "por_categoria": {}, "por_proveedor": {}}
    for registro in validos:
        orden, urgente = calcular_reposicion(registro, umbral_urgencia)
        if orden is not None:
            a["bajo_stock"] += 1
            a["ordenes"].append(orden)
            a["unidades"] += orden["cantidad_a_reponer"]
            a["costo"] += orden["costo_total_reposicion"]
            cat, prov = registro["categoria"], orden["proveedor"]
            a["por_categoria"][cat] = a["por_categoria"].get(cat, 0) + 1
            a["por_proveedor"][prov] = a["por_proveedor"].get(prov, 0) + 1
            if urgente:
                a["urgentes"].append(orden)
        elif registro["stock_actual"] > registro["stock_maximo"]:
            a["sobrestock"] += 1
        else:
            a["normal"] += 1
    return a


def seleccionar_ordenes(analisis, solo_urgentes=SOLO_EXTREMA_URGENCIA):
    """Elige las ordenes que van al CSV de salida.

    Args:
        analisis (dict): resultado de analizar_inventario.
        solo_urgentes (bool): True -> solo extrema urgencia; False -> todo
            producto bajo stock minimo. Default: SOLO_EXTREMA_URGENCIA.

    Returns:
        list[dict]: ordenes seleccionadas.
    """
    return analisis["urgentes"] if solo_urgentes else analisis["ordenes"]


# =====================================================================
# 5. ENTRADA / SALIDA
# =====================================================================
def leer_csv(ruta=ARCHIVO_ENTRADA, encoding="utf-8-sig"):
    """Lee el inventario como lista de diccionarios.

    Los errores no recuperables se registran en el log y se vuelven a
    lanzar para que main() termine de forma controlada.

    Args:
        ruta (Path): archivo de entrada. Default: data/inventario_cd.csv o
            inventario_cd.csv junto al script.
        encoding (str): codificacion. Default: 'utf-8-sig' (UTF-8 que tolera
            la marca BOM de Excel).

    Returns:
        list[dict]: filas originales.

    Raises:
        FileNotFoundError, PermissionError, UnicodeDecodeError, csv.Error,
        ValueError (encabezados incompletos).
    """
    filas = []
    try:
        with open(ruta, "r", encoding=encoding, newline="") as archivo:
            lector = csv.DictReader(archivo)
            faltantes = sorted(set(COLUMNAS_ENTRADA).difference(lector.fieldnames or []))
            if faltantes:
                LOGGER.error("Encabezados incompletos en %s. Faltan: %s", ruta, faltantes)
                raise ValueError(f"Encabezados CSV incompletos: {faltantes}")
            for fila in lector:
                filas.append(fila)
    except FileNotFoundError:
        LOGGER.error("Archivo de entrada no encontrado: %s", ruta)
        raise
    except PermissionError:
        LOGGER.error("Sin permisos para leer el archivo: %s", ruta)
        raise
    except UnicodeDecodeError as exc:
        LOGGER.error("Codificacion invalida (%s) en %s: %s", encoding, ruta, exc)
        raise
    except csv.Error as exc:
        LOGGER.error("CSV mal formado en %s (linea %d): %s", ruta, lector.line_num, exc)
        raise
    else:
        LOGGER.info("Archivo leido: %s (%d filas de datos)", ruta, len(filas))
        return filas
    finally:
        LOGGER.info("Intento de lectura de %s finalizado.", ruta)


def escribir_csv_salida(ruta, registros, encoding="utf-8"):
    """Escribe las ordenes de compra en el CSV de salida.

    Args:
        ruta (Path): archivo destino.
        registros (list[dict]): ordenes a escribir.
        encoding (str): codificacion. Default: 'utf-8'.

    Returns:
        int: cantidad de filas escritas.

    Raises:
        PermissionError: sin permisos (o archivo abierto en Excel).
        OSError: otro fallo de disco o ruta.
    """
    try:
        with open(ruta, "w", encoding=encoding, newline="") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS_SALIDA)
            escritor.writeheader()
            escritor.writerows(registros)
    except PermissionError:
        LOGGER.error("Sin permisos para escribir %s (cierrelo si esta abierto).", ruta)
        raise
    except OSError as exc:
        LOGGER.error("Fallo del sistema al escribir %s: %s", ruta, exc)
        raise
    else:
        LOGGER.info("Archivo de salida generado: %s (%d ordenes)", ruta, len(registros))
        return len(registros)
    finally:
        LOGGER.info("Intento de escritura de %s finalizado.", ruta)


# =====================================================================
# 6. REPORTE
# =====================================================================
def formatear_clp(valor):
    """Formatea un monto en pesos chilenos, con punto como separador de miles.

    Args:
        valor (float): monto.

    Returns:
        str: texto como '$1.234.567'.
    """
    return "$" + f"{valor:,.0f}".replace(",", ".")


def construir_resumen(leidos, analisis, descartados, correcciones, ordenes_salida):
    """Calcula los indicadores del reporte ejecutivo.

    El motivo principal de descarte cuenta FILAS afectadas por cada regla
    (una fila con varios errores de la misma regla cuenta una sola vez).

    Args:
        leidos (int): filas leidas del CSV.
        analisis (dict): resultado de analizar_inventario.
        descartados (list[dict]): descartes de validar_lote.
        correcciones (list[str]): correcciones automaticas aplicadas.
        ordenes_salida (int): ordenes escritas en el CSV de salida.

    Returns:
        dict: indicadores para generar_reporte_consola.
    """
    motivos = {}
    for d in descartados:
        for regla in {m.split(" | ")[1] for m in d["errores"]}:
            motivos[regla] = motivos.get(regla, 0) + 1

    def mas_frecuente(conteo):
        return max(conteo, key=conteo.get) if conteo else None

    categoria = mas_frecuente(analisis["por_categoria"])
    proveedor = mas_frecuente(analisis["por_proveedor"])
    return {
        "leidos": leidos, "validos": leidos - len(descartados),
        "descartados": len(descartados),
        "pct_descartados": len(descartados) / leidos if leidos else 0.0,
        "correcciones": len(correcciones),
        "motivos": motivos, "motivo_principal": mas_frecuente(motivos),
        "ejemplos": [d["errores"][0] for d in descartados[:5]],
        "bajo_stock": analisis["bajo_stock"], "sobrestock": analisis["sobrestock"],
        "normal": analisis["normal"], "unidades": analisis["unidades"],
        "costo": analisis["costo"],
        "urgentes": analisis["urgentes"],
        "costo_urgentes": sum(o["costo_total_reposicion"] for o in analisis["urgentes"]),
        "proveedores": analisis["por_proveedor"],
        "categoria_critica": categoria,
        "categoria_critica_n": analisis["por_categoria"].get(categoria, 0),
        "proveedor_critico": proveedor,
        "proveedor_critico_n": analisis["por_proveedor"].get(proveedor, 0),
        "ordenes_salida": ordenes_salida,
    }


def redactar_recomendacion(resumen, umbral_urgencia=UMBRAL_EXTREMA_URGENCIA):
    """Redacta la recomendacion al Jefe del CD a partir de los resultados.

    Args:
        resumen (dict): resultado de construir_resumen.
        umbral_urgencia (int): umbral citado en el texto. Default: 5 dias.

    Returns:
        str: parrafo de recomendacion logistica.
    """
    if resumen["validos"] == 0:
        return ("No hubo registros validos para analizar. Revise los datos de "
                "origen y errores.log antes de volver a ejecutar.")
    partes = []
    n_urg = len(resumen["urgentes"])
    if n_urg:
        partes.append(f"Se recomienda emitir de inmediato las {n_urg} ordenes de extrema urgencia "
                      f"(bajo stock minimo y lead time superior a {umbral_urgencia} dias), por "
                      f"{formatear_clp(resumen['costo_urgentes'])}, porque el plazo de entrega "
                      f"agrava el riesgo de quiebre.")
    else:
        partes.append("No hay productos en extrema urgencia; la reposicion puede programarse con normalidad.")
    if resumen["categoria_critica"]:
        partes.append(f"La categoria mas critica es {resumen['categoria_critica']} "
                      f"(con {resumen['categoria_critica_n']} bajo el minimo) y el proveedor con "
                      f"mas alertas es {resumen['proveedor_critico']} ({resumen['proveedor_critico_n']}): "
                      f"conviene revisar con él sus plazos de entrega.")
    if resumen["sobrestock"]:
        partes.append(f"Hay {resumen['sobrestock']} productos con sobrestock: no deben reponerse "
                      f"y conviene revisar su rotacion.")
    if resumen["descartados"]:
        motivo = resumen["motivo_principal"]
        partes.append(f"Se descartaron {resumen['descartados']} registros ({resumen['pct_descartados']:.0%}); "
                      f"el motivo principal es {motivo} ({DESCRIPCION_REGLAS.get(motivo, motivo)}). "
                      f"Se sugiere corregir el dato en el WMS o en el maestro de productos antes de "
                      f"la proxima carga.")
    return " ".join(partes)


def generar_reporte_consola(resumen, ruta_salida=ARCHIVO_SALIDA, ruta_log=ARCHIVO_LOG, max_urgentes=10, escritura_correcta=True):
    """Imprime el resumen ejecutivo y la recomendacion final.

    Args:
        resumen (dict): resultado de construir_resumen.
        ruta_salida (Path): CSV de salida a informar. Default: ARCHIVO_SALIDA.
        ruta_log (Path | str): log a informar. Default: ARCHIVO_LOG.
        max_urgentes (int): maximo de productos urgentes a listar. Default: 10.
        escritura_correcta (bool): confirma si se guardo correctamente el CSV.

    Returns:
        str: texto completo del reporte (el mismo que se imprime).
    """
    r = resumen
    L = ["", "=" * 66, "RESUMEN EJECUTIVO V3 - DIMAULE SpA", "=" * 66,
         "--- Validacion de datos ---",
         f"Registros leidos:         {r['leidos']}",
         f"Registros validos:        {r['validos']}",
         f"Registros descartados:    {r['descartados']} ({r['pct_descartados']:.1%})",
         f"Correcciones automaticas: {r['correcciones']}"]
    if r["descartados"]:
        L.append("Descartes por regla (filas afectadas):")
        for regla, n in sorted(r["motivos"].items(), key=lambda p: p[1], reverse=True):
            L.append(f"   {regla}: {n}  ({DESCRIPCION_REGLAS.get(regla, regla)})")
        L.append(f"Motivo principal de descarte: {r['motivo_principal']}")
        L.append("Ejemplos (detalle completo en el log):")
        L.extend(f"   {m}" for m in r["ejemplos"])
    L += ["", "--- Estado del inventario (registros validos) ---",
          f"Bajo stock minimo:      {r['bajo_stock']}",
          f"Sobrestock:             {r['sobrestock']}",
          f"Stock normal:           {r['normal']}",
          f"Unidades a reponer:     {r['unidades']:,}".replace(",", "."),
          f"Costo total reposicion: {formatear_clp(r['costo'])}",
          f"Categoria mas critica:  {r['categoria_critica'] or 'Sin casos'}",
          "", "--- Alertas por proveedor (bajo stock) ---"]
    L.extend(f"   {p}: {n}" for p, n in sorted(r["proveedores"].items()))
    L += ["", f"--- Extrema urgencia (bajo stock y lead time > {UMBRAL_EXTREMA_URGENCIA} dias) ---",
          f"Productos: {len(r['urgentes'])} | Costo: {formatear_clp(r['costo_urgentes'])}"]
    mayores = sorted(r["urgentes"], key=lambda o: o["costo_total_reposicion"], reverse=True)
    for o in mayores[:max_urgentes]:
        L.append(f"   {o['id_producto']} - {o['producto']} | "
                 f"{formatear_clp(o['costo_total_reposicion'])} | {o['dias_estimados_reposicion']} dias")
    if len(mayores) > max_urgentes:
        L.append(f"   ... y {len(mayores) - max_urgentes} mas (ver CSV de salida)")
    L += ["", (f"Ordenes en CSV de salida: {r['ordenes_salida']} -> {ruta_salida}" if escritura_correcta else f"ERROR: No se pudo generar el CSV de salida -> {ruta_salida}"),
          f"Registro de errores y eventos: {ruta_log}", "",
          "--- Recomendacion al Jefe del CD ---", redactar_recomendacion(r), "=" * 66]
    texto = "\n".join(L)
    print(texto)
    return texto


# =====================================================================
# 7. PROGRAMA PRINCIPAL
# =====================================================================
def main():
    """Orquesta lectura, validacion, analisis, salida y reporte.

    Es el unico punto de orquestacion. Siempre termina de forma controlada.

    Returns:
        int: codigo de salida (0 exito, 1 error de lectura, 2 error al
        escribir la salida, 3 descartes sobre el umbral).
    """
    destino_log = configurar_log()
    LOGGER.info("INICIO | Procesador de inventario V3 | entrada=%s", ARCHIVO_ENTRADA)
    codigo = 0
    try:
        filas = leer_csv()
        validos, descartados, correcciones = validar_lote(filas)
        analisis = analizar_inventario(validos)
        ordenes = seleccionar_ordenes(analisis)
        ordenes_escritas = 0
        escritura_correcta = False
        try:
            ordenes_escritas = escribir_csv_salida(ARCHIVO_SALIDA, ordenes)
            escritura_correcta = True
        except PermissionError:
            print(f"ERROR: sin permisos para escribir {ARCHIVO_SALIDA.name}. "
                  "Si esta abierto en Excel, cierrelo y reintente.")
            codigo = 2
        except OSError as exc:
            print(f"ERROR: no se pudo escribir {ARCHIVO_SALIDA.name}: {exc}")
            codigo = 2
        resumen = construir_resumen(len(filas), analisis, descartados, correcciones, ordenes_escritas)
        generar_reporte_consola(resumen, ruta_log=destino_log or "(solo consola)", escritura_correcta=escritura_correcta)
        if codigo == 0 and resumen["pct_descartados"] > UMBRAL_DESCARTE:
            print(f"ADVERTENCIA: se descartaron mas del {UMBRAL_DESCARTE:.0%} de los registros. "
                  "Revise la calidad del archivo de origen.")
            codigo = 3
    except FileNotFoundError:
        print(f"ERROR: no se encontro el archivo de entrada: {ARCHIVO_ENTRADA}\n"
              "Verifique que bodega lo haya depositado en 'data/' o junto al script.")
        codigo = 1
    except PermissionError:
        print(f"ERROR: sin permisos para leer {ARCHIVO_ENTRADA}.")
        codigo = 1
    except UnicodeDecodeError:
        print("ERROR: el archivo no esta en UTF-8. Guardelo con esa codificacion y reintente.")
        codigo = 1
    except csv.Error:
        print("ERROR: el archivo CSV esta mal formado. Detalle en errores.log.")
        codigo = 1
    except ValueError as exc:
        print(f"ERROR de datos: {exc}")
        codigo = 1
    except TypeError as exc:
        LOGGER.error("Error de tipo no esperado: %s", exc, exc_info=True)
        print(f"ERROR de tipo de dato: {exc}. Detalle en errores.log.")
        codigo = 1
    except Exception as exc:        # red de seguridad final (permitida solo en main)
        LOGGER.critical("Error no controlado: %s", exc, exc_info=True)
        print("Ocurrio un error inesperado. Revise errores.log.")
        codigo = 1
    finally:
        LOGGER.info("FIN | Ejecucion finalizada con codigo de salida %d", codigo)
        print("\nProceso finalizado.")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
