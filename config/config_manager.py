import configparser
import os
import pwd
import argparse

class ConfigManager:
    def __init__(self, config_file='localhost.conf', config_dir = '../config', default_config_file='default_config.ini', username='pi'):
        self.config_file = config_file
        self.config_dir = config_dir
        self.default_config_file = default_config_file
        self.config = configparser.ConfigParser()
        self.username = username
        self.load_config()

    def skycam_uri(self):
        host = self.get('vision_system', 'skycam_host')
        port = self.getint('vision_system', 'skycam_port')
        return f'ws://{host}:{port}/websocket'

    def skybox_uri(self):
        host = self.get('skybox', 'server_host')
        port = self.getint('skybox', 'server_port')
        return f'ws://{host}:{port}/websocket'

    def moonraker_uri(self):
        host = self.get('skylight', 'moonraker_host')
        port = self.getint('skylight', 'moonraker_port')
        return f'ws://{host}:{port}/websocket'

    @staticmethod
    def parse_arguments():
        parser = argparse.ArgumentParser(description='Run the Skybox Control system.')
        parser.add_argument('-d', '--config-dir', type=str, help='Directory containing the configuration file')
        parser.add_argument('-f', '--config-file', type=str, help='Name of the configuration file')
        args = parser.parse_args()
        return args

    def load_config(self):
        args = self.parse_arguments()
        if args.config_file:
            self.config_file = args.config_file
        if args.config_dir:
            self.config_dir = args.config_dir
        self.config_file = os.path.join(self.config_dir, self.config_file)

        config_exists = os.path.exists(self.config_file)
        if config_exists:
            self.config.read(self.config_file)
        else:
            self.load_default_config()
            self.create_default_config()

    def load_default_config(self):
        self.default_config = configparser.ConfigParser()
        default_config_file = os.path.join(self.config_dir, self.default_config_file)
        if os.path.exists(default_config_file):
            self.default_config.read(default_config_file)
        else:
            raise FileNotFoundError(f"Default config file '{self.default_config_file}' not found.")

    def create_default_config(self):
        # Copy default config to main config
        for section in self.default_config.sections():
            if not self.config.has_section(section):
                self.config.add_section(section)
            for key, value in self.default_config.items(section):
                if not self.config.has_option(section, key):
                    self.config.set(section, key, value)

        # Write the default config to the specified config file
        with open(self.config_file, 'w') as file:
            self.config.write(file)
        try:
            user_info = pwd.getpwnam(self.username)
            os.chown(self.config_file, user_info.pw_uid, user_info.pw_gid)
        except KeyError:
            print(f"User '{self.username}' does not exist")

    def get(self, section, key, fallback=None):
        return self.config.get(section, key, fallback=fallback)

    def getint(self, section, key, fallback=None):
        return self.config.getint(section, key, fallback=fallback)

    def getboolean(self, section, key, fallback=None):
        return self.config.getboolean(section, key, fallback=fallback)

    def get_section_items(self, section):
        if self.config.has_section(section):
            return dict(self.config.items(section))
        return {}

