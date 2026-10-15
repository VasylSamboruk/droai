#!/bin/bash
# wifi-mode.sh — перемикання wlan0 між точкою доступу R2D2 і клієнтом Wi-Fi.
#
# Чому це потрібно окремим скриптом:
#   wpa_supplicant тут працює в AP-режимі (mode=2, ap_scan=2), тому поки
#   точка піднята — сканування мереж неможливе взагалі.
#
# Безпека: режим клієнта за замовчуванням НЕ зберігається на диск.
#   Постійний конфіг (/etc/wpa_supplicant/wpa_supplicant.conf) лишається
#   AP-шним, тож будь-яке перезавантаження повертає точку доступу R2D2.
#   Плюс сторожовий таймер: не отримали IP за N секунд — AP піднімається сам.
#
# Використання:
#   sudo ./wifi-mode.sh scan
#   sudo ./wifi-mode.sh client "МояМережа" "пароль" [КРАЇНА] [СЕКУНД]
#   sudo ./wifi-mode.sh ap
#   sudo ./wifi-mode.sh status

set -u

IFACE=wlan0
AP_CONF=/etc/wpa_supplicant/wpa_supplicant.conf
CLI_CONF=/tmp/wpa_client.conf
LOG=/tmp/wifi-mode.log

need_root() { [ "$(id -u)" = 0 ] || { echo "потрібен root (sudo)"; exit 1; }; }

have_ip() { ip -4 addr show "$IFACE" 2>/dev/null | grep -q "inet "; }

stop_all() {
    systemctl stop dnsmasq           2>/dev/null
    ifdown --force "$IFACE"          2>/dev/null
    pkill -f "wpa_supplicant.*$IFACE" 2>/dev/null
    pkill -f "dhclient.*$IFACE"       2>/dev/null
    sleep 1
    ip addr flush dev "$IFACE"       2>/dev/null
    ip link set "$IFACE" up          2>/dev/null
    sleep 1
}

mode_ap() {
    stop_all
    rm -f "/run/network/ifstate.$IFACE"
    ifup "$IFACE"
    systemctl start dnsmasq
    sleep 1
    echo "режим: ТОЧКА ДОСТУПУ  ssid=R2D2  ip=10.0.0.1"
    ip -4 addr show "$IFACE" | sed -n 's/^ *//p'
}

do_scan() {
    # для сканування треба вийти з AP-режиму
    stop_all
    rfkill unblock wifi 2>/dev/null
    echo "сканую (це вимкнуло точку доступу; 'ap' поверне її)..."
    iw dev "$IFACE" scan 2>/dev/null \
        | awk '/^BSS/{b=$2} /SSID:/{s=substr($0,index($0,":")+2)}
               /signal:/{g=$2}
               /SSID:/{ if (s!="") printf "  %-32s %s dBm\n", s, g }' \
        | sort -u
    echo
    echo "далі:  sudo $0 client \"SSID\" \"пароль\""
    echo "назад: sudo $0 ap"
}

client_run() {
    local ssid="$1" psk="$2" country="$3" revert="$4"

    umask 077
    {
        echo "ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev"
        echo "update_config=1"
        echo "country=$country"
        echo "network={"
        echo "    ssid=\"$ssid\""
        if [ -n "$psk" ]; then echo "    psk=\"$psk\""; else echo "    key_mgmt=NONE"; fi
        echo "    scan_ssid=1"
        echo "}"
    } > "$CLI_CONF"

    stop_all
    iw reg set "$country" 2>/dev/null

    wpa_supplicant -B -i "$IFACE" -c "$CLI_CONF"
    for i in $(seq 1 15); do
        st=$(wpa_cli -i "$IFACE" status 2>/dev/null | sed -n 's/^wpa_state=//p')
        echo "  wpa_state=$st"
        [ "$st" = "COMPLETED" ] && break
        sleep 1
    done

    dhclient -1 -v "$IFACE"

    if have_ip; then
        echo "режим: КЛІЄНТ  ssid=$ssid"
        ip -4 addr show "$IFACE" | sed -n 's/^ *//p'
        echo
        echo "Заходьте по SSH на цю адресу, або на R2D2.local (працює avahi)."
        echo "Щоб зробити постійним: sudo $0 persist"
        echo "Щоб повернути точку:   sudo $0 ap   (або просто перезавантажити)"
    else
        echo "IP не отримано — повертаю точку доступу"
        mode_ap
        return 1
    fi

    # сторожовий таймер: якщо звʼязок відвалиться — піднімемо AP назад
    if [ "$revert" -gt 0 ]; then
        (
            sleep "$revert"
            if ! have_ip; then
                echo "[watchdog] IP зник — повертаю AP" >> "$LOG"
                mode_ap >> "$LOG" 2>&1
            fi
        ) &
    fi
}

