from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import SQLALCHEMY_DATABASE_URI

# Crear motor de conexión
engine = create_engine(SQLALCHEMY_DATABASE_URI, echo=True)

# Crear clase base para modelos
Base = declarative_base()

# Crear sesión
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# Función auxiliar para obtener una sesión
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
