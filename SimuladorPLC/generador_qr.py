import qrcode
import os

def crear_qr(numero):
    # Configurar el objeto QR
    qr = qrcode.QRCode(
        version=1, # Tamaño más pequeño
        error_correction=qrcode.constants.ERROR_CORRECT_H, # Alta corrección de errores (fácil de leer)
        box_size=15, # Tamaño de los cuadros
        border=4,    # Borde blanco
    )
    
    # Agregar el número (en formato texto para el QR)
    qr.add_data(str(numero))
    qr.make(fit=True)

    # Crear imagen en blanco y negro
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Guardar la imagen
    filename = f"qr_categoria_{numero}.png"
    img.save(filename)
    print(f"[ÉXITO] Código QR para la Categoría '{numero}' guardado como '{filename}'")

if __name__ == "__main__":
    print("===========================================")
    print("  GENERADOR DE CÓDIGOS QR INDUSTRIALES     ")
    print("===========================================")
    print("Creando los códigos de prueba...")
    
    # Generar QR para las categorías 1, 2 y 3
    for i in [1, 2, 3]:
        crear_qr(i)
        
    print("¡Terminado! Puedes abrir los archivos PNG generados.")
