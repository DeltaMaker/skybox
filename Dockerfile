FROM python:3.10-slim-bookworm AS builder

# Install SSH and system dependencies
RUN apt-get update && apt-get install -y \
    openssh-server \
    build-essential \
    python3-dev \
    git \
    sudo \
    python3-venv \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Create pi user and group
RUN useradd -m -s /bin/bash pi && \
    adduser pi sudo && \
    echo "pi ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Set up SSH with proper permissions
RUN mkdir -p /var/run/sshd /home/pi/.ssh && \
    chmod 0755 /var/run/sshd && \
    chown -R pi:pi /home/pi/.ssh && \
    chmod 700 /home/pi/.ssh

# Configure SSH
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && \
    sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

# SSH login fix
RUN sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd

# Set up project directory
WORKDIR /home/pi/skybox
RUN chown -R pi:pi /home/pi/skybox

# Switch to pi user
USER pi

# Copy application code
COPY --chown=pi:pi . .

# Run setup.sh to create venv and install dependencies
RUN chmod +x setup.sh && ./setup.sh

# Switch back to root for starting services
USER root

# Expose ports
EXPOSE 22 7120 7130 7140 7150

# Create startup script
RUN echo '#!/bin/bash\n\
/usr/sbin/sshd -D &\n\
sudo -u pi bash -c "source /home/pi/skybox/venv/bin/activate && python /home/pi/skybox/skylight/skylight_server_v2.py"\n\
' > /start.sh && chmod +x /start.sh

# Start services
CMD ["/start.sh"] 