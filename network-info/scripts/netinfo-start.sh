#!/bin/sh
# System startup script for DeltaMaker Skybox 3D printer code

### BEGIN INIT INFO
# Provides:          netinfo
# Required-Start:    $local_fs
# Required-Stop:
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Network Info daemon
# Description:       Starts the Network Info daemon.
### END INIT INFO

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
DESC="netinfo daemon"
NAME="netinfo"
DEFAULTS_FILE=/etc/default/netinfo
PIDFILE=/var/run/netinfo.pid

. /lib/lsb/init-functions

# Read defaults file
[ -r $DEFAULTS_FILE ] && . $DEFAULTS_FILE

case "$1" in
start)  log_daemon_msg "Starting netinfo" $NAME
        start-stop-daemon --start --quiet --exec $SKYBOX_EXEC \
                          --background --pidfile $PIDFILE --make-pidfile \
                          --chuid $SKYBOX_USER --user $SKYBOX_USER \
                          -- $SKYBOX_ARGS
        log_end_msg $?
        ;;
stop)   log_daemon_msg "Stopping netinfo" $NAME
        killproc -p $PIDFILE $SKYBOX_EXEC
        RETVAL=$?
        [ $RETVAL -eq 0 ] && [ -e "$PIDFILE" ] && rm -f $PIDFILE
        log_end_msg $RETVAL
        ;;
restart) log_daemon_msg "Restarting netinfo" $NAME
        $0 stop
        $0 start
        ;;
reload|force-reload)
        log_daemon_msg "Reloading configuration not supported" $NAME
        log_end_msg 1
        ;;
status)
        status_of_proc -p $PIDFILE $SKYBOX_EXEC $NAME && exit 0 || exit $?
        ;;
*)      log_action_msg "Usage: /etc/init.d/netinfo {start|stop|status|restart|reload|force-reload}"
        exit 2
        ;;
esac
exit 0
