CXX      = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -I./include -pthread

SRC_DIR = src
OBJ_DIR = build
BIN_DIR = bin
TARGET  = $(BIN_DIR)/clasificador_plc

# ---- SSL (requerido para camara en dispositivos moviles) ----
# Compilar con: make USE_SSL=1  (default: activado)
USE_SSL ?= 1

ifeq ($(USE_SSL), 1)
    CXXFLAGS += -DCPPHTTPLIB_OPENSSL_SUPPORT
    LDFLAGS   = -lopen62541 -lsqlite3 -lssl -lcrypto -latomic
    $(info [Makefile] Compilando CON SSL/HTTPS (USE_SSL=1))
else
    LDFLAGS   = -lopen62541 -lsqlite3 -latomic
    $(info [Makefile] Compilando SIN SSL/HTTPS (USE_SSL=0))
endif

# Descubrir todos los .cpp en src/ automaticamente
SRCS = $(wildcard $(SRC_DIR)/*.cpp)
OBJS = $(patsubst $(SRC_DIR)/%.cpp,$(OBJ_DIR)/%.o,$(SRCS))

# ---- Reglas ----
.PHONY: all clean install-deps certs run

all: directories httplib jsqr $(TARGET)
	@echo ""
	@echo "=== Compilacion exitosa ==="
	@echo "Ejecutable : $(TARGET)"
	@echo "Uso        : ./$(TARGET)"
ifeq ($(USE_SSL), 1)
	@echo "Dashboard  : https://<IP-RaspberryPi>:8443"
	@echo "NOTA: Genera certificados primero si no existen:"
	@echo "      ./scripts/generar_certificados.sh"
endif
	@echo ""

directories:
	@mkdir -p $(OBJ_DIR) $(BIN_DIR) certs web/js

# httplib.h: ya incluida en el repo (descargada en Windows)
# Si falta, intenta descargarla (requiere internet)
httplib: include/httplib.h

include/httplib.h:
	@if [ -f include/httplib.h ]; then \
	    echo "[Makefile] httplib.h ya existe. OK."; \
	else \
	    echo "[Makefile] Descargando httplib.h..."; \
	    wget -q https://raw.githubusercontent.com/yhirose/cpp-httplib/master/httplib.h \
	        -O include/httplib.h 2>/dev/null || \
	    curl -sL https://raw.githubusercontent.com/yhirose/cpp-httplib/master/httplib.h \
	        -o include/httplib.h || \
	    (echo "[ERROR] No se pudo descargar httplib.h. Copia el archivo manualmente." && exit 1); \
	fi

# jsQR: ya incluida en el repo (descargada en Windows)
jsqr: web/js/jsqr.min.js

web/js/jsqr.min.js:
	@if [ -f web/js/jsqr.min.js ]; then \
	    echo "[Makefile] jsqr.min.js ya existe. OK."; \
	else \
	    echo "[Makefile] Descargando jsQR..."; \
	    wget -q https://raw.githubusercontent.com/cozmo/jsQR/master/dist/jsQR.js \
	        -O web/js/jsqr.min.js 2>/dev/null || \
	    curl -sL https://raw.githubusercontent.com/cozmo/jsQR/master/dist/jsQR.js \
	        -o web/js/jsqr.min.js || \
	    (echo "[ERROR] No se pudo descargar jsQR. Copia el archivo manualmente." && exit 1); \
	fi

# Generar certificados SSL
certs:
	@bash scripts/generar_certificados.sh

# Enlazar ejecutable
$(TARGET): $(OBJS)
	$(CXX) $(OBJS) -o $@ $(LDFLAGS)

# Compilar cada .cpp
$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Limpiar build
clean:
	rm -rf $(OBJ_DIR)/*.o $(TARGET)

# Instalar dependencias en Raspberry Pi OS / Debian
install-deps:
	sudo apt-get update
	sudo apt-get install -y \
	    build-essential g++ wget curl \
	    libsqlite3-dev sqlite3 \
	    libopen62541-dev \
	    tcpdump \
	    libssl-dev openssl

# Flujo completo en una Raspberry Pi nueva
setup: install-deps certs all

# Ejecutar directamente
run: all
	./$(TARGET)
