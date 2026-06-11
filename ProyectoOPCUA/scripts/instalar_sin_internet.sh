#!/bin/bash
# ============================================================
# instalar_sin_internet.sh
# Instala TODAS las dependencias del proyecto en la Raspberry Pi
# sin necesidad de conexion a internet directa.
#
# REQUISITO: Ejecutar este script en una maquina Linux/WSL
# que SI tenga internet, para descargar los .deb.
# Luego copiar la carpeta generada a la RPi.
#
# USO:
#   En PC con Linux o WSL (con internet):
#     chmod +x scripts/instalar_sin_internet.sh
#     ./scripts/instalar_sin_internet.sh --descargar
#
#   Luego copiar el proyecto completo a la RPi y ejecutar:
#     ./scripts/instalar_sin_internet.sh --instalar
# ============================================================

set -e

CACHE_DIR="./paquetes_offline"
ARCH="armhf"   # Raspberry Pi 3 = armhf (32-bit) | Pi 4/5 64-bit = arm64

PAQUETES=(
    "build-essential"
    "g++"
    "make"
    "libsqlite3-dev"
    "sqlite3"
    "libssl-dev"
    "openssl"
    "libopen62541-dev"
    "libopen62541-1"
    "tcpdump"
)

# ---- Deteccion automatica de arquitectura ----
if [ "$(uname -m)" = "aarch64" ]; then
    ARCH="arm64"
elif [ "$(uname -m)" = "armv7l" ] || [ "$(uname -m)" = "armv6l" ]; then
    ARCH="armhf"
fi

# ============================================================
# MODO 1: Descargar paquetes (en maquina con internet)
# ============================================================
if [ "$1" = "--descargar" ]; then
    echo "=========================================="
    echo " Descargando paquetes para Raspberry Pi"
    echo " Arquitectura detectada: $ARCH"
    echo "=========================================="

    mkdir -p "$CACHE_DIR"

    # Agregar repositorios de Raspberry Pi si no existen
    if ! grep -q "raspbian" /etc/apt/sources.list 2>/dev/null && \
       ! grep -q "raspberrypi" /etc/apt/sources.list.d/*.list 2>/dev/null; then
        echo "[INFO] Actualizando listas de paquetes..."
    fi

    sudo apt-get update -q

    echo ""
    echo "Descargando paquetes y sus dependencias..."
    cd "$CACHE_DIR"

    for pkg in "${PAQUETES[@]}"; do
        echo "  -> $pkg"
        apt-get download "$pkg" 2>/dev/null || \
        apt-get download "$(apt-cache depends --recurse --no-recommends --no-suggests \
            --no-conflicts --no-breaks --no-replaces --no-enhances \
            --no-pre-depends "$pkg" | grep "^\w" | sort -u)" 2>/dev/null || true
    done

    # Descargar con dependencias recursivas
    apt-get download $(apt-cache depends --recurse --no-recommends \
        --no-suggests --no-conflicts --no-breaks --no-replaces \
        --no-enhances "${PAQUETES[@]}" 2>/dev/null | grep "^\w" | sort -u) 2>/dev/null || true

    cd ..

    # Contar lo descargado
    COUNT=$(ls "$CACHE_DIR"/*.deb 2>/dev/null | wc -l)
    SIZE=$(du -sh "$CACHE_DIR" 2>/dev/null | cut -f1)

    echo ""
    echo "=========================================="
    echo " Descarga completa: $COUNT paquetes ($SIZE)"
    echo " Guardados en: $CACHE_DIR/"
    echo ""
    echo " SIGUIENTE PASO:"
    echo " Copia todo el proyecto a la Raspberry Pi:"
    echo ""
    echo "   scp -r . pi@192.168.10.10:~/ProyectoOPCUA"
    echo ""
    echo " Y en la Raspberry ejecuta:"
    echo "   ./scripts/instalar_sin_internet.sh --instalar"
    echo "=========================================="
    exit 0
fi

# ============================================================
# MODO 2: Instalar paquetes (en la Raspberry Pi)
# ============================================================
if [ "$1" = "--instalar" ]; then
    echo "=========================================="
    echo " Instalando dependencias en Raspberry Pi"
    echo "=========================================="

    # Verificar que existen los .deb
    if [ ! -d "$CACHE_DIR" ] || [ -z "$(ls "$CACHE_DIR"/*.deb 2>/dev/null)" ]; then
        echo "[ERROR] No se encontro la carpeta '$CACHE_DIR' con paquetes .deb"
        echo "Ejecuta primero en una maquina con internet:"
        echo "  ./scripts/instalar_sin_internet.sh --descargar"
        exit 1
    fi

    COUNT=$(ls "$CACHE_DIR"/*.deb | wc -l)
    echo "Instalando $COUNT paquetes desde $CACHE_DIR/..."

    # Instalar todos los .deb de una vez (dpkg resuelve orden)
    sudo dpkg -i "$CACHE_DIR"/*.deb 2>/dev/null || true
    # Corregir dependencias rotas si las hay
    sudo apt-get install -f --no-download -y 2>/dev/null || true

    echo ""
    echo "=========================================="
    echo " Verificando instalacion..."
    echo "=========================================="

    check() {
        if command -v "$1" &>/dev/null || dpkg -l "$2" &>/dev/null 2>&1; then
            echo "  ✓ $2"
        else
            echo "  ✗ $2 (FALTA)"
        fi
    }

    check "g++"          "g++"
    check "make"         "make"
    check "openssl"      "openssl"
    check "sqlite3"      "sqlite3"
    check "pkg-config"   "libopen62541-dev"
    check "pkg-config"   "libssl-dev"

    echo ""
    echo "=========================================="
    echo " SIGUIENTE PASO: Compilar el proyecto"
    echo "   cd ~/ProyectoOPCUA"
    echo "   ./scripts/generar_certificados.sh"
    echo "   make"
    echo "   ./bin/clasificador_plc"
    echo "=========================================="
    exit 0
fi

# Sin argumentos: mostrar ayuda
echo "Uso:"
echo "  En PC con internet (Linux/WSL):"
echo "    ./scripts/instalar_sin_internet.sh --descargar"
echo ""
echo "  En Raspberry Pi (sin internet):"
echo "    ./scripts/instalar_sin_internet.sh --instalar"
