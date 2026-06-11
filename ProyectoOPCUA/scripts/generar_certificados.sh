#!/bin/bash
# ============================================================
# generar_certificados.sh
# Genera certificados SSL/TLS autofirmados con SAN (Subject
# Alternative Name) para que los navegadores móviles los acepten.
#
# IMPORTANTE: Los navegadores modernos exigen SAN. Sin este campo,
# Chrome/Firefox en Android/iOS rechazan el certificado.
#
# USO:
#   cd /ruta/a/ProyectoOPCUA
#   chmod +x scripts/generar_certificados.sh
#   ./scripts/generar_certificados.sh
# ============================================================

set -e

CERT_DIR="certs"
mkdir -p "$CERT_DIR"

# Detectar IPs locales de la Raspberry Pi para incluirlas en SAN
ETH_IP=$(ip addr show eth0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1 | head -1)
WLAN_IP=$(ip addr show wlan0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1 | head -1)
HOSTNAME=$(hostname)

echo "================================================"
echo "  Generando Certificados SSL/TLS con SAN"
echo "================================================"
echo " Hostname : $HOSTNAME"
echo " Ethernet : ${ETH_IP:-'no detectada'}"
echo " WiFi     : ${WLAN_IP:-'no detectada'}"
echo ""

# Construir lista de SANs (IPs y nombres)
SAN="DNS:localhost,DNS:$HOSTNAME,IP:127.0.0.1"
[ -n "$ETH_IP"  ] && SAN="$SAN,IP:$ETH_IP"
[ -n "$WLAN_IP" ] && SAN="$SAN,IP:$WLAN_IP"

echo " SANs incluidos: $SAN"
echo ""

# Crear archivo de configuracion OpenSSL temporal
cat > /tmp/openssl_rpi.cnf << EOF
[req]
default_bits       = 2048
prompt             = no
default_md         = sha256
distinguished_name = dn
x509_extensions    = v3_req

[dn]
C  = CO
ST = Colombia
L  = Bogota
O  = UNAL ProyectoOPCUA
OU = Automatizacion Industrial
CN = $HOSTNAME

[v3_req]
subjectAltName     = $SAN
keyUsage           = critical, digitalSignature, keyEncipherment
extendedKeyUsage   = serverAuth
basicConstraints   = CA:FALSE
EOF

# Generar clave privada y certificado en un solo comando
openssl req -x509 \
    -newkey rsa:2048 \
    -keyout "$CERT_DIR/key.pem" \
    -out    "$CERT_DIR/cert.pem" \
    -sha256 \
    -days   3650 \
    -nodes \
    -config /tmp/openssl_rpi.cnf

rm -f /tmp/openssl_rpi.cnf

# Verificar
echo ""
echo "✓ Certificados generados en $CERT_DIR/"
echo "  - $CERT_DIR/cert.pem"
echo "  - $CERT_DIR/key.pem"
echo ""
echo "SANs incluidos en el certificado:"
openssl x509 -in "$CERT_DIR/cert.pem" -noout -ext subjectAltName 2>/dev/null || true
echo ""
echo "================================================"
echo " PROXIMOS PASOS:"
echo "================================================"
echo " 1. Compilar con soporte SSL:"
echo "    make USE_SSL=1"
echo ""
echo " 2. Ejecutar el sistema:"
echo "    ./bin/clasificador_plc"
echo ""
echo " 3. Desde tu dispositivo movil:"
echo "    Abrir: https://<IP-de-la-Raspberry>:8443"
echo ""
echo " 4. El navegador mostrara una advertencia de certificado."
echo "    En Chrome Android: 'Configuracion avanzada' -> 'Continuar'"
echo "    En Safari iOS:     'Mostrar detalles' -> 'Visitar este sitio'"
echo ""
echo " NOTA: Cada dispositivo debe aceptar el certificado"
echo "       UNA SOLA VEZ. Despues funciona normalmente."
echo "================================================"
