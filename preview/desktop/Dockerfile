# A ROS desktop you can open in a browser.
#
# This runs the real GNOME session with the real ros-branding package and the
# real management agent, rendered by Xvfb and served over noVNC. It is not how
# ROS is deployed - that is an ISO - but it shows exactly what the branding and
# the policy do, in about a minute instead of a multi-hour image build.
#
# systemd runs as PID 1 because GNOME Shell 48 requires logind: it asks
# org.freedesktop.login1 about the session before it will draw anything, and
# there is no way to opt out. That also means the agent runs on its real
# systemd timer here rather than on a shell loop.
FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive \
    container=docker \
    DISPLAY=:0 \
    LIBGL_ALWAYS_SOFTWARE=1 \
    GALLIUM_DRIVER=llvmpipe \
    NO_AT_BRIDGE=1 \
    LANG=en_US.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        systemd systemd-sysv dbus dbus-user-session \
        gnome-shell \
        gnome-settings-daemon \
        gnome-control-center \
        gnome-shell-extension-dashtodock \
        gnome-shell-extension-appindicator \
        nautilus \
        firefox-esr \
        gnome-console \
        gnome-text-editor \
        gnome-system-monitor \
        adwaita-icon-theme \
        fonts-inter \
        fonts-cantarell \
        fonts-noto-core \
        dconf-cli \
        dconf-gsettings-backend \
        librsvg2-common \
        libgl1-mesa-dri \
        xvfb \
        xdotool \
        x11vnc \
        novnc \
        websockify \
        dbus-x11 \
        xdg-user-dirs \
        locales \
        python3 \
        ca-certificates \
        procps \
    && sed -i 's/^# *\(en_US.UTF-8\)/\1/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

# Units that have nothing to manage in a container and only add noise.
RUN systemctl mask \
        systemd-udevd.service systemd-udev-trigger.service \
        systemd-firstboot.service systemd-machine-id-commit.service \
        getty.target console-getty.service \
        systemd-networkd-wait-online.service

# The ROS packages, exactly as a workstation gets them.
COPY out/packages/ros-branding_*.deb out/packages/ros-agent_*.deb /tmp/ros/
RUN apt-get update \
    && apt-get install -y --no-install-recommends /tmp/ros/*.deb \
    && rm -rf /tmp/ros /var/lib/apt/lists/*

# GNOME refuses to run a session as root, so the desktop has a user.
RUN useradd --create-home --uid 1000 --shell /bin/bash ros \
    && passwd -d ros

COPY preview/desktop/start.sh /usr/local/bin/ros-desktop-preview
COPY preview/desktop/ros-preview.service /etc/systemd/system/
COPY preview/desktop/ros-agent-preview.conf \
     /etc/systemd/system/ros-agent.timer.d/preview.conf
RUN chmod +x /usr/local/bin/ros-desktop-preview \
    && systemctl enable ros-preview.service

EXPOSE 6080
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
