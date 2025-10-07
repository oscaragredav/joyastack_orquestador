#!/bin/bash

# Script: init_worker.sh
# Descripción: Inicializa un Worker creando un OvS local y conectando interfaces
# Parámetros: $1=nombreOvS, $2=InterfacesAConectar (separadas por comas)

# Validar parámetros
if [ $# -ne 2 ]; then
    echo "Uso: $0 <nombreOvS> <InterfacesAConectar>"
    echo "Ejemplo: $0 br-int ens4"
    exit 1
fi

NOMBRE_OVS=$1
INTERFACES=$2

echo "=== Inicializando Worker ==="
echo "OvS: $NOMBRE_OVS"
echo "Interfaces: $INTERFACES"

# Función para verificar si un bridge existe
bridge_exists() {
    ovs-vsctl br-exists $1 2>/dev/null
}

# Crear OvS local si no existe
if ! bridge_exists $NOMBRE_OVS; then
    echo "Creando bridge OvS: $NOMBRE_OVS"
    sudo ovs-vsctl add-br $NOMBRE_OVS
    if [ $? -eq 0 ]; then
        echo "Bridge $NOMBRE_OVS creado exitosamente"
        sudo ip link set $NOMBRE_OVS up
    else
        echo "Error al crear el bridge $NOMBRE_OVS"
        exit 1
    fi
else
    echo "Bridge $NOMBRE_OVS ya existe"
fi

# Conectar interfaces al OvS
IFS=',' read -ra INTERFACE_ARRAY <<< "$INTERFACES"
for interface in "${INTERFACE_ARRAY[@]}"; do
    # Limpiar espacios en blanco
    interface=$(echo $interface | xargs)
    
    # Verificar si la interfaz existe
    if ! ip link show $interface &> /dev/null; then
        echo "La interfaz $interface no existe"
        continue
    fi
    
    # Verificar si la interfaz ya está conectada al bridge
    if ovs-vsctl port-to-br $interface &> /dev/null; then
        current_bridge=$(ovs-vsctl port-to-br $interface)
        if [ "$current_bridge" = "$NOMBRE_OVS" ]; then
            echo "Interfaz $interface ya está conectada a $NOMBRE_OVS"
            continue
        fi
    fi
    
    # Limpiar configuración IP de la interfaz
    echo "Limpiando configuración IP de $interface..."
    sudo ip addr flush dev $interface
    
    # Conectar interfaz al OvS
    echo "Conectando $interface a $NOMBRE_OVS..."
    sudo ovs-vsctl add-port $NOMBRE_OVS $interface
    
    if [ $? -eq 0 ]; then
        echo "Interfaz $interface conectada exitosamente"
        sudo ip link set $interface up
    else
        echo "Error al conectar $interface"
    fi
done

# Mostrar configuración final del bridge
echo ""
echo "=== Configuración final del bridge $NOMBRE_OVS ==="
sudo ovs-vsctl show $NOMBRE_OVS

echo ""
echo "=== Worker inicializado exitosamente ==="
