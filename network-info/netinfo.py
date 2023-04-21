#
# Flask app to display the DeltaMaker Network Info page
#

from flask import Flask, render_template
import subprocess

app = Flask(__name__)
port = 8088

def run_command(cmd_line):
    try:
        result = subprocess.check_output([cmd_line], shell=True)
        result_str = result.decode("utf-8")
    except subprocess.CalledProcessError as e:
        print ("exception: ", e)
        return ""
    return result_str.strip()

@app.route("/")
def main():
    eth0_cmd = "/sbin/ifconfig eth0 | grep 'inet ' | awk '{ print $2}'"
    eth0_cmd2 = "/sbin/ifconfig eth0 | grep 'ether ' | awk '{ print $2}'"
    wlan0_cmd = "/sbin/ifconfig wlan0 | grep 'inet ' | awk '{ print $2}'"
    hostname_cmd = "hostname"

    ethernet_str = run_command(eth0_cmd)
    ethermac_str = run_command(eth0_cmd2)
    wifi_str = run_command(wlan0_cmd)
    hostname_str = run_command(hostname_cmd) + '.local'

    print ("output=", ethernet_str, ethermac_str, wifi_str, hostname_str)
    return render_template('main.html',title="Network Info Page", 
        ethernet=ethernet_str, ethermac=ethermac_str, 
        wifi=wifi_str, hostname=hostname_str)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
