import csv

ARCHIVO_ENTRADA = "inventario_cd.csv"
UMBRAL_EXTREMA_URGENCIA = 5

# Inicialización de contadores
total_productos = 0
total_bajo_stock = 0
total_sobrestock = 0
total_stock_normal = 0
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
    lector = csv.DictReader(archivo)

    for fila in lector:

        # Conversión de datos
        stock_actual = int(fila["stock_actual"])
        stock_minimo = int(fila["stock_minimo"])
        stock_maximo = int(fila["stock_maximo"])
        demanda_semanal = int(fila["demanda_semanal"])
        costo_unitario = float(fila["costo_unitario"])
        categoria = fila["categoria"]
        proveedor = fila["proveedor"]
        lead_time_dias = int(fila["lead_time_dias"])

        # Almacenar registro del inventario
        registros_inventario.append(fila.copy())

        # Contar cada producto procesado
        total_productos += 1

        # Clasificar el inventario
        if stock_actual < stock_minimo:
            total_bajo_stock += 1

                # Calcular cantidad necesaria para reponer
            cantidad_a_reponer = stock_maximo - stock_actual

                # Calcular costo de reposición
            costo_reposicion = cantidad_a_reponer * costo_unitario

               # Acumular resultados
            total_unidades_reponer += cantidad_a_reponer
            costo_total_reposicion += costo_reposicion
            # Registrar orden de compra
            ordenes_compra.append({
                "id_producto": fila["id_producto"],
                "producto": fila["producto"],
                "cantidad_a_reponer": cantidad_a_reponer,
                "costo_total_reposicion": round(costo_reposicion, 0),
                "proveedor": proveedor
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

# Mostrar resultados
print("===== RESUMEN DE INVENTARIO =====")
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
ARCHIVO_SALIDA = "ordenes_compra_urgente.csv"

columnas_salida = [
    "id_producto",
    "producto",
    "cantidad_a_reponer",
    "costo_total_reposicion",
    "proveedor"
]

with open(ARCHIVO_SALIDA, mode="w", encoding="utf-8", newline="") as archivo:
    escritor = csv.DictWriter(archivo, fieldnames=columnas_salida)
    escritor.writeheader()
    escritor.writerows(ordenes_compra)

print("\nArchivo de ordenes de compra generado correctamente.")
print(f"Total de ordenes registradas: {len(ordenes_compra)}")