# app/models.py

from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from .database import Base

class Celular(Base):
    __tablename__ = "celulares"

    imei = Column(String, primary_key=True, index=True)
    oc_id = Column(String, index=True)
    
    # Nuevos campos de proveedor y costo
    proveedor = Column(String, nullable=True) # <-- NUEVO CAMPO
    costo_total_usd = Column(Float, nullable=True) # <-- NUEVO CAMPO
    
    # Hemos simplificado, ahora solo guardamos el costo unitario ponderado en COP
    costo_cop = Column(Float) # Ahora representa el Costo Unitario Ponderado
    
    estado = Column(String, default="En Inventario") 
    cliente_consignacion = Column(String, nullable=True)
    vendedor = Column(String, nullable=True)
    fecha_entrada = Column(DateTime, default=func.now())
    fecha_salida = Column(DateTime, nullable=True)
    precio_venta = Column(Float, nullable=True)

    