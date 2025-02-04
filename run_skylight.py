from skylight.skylight_server import SkylightServer
from config.config_manager import ConfigManager

def main():
    config_manager = ConfigManager(config_file="localhost.conf", config_dir="config")
    skylight_server = SkylightServer(config_manager)
    skylight_server.start()

if __name__ == "__main__":
    main() 