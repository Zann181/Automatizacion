@echo off
title Configurador de Red Industrial - OPC UA
color 0A

echo ==========================================================
echo  Configurando Red Industrial (Ethernet Directo) en Windows
echo ==========================================================
echo.
echo Asignando IP Fija: 192.168.10.11
echo.

netsh interface ipv4 set address name="Ethernet" static 192.168.10.11 255.255.255.0
if %errorlevel% neq 0 (
    color 0C
    echo [ERROR CRITICO] Fallo al cambiar la IP.
    echo.
    echo Por favor verifica lo siguiente:
    echo 1. Debes darle CLIC DERECHO a este archivo y seleccionar
    echo    "Ejecutar como administrador".
    echo 2. Asegurate de que el cable este conectado.
    echo 3. Verifica en tu Panel de Control que la conexion
    echo    se llame exactamente "Ethernet".
) else (
    echo [EXITO] Tu PC ahora tiene la IP 192.168.10.11.
    echo Puedes iniciar el Simulador PLC en Python.
)

echo.
pause
