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
#  $8 = NUM_IFACES (número de interfaces TAP)

START_TIME=$(date +%s)

# Auto-fix CRLF si existe (DEBE SER LO PRIMERO)
if grep -q $'\r' "$0" 2>/dev/null; then
  sed -i 's/\r$//' "$0"
  exec /usr/bin/env bash "$0" "$@"
fi

# Función para logging con timestamp
log() {
    echo "[$(date +'%H:%M:%S')] $*"
}

error_exit() {
    log "❌ ERROR: $*"
    exit 1
}

# Validar parámetros
if [ $# -ne 8 ]; then
    error_exit "Número incorrecto de parámetros (recibidos: $#, esperados: 8)"
fi

VM_NAME=$1
OVS_NAME=$2
VLAN_ID=$3
VNC_PORT=$4
CPUS=$5
RAM=$6
DISK=$7
NUM_IFACES=$8

# Validaciones de parámetros
[[ "$CPUS" =~ ^[0-9]+$ ]] || error_exit "CPUs debe ser un número (recibido: '$CPUS')"
[[ "$RAM" =~ ^[0-9]+$ ]] || error_exit "RAM debe ser un número (recibido: '$RAM')"
[[ "$VNC_PORT" =~ ^[0-9]+$ ]] || error_exit "VNC_PORT debe ser un número (recibido: '$VNC_PORT')"
[ "$CPUS" -gt 0 ] || error_exit "CPUs debe ser mayor a 0"
[ "$RAM" -ge 64 ] || error_exit "RAM debe ser al menos 64MB"
[ "$VNC_PORT" -ge 0 ] && [ "$VNC_PORT" -le 9999 ] || error_exit "VNC_PORT debe estar entre 0-9999"

# Configuraciones
IMAGE_DIR="/home/ubuntu"
CIRROS_IMAGE="cirros-0.5.1-x86_64-disk.img"
TAP_INTERFACE="${OVS_NAME}-${VM_NAME}-tap"
MAC_ADDRESS="20:19:37:33:ee:$(printf "%02x" "$VNC_PORT")"

log "========================================="
log "=== Creando VM: $VM_NAME ==="
log "========================================="
log "OvS: $OVS_NAME"
log "VLAN ID: $VLAN_ID"
log "Puerto VNC: $VNC_PORT (Display: :$VNC_PORT → puerto $((5900 + VNC_PORT)))"
log "CPUs: $CPUS"
log "RAM: ${RAM}MB"
log "Disco: ${DISK}GB"
log "Interfaz TAP: $TAP_INTERFACE"
log "MAC Address: $MAC_ADDRESS"
log "========================================="

# 1. Verificar que el bridge OvS existe
log "🔍 Verificando bridge OvS..."
if ! ovs-vsctl br-exists "$OVS_NAME" 2>/dev/null; then
    error_exit "El bridge $OVS_NAME no existe. Ejecute primero init_worker.sh"
fi
log "✅ Bridge $OVS_NAME encontrado"

# 2. Verificar que QEMU está instalado
log "🔍 Verificando QEMU..."
if ! command -v qemu-system-x86_64 &>/dev/null; then
    error_exit "qemu-system-x86_64 no está instalado"
fi
log "✅ QEMU instalado: $(qemu-system-x86_64 --version | head -n1)"

# 3. Limpiar VM existente si hay conflicto
log "🔍 Buscando procesos conflictivos..."
existing_pid=$(pgrep -f "qemu-system-x86_64.*-name $VM_NAME" 2>/dev/null || true)
if [ -n "$existing_pid" ]; then
    log "⚠️  VM $VM_NAME ya existe (PID: $existing_pid). Limpiando..."
    kill -9 "$existing_pid" 2>/dev/null || true
    sleep 2
    log "✅ Proceso anterior eliminado"
fi

# 4. Limpiar interfaz TAP si existe (MEJORADO: limpiar en OvS primero)
log "🧹 Limpiando recursos previos..."
# IMPORTANTE: Primero eliminar del OvS, luego la interfaz
ovs-vsctl --if-exists del-port "$OVS_NAME" "$TAP_INTERFACE" 2>/dev/null || true
sleep 1  # Dar tiempo a OvS para procesar

if ip link show "$TAP_INTERFACE" &>/dev/null; then
    log "🧹 Eliminando interfaz TAP huérfana: $TAP_INTERFACE"
    ip link delete "$TAP_INTERFACE" 2>/dev/null || true
    sleep 1
fi
log "✅ Limpieza completada"

# 5. Verificar/Descargar imagen
log "🔍 Verificando imagen CirrOS..."
if [ ! -f "${IMAGE_DIR}/${CIRROS_IMAGE}" ]; then
    log "⚠️  Imagen no encontrada. Descargando CirrOS 0.5.1..."
    mkdir -p "$IMAGE_DIR" 2>/dev/null || true
    
    if ! wget -q --show-progress -O "${IMAGE_DIR}/${CIRROS_IMAGE}" \
         "https://download.cirros-cloud.net/0.5.1/cirros-0.5.1-x86_64-disk.img"; then
        error_exit "No se pudo descargar la imagen CirrOS"
    fi
    log "✅ Imagen descargada: ${IMAGE_DIR}/${CIRROS_IMAGE}"
else
    log "✅ Imagen encontrada: ${IMAGE_DIR}/${CIRROS_IMAGE}"
fi

# 5.1 Crear disco overlay para la VM
OVERLAY_DISK="${IMAGE_DIR}/${VM_NAME}_overlay.qcow2"

log "🔧 Creando disco overlay para la VM..."
if [ -f "$OVERLAY_DISK" ]; then
    log "⚠️  Disco overlay existente encontrado, reutilizando: $OVERLAY_DISK"
else
    if ! qemu-img create -f qcow2 -b "${IMAGE_DIR}/${CIRROS_IMAGE}" "$OVERLAY_DISK" "${DISK}G" >/dev/null 2>&1; then
    error_exit "No se pudo crear el disco overlay para la VM"
    fi
    log "✅ Disco overlay creado: $OVERLAY_DISK"
fi


# 6. Crear interfaz TAP
log "🔧 Creando interfaz TAP: $TAP_INTERFACE"
if ! ip tuntap add mode tap name "$TAP_INTERFACE" 2>&1; then
    error_exit "No se pudo crear la interfaz TAP"
fi
log "✅ Interfaz TAP creada"

# 7. Levantar la interfaz TAP
log "🔧 Levantando interfaz TAP..."
if ! ip link set dev "$TAP_INTERFACE" up 2>&1; then
    ip link delete "$TAP_INTERFACE" 2>/dev/null || true
    error_exit "No se pudo levantar la interfaz TAP"
fi
log "✅ Interfaz TAP activa"

# 8. Conectar TAP al OvS con VLAN tag
log "🔗 Conectando $TAP_INTERFACE a $OVS_NAME (VLAN $VLAN_ID)..."
if ! ovs-vsctl add-port "$OVS_NAME" "$TAP_INTERFACE" tag="$VLAN_ID" 2>&1; then
    ip link delete "$TAP_INTERFACE" 2>/dev/null || true
    error_exit "No se pudo conectar la interfaz al OvS"
fi
log "✅ Interfaz conectada al OvS"

# 9. Verificar que KVM está disponible (opcional pero recomendado)
if [ ! -e /dev/kvm ]; then
    log "⚠️  ADVERTENCIA: /dev/kvm no disponible, la VM será más lenta"
    KVM_FLAG=""
else
    KVM_FLAG="-enable-kvm"
    log "✅ KVM disponible (aceleración por hardware)"
fi

# 10. Iniciar VM con QEMU
log "🚀 Iniciando VM con QEMU..."
log "   Configuración: RAM=${RAM}MB, CPUs=$CPUS, VNC=:$VNC_PORT"

# Construir comando QEMU con validación
QEMU_CMD="qemu-system-x86_64 \
    $KVM_FLAG \
    -vnc 0.0.0.0:$VNC_PORT \
    -netdev tap,id=${VM_NAME}-netdev,ifname=$TAP_INTERFACE,script=no,downscript=no \
    -device e1000,netdev=${VM_NAME}-netdev,mac=$MAC_ADDRESS \
    -daemonize \
    -snapshot \
    -name $VM_NAME \
    -smp $CPUS \
    -m $RAM \
    -drive file=$OVERLAY_DISK,if=virtio,format=qcow2"

# Ejecutar QEMU y capturar salida
if ! $QEMU_CMD 2>&1; then
    log "❌ Comando QEMU falló"
    log "Comando ejecutado: $QEMU_CMD"
    # Limpiar recursos
    ovs-vsctl --if-exists del-port "$OVS_NAME" "$TAP_INTERFACE" 2>/dev/null || true
    ip link delete "$TAP_INTERFACE" 2>/dev/null || true
    exit 1
fi

# 11. Verificar que QEMU inició correctamente
log "🔍 Verificando inicio de QEMU..."
sleep 2

qemu_pid=$(pgrep -f "qemu-system-x86_64.*-name $VM_NAME" 2>/dev/null || true)

if [ -z "$qemu_pid" ]; then
    log "❌ QEMU no inició (proceso no encontrado)"
    log "Verificando logs del sistema..."
    dmesg | tail -n 20
    # Limpiar recursos
    ovs-vsctl --if-exists del-port "$OVS_NAME" "$TAP_INTERFACE" 2>/dev/null || true
    ip link delete "$TAP_INTERFACE" 2>/dev/null || true
    exit 1
fi

# 12. Verificar que el proceso está realmente corriendo
if ! ps -p "$qemu_pid" &>/dev/null; then
    error_exit "Proceso QEMU existe pero no está corriendo (PID: $qemu_pid)"
fi

log "✅ QEMU corriendo (PID: $qemu_pid)"

# 13. Guardar información de la VM
INFO_FILE="/tmp/${VM_NAME}_info.txt"
cat > "$INFO_FILE" << EOF
VM_NAME=$VM_NAME
PID=$qemu_pid
TAP_INTERFACE=$TAP_INTERFACE
VLAN_ID=$VLAN_ID
VNC_PORT=$VNC_PORT
MAC_ADDRESS=$MAC_ADDRESS
OVS_NAME=$OVS_NAME
RAM=$RAM
CPUS=$CPUS
DISK=$DISK
CREATED=$(date '+%Y-%m-%d %H:%M:%S')
IMAGE_BASE=${IMAGE_DIR}/${CIRROS_IMAGE}
OVERLAY_DISK=$OVERLAY_DISK
EOF

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

# 14. Mostrar resumen de éxito
HOST_IP=$(hostname -I | awk '{print $1}')
echo ""
log "========================================="
log "✅✅✅ VM $VM_NAME CREADA EXITOSAMENTE ✅✅✅"
log "========================================="
log "📋 Información de la VM:"
log "   Nombre: $VM_NAME"
log "   PID QEMU: $qemu_pid"
log "   Interfaz TAP: $TAP_INTERFACE"
log "   MAC Address: $MAC_ADDRESS"
log "   VLAN ID: $VLAN_ID"
log "   CPUs: $CPUS | RAM: ${RAM}MB | Disco: ${DISK}GB"
log ""
log "📺 Acceso VNC:"
log "   Directo: vnc://${HOST_IP}:$((5900 + VNC_PORT))"
log "   Display: :$VNC_PORT"
log ""
log "🔧 Comandos útiles:"
log "   Ver proceso: ps aux | grep $qemu_pid"
log "   Detener VM: kill $qemu_pid"
log "   Ver info: cat $INFO_FILE"
log "   Ver TAP: ip link show $TAP_INTERFACE"
log "   Ver en OvS: ovs-vsctl show"
log "========================================="
log "✅ Info guardada en: $INFO_FILE"
log "========================================="
log "⏱️ Tiempo total de creación: ${ELAPSED} segundos"
echo ""

# Retornar éxito explícito
exit 0