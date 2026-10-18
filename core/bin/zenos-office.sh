#!/bin/bash
# ZENOS Office launcher - forces KDE Breeze Dark so LibreOffice matches the ZENOS desktop.
unset WAYLAND_DISPLAY
export GDK_BACKEND=x11
export DISPLAY=:1
export XAUTHORITY=/home/zenos/.Xauthority
export SAL_USE_VCLPLUGIN=kf6
export QT_QPA_PLATFORM=xcb
export QT_QPA_PLATFORMTHEME=kde
export XDG_CURRENT_DESKTOP=KDE
exec libreoffice "$@"
