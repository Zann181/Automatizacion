import subprocess
import sys
import os

def download_wheels():
    # Detect target Python version and architecture
    py_version = input("Introduce la version de Python de la Raspberry Pi (ej. 3.9, 3.10, 3.11) [Por defecto: 3.9]: ").strip()
    if not py_version:
        py_version = "3.9"
        
    arch = input("Introduce la arquitectura de la Raspberry Pi (aarch64 o armv7l) [Por defecto: aarch64]: ").strip()
    if not arch:
        arch = "aarch64"
        
    # Translate architecture to pip platform tag
    # aarch64 -> manylinux2014_aarch64
    # armv7l -> manylinux_2_17_armv7l
    platform_tag = f"manylinux2014_{arch}"
    if arch == "armv7l":
        platform_tag = "manylinux_2_17_armv7l"
        
    # Create wheels directory
    os.makedirs("wheels", exist_ok=True)
    
    # ABI tag logic: cp39 for 3.9, cp310 for 3.10, cp311 for 3.11
    version_clean = py_version.replace(".", "")
    abi_tag = f"cp{version_clean}"
    
    # We will run pip download
    cmd = [
        sys.executable, "-m", "pip", "download",
        "--only-binary=:all:",
        "--platform", platform_tag,
        "--python-version", py_version,
        "--implementation", "cp",
        "--abi", abi_tag,
        "-d", "wheels",
        "-r", "requirements.txt"
    ]
    
    print(f"\nEjecutando comando de descarga:\n{' '.join(cmd)}\n")
    try:
        subprocess.run(cmd, check=True)
        print("\n[OK] Dependencias descargadas con exito en la carpeta 'wheels/'.")
        print("Ahora puedes copiar todo este directorio a la Raspberry Pi.")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Ocurrio un error al descargar las ruedas: {e}")
        print("Asegurate de tener conexion a internet y de haber especificado la version de Python y arquitectura correctas.")

if __name__ == "__main__":
    download_wheels()
