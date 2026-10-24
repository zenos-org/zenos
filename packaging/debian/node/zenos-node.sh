# ZENOS: every Node program refuses CA certificates and keys ZENOS distrusts (/usr/lib/zenos/zdistrust.js).
# Node carries its own root list, so fixing the system trust store alone does not protect Node programs.
if [ -r /usr/lib/zenos/zdistrust.js ]; then
    case " $NODE_OPTIONS " in
        *zdistrust.js*) ;;
        *) export NODE_OPTIONS="--require=/usr/lib/zenos/zdistrust.js${NODE_OPTIONS:+ $NODE_OPTIONS}" ;;
    esac
fi