persist() {
    [ -f "$CLI_CONF" ] || { echo "немає $CLI_CONF — спершу 'client'"; exit 1; }
    rw
    cp -a "$AP_CONF" "$AP_CONF.ap-backup"
    cp "$CLI_CONF" "$AP_CONF"
    chmod 600 "$AP_CONF"
    # статична 10.0.0.1 більше не потрібна — переводимо на DHCP
    cp -a /etc/network/interfaces.d/wlan.conf /etc/network/interfaces.d/wlan.conf.ap-backup
    printf '# allow-hotplug wlan0\n\niface wlan0 inet dhcp\n    wpa-conf %s\n' \
        "$AP_CONF" > /etc/network/interfaces.d/wlan.conf
    systemctl disable dnsmasq
    sync
    ro
    echo "збережено. Відкат: sudo $0 unpersist"
}

unpersist() {
    rw
    [ -f "$AP_CONF.ap-backup" ] && mv "$AP_CONF.ap-backup" "$AP_CONF"
    [ -f /etc/network/interfaces.d/wlan.conf.ap-backup ] && \
        mv /etc/network/interfaces.d/wlan.conf.ap-backup /etc/network/interfaces.d/wlan.conf
    systemctl enable dnsmasq
    sync
    ro
    echo "відкочено до режиму точки доступу (діє після reboot або 'ap')"
}

status() {
    echo "--- $IFACE ---"
    ip -4 addr show "$IFACE" | sed -n 's/^ *//p'
    echo "--- wpa ---"
    wpa_cli -i "$IFACE" status 2>/dev/null | grep -E "wpa_state|ssid|mode|ip_address"
    echo "--- dnsmasq ---"
    systemctl is-active dnsmasq
    echo "--- постійний конфіг ---"
    grep -E "mode=|ssid=" "$AP_CONF" 2>/dev/null | sed 's/^/  /'
}

need_root
cmd=${1:-status}
case "$cmd" in
    scan)   do_scan ;;
    ap)     mode_ap ;;
    status) status ;;
    persist)   persist ;;
    unpersist) unpersist ;;
    client)
        ssid=${2:-}; psk=${3:-}; country=${4:-UA}; revert=${5:-0}
        [ -n "$ssid" ] || { echo "вкажіть SSID"; exit 1; }
        # Відʼєднуємось від терміналу: SSH-сесія помре разом із точкою доступу,
        # а робота має доїхати до кінця.
        echo "перемикаюсь у фоні, лог: $LOG"
        echo "через ~20 c підключіться до своєї мережі і: ssh root@R2D2.local"
        setsid nohup "$0" _client "$ssid" "$psk" "$country" "$revert" \
            >> "$LOG" 2>&1 < /dev/null &
        sleep 1
        ;;
    _client)
        echo "=== $(date -u) client $2 ==="
        client_run "$2" "$3" "$4" "$5"
        ;;
    *) echo "команди: scan | client SSID PASS [КРАЇНА] [СЕК] | ap | persist | unpersist | status" ;;
esac
