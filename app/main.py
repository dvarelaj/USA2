from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from . import models
from .database import engine, get_db
from sqlalchemy import func, case, extract, cast, Date # Agregar 'case', 'extract', 'cast', 'Date'
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
    trm: float
    costo_usd: float
    imeis: List[CelularEntry]

class CelularSalida(BaseModel):
    imei: str
    tipo_cliente: str # Detal o Consignacion
    nombre_cliente: str
    precio_venta: float

# --- Endpoints ---

@app.get("/")
def read_root():
    # Redirige a la página principal/dashboard
    return {"message": "Go to /static/index.html or /static/sales.html"}


@app.post("/api/v1/inventario/entrada")
def entry_batch(data: BatchEntry, db: Session = Depends(get_db)):
    """Ingresa un lote de celulares al inventario."""
    try:
        celulares_creados = 0
        for item in data.imeis:
            # Calcular costo en COP
            costo_cop = data.trm * data.costo_usd
            
            db_celular = models.Celular(
                imei=item.imei,
                oc_id=data.oc_id,
                trm_compra=data.trm,
                costo_cop=costo_cop,
            )
            db.add(db_celular)
            celulares_creados += 1
        
        db.commit()
        return {"status": "success", "count": celulares_creados, "oc_id": data.oc_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al ingresar lote: {e}")


@app.post("/api/v1/inventario/salida")
def register_sale(data: CelularSalida, db: Session = Depends(get_db)):
    """Registra una venta o entrega en consignación."""
    db_celular = db.query(models.Celular).filter(models.Celular.imei == data.imei).first()

    if not db_celular:
        raise HTTPException(status_code=404, detail="IMEI no encontrado.")
    
    if db_celular.estado != "En Inventario":
        raise HTTPException(status_code=400, detail=f"El celular ya tiene estado: {db_celular.estado}")

    # Definir el estado y la trazabilidad
    if data.tipo_cliente == "Consignacion":
        db_celular.estado = "Entregado Consignacion"
        db_celular.cliente_consignacion = data.nombre_cliente
    elif data.tipo_cliente == "Detal":
        db_celular.estado = "Vendido"
        # Para Detal, se registra la salida y el precio.
        db_celular.fecha_salida = func.now()
        db_celular.precio_venta = data.precio_venta
    else:
        raise HTTPException(status_code=400, detail="Tipo de cliente inválido.")

    db.add(db_celular)
    db.commit()
    db.refresh(db_celular)

    return {"status": "success", "imei": db_celular.imei, "nuevo_estado": db_celular.estado}


@app.get("/api/v1/ordenes/balance")
def get_ordenes_balance(db: Session = Depends(get_db)):
    """Retorna el balance de costo vs. venta y el estado de cierre para cada OC."""
    
    # 1. Agregación de datos por OC
    balance_query = db.query(
        models.Celular.oc_id.label("orden_compra"),
        func.count(models.Celular.imei).label("total_unidades"),
        
        # Total Costo de Compra
        func.sum(models.Celular.costo_cop).label("costo_total_compra"),
        
        # Total Ingreso de Venta (solo unidades vendidas)
        func.sum(case(
            (models.Celular.estado == "Vendido", models.Celular.precio_venta),
            else_=0
        )).label("ingreso_total_venta"),
        
        # Unidades en Consignación
        func.sum(case(
            (models.Celular.estado == "Entregado Consignacion", 1),
            else_=0
        )).label("unidades_consignacion"),
        
        # Unidades Disponibles (En Inventario)
        func.sum(case(
            (models.Celular.estado == "En Inventario", 1),
            else_=0
        )).label("unidades_disponibles")
        
    ).group_by(models.Celular.oc_id).all()

    # 2. Formatear resultados
    resultados = []
    for row in balance_query:
        # La OC está cerrada si no quedan unidades en inventario, vendidas, o en consignación
        # (Aunque el cálculo se hace en base a 'disponibles' y 'consignación' restantes)
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