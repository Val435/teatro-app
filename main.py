from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
import qrcode
from io import BytesIO
import base64
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.message import EmailMessage
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI()


# Configurar CORS para permitir solicitudes desde el frontend (localhost:4200)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["tps://teatro-byc4p4w3t-valentinas-projects-c81f50c4.vercel.app"],  # URL de Vercel
    allow_credentials=True,
    allow_methods=["*"],  # Permitir todos los métodos HTTP (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Permitir todas las cabeceras
)

# Conexión a Azure SQL
DATABASE_URL = "mssql+pyodbc://joselin:Adminpassword-@webteatro.database.windows.net:1433/teatrobd?driver=ODBC+Driver+17+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Modelos de la base de datos
class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    nombre = Column(String(255), nullable=False)
    qr_code = Column(String, nullable=True)
    qr_validado = Column(Boolean, default=False)
    obra_id = Column(Integer, ForeignKey("obras.id"))

class Obra(Base):
    __tablename__ = "obras"
    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(255), nullable=False)
    descripcion = Column(String)
    fecha = Column(String)

# Crear las tablas en la base de datos
Base.metadata.create_all(bind=engine)

# Modelos para crear datos desde el frontend
class UsuarioCreate(BaseModel):
    email: str
    nombre: str
    obra_id: int

class ObraCreate(BaseModel):
    titulo: str
    descripcion: str
    fecha: str

# Crear un modelo para validar el QR
class ValidarQRRequest(BaseModel):
    email: str
    qr_code: str

# Generación del QR con la URL para validación
def generar_qr(email: str, qr_code: str):
    # Generate a unique code instead of using just the email
    unique_code = base64.b64encode(f"{email}-{qr_code}".encode()).decode('utf-8')
    url = f"http://localhost:4200/validar-qr?email={email}&qr_code={unique_code}"
    img = qrcode.make(url)
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    qr_code_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return unique_code, qr_code_str

# Envío del QR por correo
def enviar_correo_qr(email, qr_code):
    try:
        msg = MIMEMultipart()
        msg['From'] = 'enestojunto21@gmail.com'
        msg['To'] = email
        msg['Subject'] = 'Tu código QR para la obra de teatro'

        # Cuerpo del mensaje
        body = 'Gracias por registrarte. Aquí está tu código QR adjunto.'
        msg.attach(MIMEText(body, 'plain'))

        # Convertir el base64 QR en bytes y adjuntar como imagen
        img_data = base64.b64decode(qr_code)
        image = MIMEImage(img_data, name="qr_code.png")
        msg.attach(image)

        # Conexión SMTP a Outlook
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()

        # Autenticarse en el servidor SMTP de Outlook
        server.login('enestojunto21@gmail.com', 'dzestzbhxcyikbct')

        # Enviar el correo
        server.sendmail('enestojunto21@gmail.com', email, msg.as_string())
        server.quit()
        print(f"Correo enviado a {email}")

    except smtplib.SMTPException as e:
        print(f"Error al enviar el correo: {str(e)}")
        return {"error": f"Error al enviar el correo: {str(e)}"}
    

# CRUD de Obras
@app.post("/obras")
async def crear_obra(obra: ObraCreate):
    db = SessionLocal()
    nueva_obra = Obra(titulo=obra.titulo, descripcion=obra.descripcion, fecha=obra.fecha)
    db.add(nueva_obra)
    db.commit()
    db.refresh(nueva_obra)
    return nueva_obra

@app.get("/obras")
async def obtener_obras():
    db = SessionLocal()
    obras = db.query(Obra).all()
    return obras

@app.get("/obras/{id}")
async def obtener_obra(id: int):
    db = SessionLocal()
    obra = db.query(Obra).filter(Obra.id == id).first()
    if not obra:
        raise HTTPException(status_code=404, detail="Obra no encontrada")
    return obra

@app.put("/obras/{id}")
async def actualizar_obra(id: int, obra: ObraCreate):
    db = SessionLocal()
    obra_actual = db.query(Obra).filter(Obra.id == id).first()
    if not obra_actual:
        raise HTTPException(status_code=404, detail="Obra no encontrada")
    
    obra_actual.titulo = obra.titulo
    obra_actual.descripcion = obra.descripcion
    obra_actual.fecha = obra.fecha
    db.commit()
    return obra_actual

@app.delete("/obras/{id}")
async def eliminar_obra(id: int):
    db = SessionLocal()
    obra = db.query(Obra).filter(Obra.id == id).first()
    if not obra:
        raise HTTPException(status_code=404, detail="Obra no encontrada")
    
    db.delete(obra)
    db.commit()
    return {"mensaje": "Obra eliminada"}

# CRUD de Usuarios
@app.post("/usuarios")
async def registrar_usuario(usuario: UsuarioCreate):
    db = SessionLocal()

    # Verificar si el email ya está registrado
    usuario_existente = db.query(Usuario).filter(Usuario.email == usuario.email).first()
    if usuario_existente:
        raise HTTPException(status_code=400, detail="El correo electrónico ya está registrado.")

    # Generar el QR basado en el email
    unique_code, qr_image = generar_qr(usuario.email, str(hash(usuario.email + str(usuario.obra_id))))

    # Crear el nuevo usuario
    nuevo_usuario = Usuario(
        email=usuario.email,
        nombre=usuario.nombre,
        obra_id=usuario.obra_id,
        qr_code=unique_code  # Store the unique code, not the image
    )

    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)

    # Enviar el correo con el QR
    enviar_correo_qr(usuario.email, qr_image)
    
    return {"mensaje": "Usuario registrado y correo enviado con QR"}

@app.get("/usuarios")
async def obtener_usuarios():
    db = SessionLocal()
    usuarios = db.query(Usuario).all()
    return usuarios

@app.get("/usuarios/{id}")
async def obtener_usuario(id: int):
    db = SessionLocal()
    usuario = db.query(Usuario).filter(Usuario.id == id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario

@app.put("/usuarios/{id}")
async def actualizar_usuario(id: int, usuario: UsuarioCreate):
    db = SessionLocal()
    usuario_actual = db.query(Usuario).filter(Usuario.id == id).first()
    if not usuario_actual:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    usuario_actual.email = usuario.email
    usuario_actual.nombre = usuario.nombre
    usuario_actual.obra_id = usuario.obra_id
    db.commit()
    return usuario_actual

@app.delete("/usuarios/{id}")
async def eliminar_usuario(id: int):
    db = SessionLocal()
    usuario = db.query(Usuario).filter(Usuario.id == id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    db.delete(usuario)
    db.commit()
    return {"mensaje": "Usuario eliminado"}

# Endpoint para validar QR
@app.post("/validar_qr")
async def validar_qr(data: ValidarQRRequest):
    print(f"Datos recibidos - Email: {data.email}, QR Code: {data.qr_code}")

    db = SessionLocal()
    usuario = db.query(Usuario).filter(Usuario.email == data.email).first()

    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if usuario.qr_validado:
        raise HTTPException(status_code=400, detail="QR ya fue validado anteriormente")

    # Compare the stored unique code with the received one
    if usuario.qr_code == data.qr_code:
        usuario.qr_validado = True
        db.commit()
        return {"mensaje": "QR validado correctamente. Gracias por asistir al evento."}
    else:
        raise HTTPException(status_code=400, detail="QR no válido")