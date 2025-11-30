# app/database.py (Cambio para Postgres)
import os
from sqlalchemy import create_engine
# ... otras importaciones

# Usar una variable de entorno proporcionada por Render
DATABASE_URL = os.environ.get("DATABASE_URL")

engine = create_engine(
    DATABASE_URL # Render proporciona la URL completa (postgres://user:pass@host:port/db)
)
# ... el resto del código SessionLocal y Base queda igual