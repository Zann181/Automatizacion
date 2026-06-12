# Guía de Conexión Paso a Paso con Google Sheets (Webhook API)

Esta guía explica detalladamente cómo conectar el sistema clasificador industrial con una hoja de cálculo de Google. Utilizaremos **Google Apps Script** para crear un Webhook (API receptora) ligero y seguro que recibirá los datos de las cajas escaneadas y las registrará automáticamente en tiempo real.

---

## 📋 Requisitos Previos
1. Una cuenta de Google (Gmail o Workspace).
2. El servidor del clasificador ejecutándose (ya sea en local o en tu intranet).

---

## 🛠️ Paso 1: Crear la Hoja de Cálculo
1. Entra a tu cuenta de Google Drive y crea una **nueva Hoja de cálculo de Google** (o ve directamente a [sheets.new](https://sheets.new)).
2. Ponle un nombre descriptivo en la parte superior izquierda, por ejemplo: `Reporte de Cajas - Clasificador Industrial`.
3. (Opcional) Puedes escribir las cabeceras en la primera fila para organizar las columnas, por ejemplo:
   - Celda **A1**: `Fecha y Hora`
   - Celda **B1**: `Categoría`
   - Celda **C1**: `Código QR (Datos)`

---

## 💻 Paso 2: Configurar Google Apps Script
1. En el menú superior de la hoja de cálculo, haz clic en **Extensiones** > **Apps Script**.
2. Se abrirá una nueva pestaña con el editor de código de Google.
3. Borra todo el código que aparezca por defecto en el archivo `Código.gs` y pega exactamente el siguiente script:

```javascript
/**
 * Receptor de peticiones POST del Clasificador Industrial
 * Registra cada caja escaneada en la hoja de cálculo activa.
 */
function doPost(e) {
  try {
    // 1. Obtener la hoja de cálculo activa y la primera pestaña
    var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = spreadsheet.getActiveSheet();
    
    // 2. Parsear el cuerpo JSON de la petición HTTP recibida
    var data = JSON.parse(e.postData.contents);
    
    // 3. Si es una petición de prueba (ping de conexión), retornar éxito de inmediato
    if (data.qr_data === "TEST_CONN") {
      return ContentService.createTextOutput(JSON.stringify({
        status: 'connected',
        message: '¡Conexión exitosa desde el Clasificador!'
      })).setMimeType(ContentService.MimeType.JSON);
    }
    
    // 4. Formatear la categoría para mejor legibilidad
    var categoriaTexto = "Categoría " + data.category;
    
    // 5. Agregar una nueva fila con: [Fecha y Hora actual, Categoría, Contenido del QR]
    sheet.appendRow([
      new Date(),       // Columna A: Timestamp
      categoriaTexto,   // Columna B: Categoría (1, 2, 3)
      data.qr_data      // Columna C: Datos del QR
    ]);
    
    // 6. Retornar respuesta HTTP 200 con JSON de confirmación
    return ContentService.createTextOutput(JSON.stringify({
      status: 'success',
      message: 'Fila agregada correctamente.'
    })).setMimeType(ContentService.MimeType.JSON);
    
  } catch (err) {
    // En caso de error, retornar código de fallo con el mensaje de error
    return ContentService.createTextOutput(JSON.stringify({
      status: 'error',
      message: err.message
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
```

4. Haz clic en el botón de **Guardar** (icono de disquete en la barra de herramientas) o presiona `Ctrl + S`.

---

## 🚀 Paso 3: Publicar e Implementar como Aplicación Web
Para que el servidor de Python pueda enviarle datos a este script, debemos publicarlo como una **Aplicación Web accesible**:

1. En la parte superior derecha de Apps Script, haz clic en el botón azul **Implementar** (Deploy) y selecciona **Nueva implementación**.
2. En el panel que se abre, haz clic en el icono de engranaje (junto a "Seleccionar tipo") y elige **Aplicación web**.
3. Configura los siguientes campos:
   - **Descripción**: `Webhook para Clasificador QR`
   - **Ejecutar como**: **Tu cuenta de Google** (tu correo).
   - **Quién tiene acceso**: **Cualquiera** (Esto es sumamente importante. Debe configurarse en *"Cualquiera"* o *"Anyone"* para que el servidor de Python pueda hacer peticiones HTTP sin lidiar con complejos tokens de autenticación OAuth de Google).
4. Haz clic en el botón azul **Implementar** en la parte inferior.
5. **Otorgar Accesos (Si aplica):**
   - Google te pedirá autorizar al script para modificar la hoja de cálculo.
   - Haz clic en **Autorizar acceso**.
   - Selecciona tu cuenta de Google.
   - Aparecerá un aviso de "Google no ha verificado esta aplicación" (es normal para scripts personales). Haz clic en **Configuración avanzada** (abajo a la izquierda) y luego en **Ir a Proyecto sin título (no seguro)**.
   - Haz clic en **Permitir**.
6. Una vez completado, verás una ventana con la **URL de la aplicación web**.
7. Haz clic en **Copiar** al lado de la URL. Debería verse similar a esto:
   `https://script.google.com/macros/s/AKfycbz...y4fg/exec`

---

## 🔗 Paso 4: Vincular la URL en el Dashboard del Clasificador
1. Entra a tu Dashboard en **`https://localhost:8000`**.
2. Dirígete a la sección **Configuración de Tiempos y Sensibilidad** (columna derecha).
3. Busca el campo **Google Apps Script Webhook URL** en la parte inferior.
4. Pega la URL completa que copiaste de Google Apps Script.
5. Haz clic en el botón **Guardar Parámetros**.
6. Al instante, verás un mensaje flotante (Toast) en el navegador:
   - Si todo está correcto y tienes internet: **"Conexión con Google Sheets verificada ✓"**.
   - Al mismo tiempo, en la parte superior derecha del header, el badge de **Nube** cambiará de color rojo/amarillo a **verde** (`Nube: Conectada`).

---

## 🧪 Paso 5: Probar el Funcionamiento en Tiempo Real
1. En el panel **Control de Banda Transportadora** (columna izquierda), localiza la sección de simulación.
2. Haz clic en el botón **Cat 1**.
3. Verás una notificación en pantalla indicando que la simulación fue enviada.
4. Ve a la tabla inferior de historial: notarás que el registro aparece con un badge verde de `☁️ Sincronizado`.
5. Abre la pestaña de tu **Google Sheet**: ¡verás cómo aparece una nueva fila con la fecha, hora, categoría 1 y el código de prueba de forma instantánea!
6. Haz una prueba con **Cat 2** o **Cat 3** y verifica que se listen del mismo modo.

---

## 🛜 ¿Cómo funciona el Sistema de Fallo de Internet? (Offline Caching)
- Si tu computadora pierde la conexión a internet, o si la URL del webhook es eliminada, el badge superior de **Nube** se pondrá en rojo y aparecerá una advertencia no invasiva en la parte inferior izquierda indicando **"Respaldo Local Activado"**.
- Cualquier caja que escanees (con cámara o con los botones de prueba) se guardará localmente en la base de datos SQLite con el estado `Local 💾 (Pendiente)`.
- El servidor de Python cuenta con una tarea en segundo plano que vigila el estado de internet. En cuanto se restablezca la conexión, el servidor detectará que hay escaneos pendientes y los enviará automáticamente a Google Sheets en lote, cambiando su estado visual a `☁️ Sincronizado` sin que pierdas ningún dato.
