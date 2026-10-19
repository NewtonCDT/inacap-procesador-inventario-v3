# Procesador de Inventario V3 — INACAP

Proyecto desarrollado en Python para la Sumativa de la Unidad 3 del Diplomado en Inteligencia Artificial Aplicada a Entornos Industriales.

## Funcionalidades

- Lectura de inventario desde un archivo CSV.
- Validación de tipos de datos y reglas de negocio RN01–RN07.
- Identificación y registro de productos con datos inválidos.
- Clasificación de inventario: bajo stock, normal y sobrestock.
- Cálculo de unidades y costos de reposición.
- Generación de órdenes de compra en formato CSV.
- Registro de errores en `errores.log`.
- Manejo de excepciones y reporte ejecutivo.

## Requisitos

- Python 3.
- Archivo `inventario_cd.csv` con las columnas requeridas.
- No requiere bibliotecas externas.

## Ejecución

Ubicar `inventario_cd.csv` en la carpeta del proyecto y ejecutar:

```bash
python3 procesador_inventario_v3.py
```

## Archivos generados

- `ordenes_compra_urgente_v3.csv`: órdenes de compra.
- `errores.log`: registro de errores detectados.

## Resultados de referencia

- 500 registros recibidos.
- 362 productos válidos.
- 138 registros descartados.
- 196 órdenes de compra.
- 21.723 unidades a reponer.
- Costo estimado: $37.309.170.

## Control de versiones

El repositorio conserva el desarrollo progresivo mediante Git.

El archivo de datos original no se publica en este repositorio.
