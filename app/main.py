from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from sqlalchemy import func, case

from . import models
from .database import engine, get_db

# Crear todas las tablas en la DB (solo si no existen)
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Montar los archivos estáticos (HTML/JS/CSS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Schemas (Pydantic) ---

class CelularEntry(BaseModel):
    imei: str

class BatchEntry(BaseModel):
    oc_id: str
    proveedor: str
    costo_total_usd: float
    costo_unitario_cop: float
    imeis: List[CelularEntry]

class CelularSalida(BaseModel):
    imei: str
    tipo_cliente: str
    nombre_cliente: str
    precio_venta: float
    vendedor: str

# --- Endpoints ---

@app.get("/")
def read_root():
    return {"message": "Go to /static/index.html or /static/sales.html"}

@app.post("/api/v1/inventario/entrada")
def entry_batch(data: BatchEntry, db: Session = Depends(get_db)):
    """Ingresa un lote de celulares al inventario."""
    try:
        celulares_creados = 0
        for item in data.imeis:
            db_celular = models.Celular(
                imei=item.imei,
                oc_id=data.oc_id,
                proveedor=data.proveedor,
                costo_total_usd=data.costo_total_usd,
                costo_cop=data.costo_unitario_cop,
            )
            # Manejar la clave primaria duplicada
            existing_celular = db.query(models.Celular).filter(models.Celular.imei == item.imei).first()
            if existing_celular:
                continue 
            db.add(db_celular)
            celulares_creados += 1
        db.commit()
        return {"status": "success", "count": celulares_creados, "oc_id": data.oc_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al ingresar lote: {str(e)}")

@app.post("/api/v1/inventario/salida")
def register_sale(data: CelularSalida, db: Session = Depends(get_db)):
    """Registra una venta o entrega en consignación."""
    db_celular = db.query(models.Celular).filter(models.Celular.imei == data.imei).first()

    if not db_celular:
        raise HTTPException(status_code=404, detail="IMEI no encontrado.")
    
    if db_celular.estado != "En Inventario":
        raise HTTPException(status_code=400, detail=f"El celular ya tiene estado: {db_celular.estado}")

    # Asignar el vendedor
    db_celular.vendedor = data.vendedor

    # Definir el estado y la trazabilidad
    if data.tipo_cliente == "Consignacion":
        db_celular.estado = "Entregado Consignacion"
        db_celular.cliente_consignacion = data.nombre_cliente
    elif data.tipo_cliente == "Detal":
        db_celular.estado = "Vendido"
        db_celular.fecha_salida = func.now()
        db_celular.precio_venta = data.precio_venta
    else:
        raise HTTPException(status_code=400, detail="Tipo de cliente inválido.")

    db.add(db_celular)
    db.commit()
    db.refresh(db_celular)

    return {"status": "success", "imei": db_celular.imei, "nuevo_estado": db_celular.estado}

@app.post("/api/v1/inventario/reingreso")
def register_reentry(imei_data: CelularEntry, db: Session = Depends(get_db)):
    """Reingresa un celular al inventario (ej. por devolución de consignación)."""
    
    db_celular = db.query(models.Celular).filter(models.Celular.imei == imei_data.imei).first()

    if not db_celular:
        raise HTTPException(status_code=404, detail="IMEI no encontrado.")
    
    # Permitir reingreso solo si el estado es Consignación o Vendido (en caso de devolución)
    if db_celular.estado not in ["Entregado Consignacion", "Vendido"]:
        raise HTTPException(status_code=400, detail=f"El celular ya está en estado {db_celular.estado}. Solo se pueden reingresar ítems en Consignación o Vendidos.")

    # Revertir el estado y limpiar campos de salida
    previous_state = db_celular.estado
    db_celular.estado = "En Inventario"
    db_celular.cliente_consignacion = None
    db_celular.vendedor = None
    db_celular.fecha_salida = None
    db_celular.precio_venta = None

    db.add(db_celular)
    db.commit()
    db.refresh(db_celular)

    return {
        "status": "success", 
        "imei": db_celular.imei, 
        "estado_anterior": previous_state,
        "nuevo_estado": db_celular.estado
    }

@app.get("/api/v1/ordenes/balance")
def get_ordenes_balance(db: Session = Depends(get_db)):
    """Retorna el balance de costo vs. venta y el estado de cierre para cada OC."""
    balance_query = db.query(
        models.Celular.oc_id.label("orden_compra"),
        func.count(models.Celular.imei).label("total_unidades"),
        func.sum(models.Celular.costo_cop).label("costo_total_compra"),
        func.sum(case(
            (models.Celular.estado == "Vendido", models.Celular.precio_venta),
            else_=0
        )).label("ingreso_total_venta"),
        func.sum(case(
            (models.Celular.estado == "Entregado Consignacion", 1),
            else_=0
        )).label("unidades_consignacion"),
        func.sum(case(
            (models.Celular.estado == "En Inventario", 1),
            else_=0
        )).label("unidades_disponibles")
    ).group_by(models.Celular.oc_id).all()

    resultados = []
    for row in balance_query:
        pendientes = row.unidades_disponibles + row.unidades_consignacion
        resultados.append({
            "orden_compra": row.orden_compra,
            "total_unidades": row.total_unidades,
            "costo_total_compra": round(row.costo_total_compra or 0, 2),
            "ingreso_total_venta": round(row.ingreso_total_venta or 0, 2),
            "utilidad_bruta": round((row.ingreso_total_venta or 0) - (row.costo_total_compra or 0), 2),
            "unidades_consignacion": row.unidades_consignacion,
            "unidades_disponibles": row.unidades_disponibles,
            "estado_cierre": "CERRADA" if pendientes == 0 else "ABIERTA"
        })
    return {"ordenes_resumen": resultados}
