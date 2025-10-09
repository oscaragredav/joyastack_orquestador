#!/bin/bash

# Script: vm_create.sh
# Descripción: Crea una VM usando QEMU y la conecta al OvS con VLAN ID específico
# Parámetros:
#  $1 = NombreVM
#  $2 = NombreOvS
#  $3 = VLAN_ID
#  $4 = PuertoVNC
#  $5 = CPUs
#  $6 = RAM MB
#  $7 = Disco GB

# Validar parámetros
if [ $# -ne 8 ]; then
    echo "Error: Número incorrecto de parámetros."
    echo "Uso: $0 <NombreVM> <OvS> <VLAN> <VNC_PORT> <CPUs> <RAM_MB> <DISK_GB> <NUM_IFACES>"
    echo "Ejemplo: $0 VM1 br-int 100 1 1 256 1 1"
    exit 1
fi

VM_NAME=$1
OVS_NAME=$2
VLAN_ID=$3
VNC_PORT=$4
CPUS=$5
RAM=$6
DISK=$7

# Configuraciones
IMAGE_DIR="/home/ubuntu"  # Directorio donde están las imágenes
CIRROS_IMAGE="cirros-0.5.1-x86_64-disk.img"  # Imagen de CIRROS
TAP_INTERFACE="${OVS_NAME}-${VM_NAME}-tap" # Nombre de interfaz TAP
MAC_ADDRESS="20:19:37:33:ee:$(printf "%02x" "$VNC_PORT")" # MAC

echo "=== Creando VM: $VM_NAME ==="
echo "OvS: $OVS_NAME"
echo "VLAN ID: $VLAN_ID"
echo "Puerto VNC: $VNC_PORT"
echo "Interfaz TAP: $TAP_INTERFACE"
echo "MAC Address: $MAC_ADDRESS"

# Verificar que el bridge OvS existe
if ! sudo ovs-vsctl br-exists $OVS_NAME; then
    echo "Error: El bridge $OVS_NAME no existe"
    echo "Ejecute primero init_worker.sh"
    exit 1
fi


# ===========================================
# Crear una o varias interfaces TAP
# ===========================================
NUM_IFACES=${8:-1}   # nuevo parámetro opcional, por defecto 1 interfaz
echo "Número de interfaces a crear: $NUM_IFACES"

for IF in $(seq 1 $NUM_IFACES); do
    TAP_INTERFACE="${OVS_NAME}-${VM_NAME}-tap${IF}"
    echo "→ Creando TAP ${TAP_INTERFACE}..."
    ip tuntap add mode tap name $TAP_INTERFACE
    ip link set dev $TAP_INTERFACE up
    ovs-vsctl add-port $OVS_NAME $TAP_INTERFACE
    echo "   TAP ${TAP_INTERFACE} creada y conectada (sin VLAN todavía)"
done

if [ $? -eq 0 ]; then
    echo "Interfaz conectada al OvS con VLAN tag $VLAN_ID"
else
    echo "Error al conectar interfaz al OvS"
    # Limpiar interfaz TAP creada
    sudo ip link delete $TAP_INTERFACE 2>/dev/null
    exit 1
fi

# Crear y ejecutar la VM con qemu-system-x86_64
echo "Iniciando VM con QEMU..."

## OJO: INVESTIGAR COMO IMPLEMENTAR LO DEL DISCO
qemu-system-x86_64 \
    -enable-kvm \
    -vnc 0.0.0.0:"$VNC_PORT" \
    -netdev tap,id="${VM_NAME}"-netdev,ifname="$TAP_INTERFACE",script=no,downscript=no \
    -device e1000,netdev="${VM_NAME}"-netdev,mac="$MAC_ADDRESS" \
    -daemonize \
    -snapshot \
    -name "$VM_NAME" \
    -smp "$CPUS" \
    -m "$RAM" \
    ${IMAGE_DIR}/${CIRROS_IMAGE}

if [ $? -eq 0 ]; then
    echo "VM $VM_NAME iniciada exitosamente"

    # Obtener PID del proceso QEMU
    sleep 1
    qemu_pid=$(ps aux | grep "qemu-system-x86_64" | grep "$TAP_INTERFACE" | grep -v grep | awk '{print $2}')

    echo ""
    echo "=== Información de la VM ==="
    echo "Nombre: $VM_NAME"
    echo "PID QEMU: $qemu_pid"
    echo "Interfaz TAP: $TAP_INTERFACE"
    echo "MAC Address: $MAC_ADDRESS"
    echo "VLAN ID: $VLAN_ID"
    echo "Puerto VNC: $VNC_PORT"
    echo "Acceso VNC: vnc://$(hostname -I | cut -d' ' -f1):$((5900 + VNC_PORT))"
    echo "Imagen: ${IMAGE_DIR}/${CIRROS_IMAGE}"
    echo "Modo: Snapshot (cambios no persistentes)"

else
    echo "Error al iniciar la VM"
    echo "Limpiando recursos..."
    sudo ovs-vsctl --if-exists del-port "$OVS_NAME" "$TAP_INTERFACE"
    sudo ip link delete "$TAP_INTERFACE" 2>/dev/null
    exit 1
fi

echo ""
echo "=== VM $VM_NAME creada exitosamente ==="
echo ""
