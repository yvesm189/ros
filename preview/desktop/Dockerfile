# A ROS desktop you can log into with a VNC client.
#
# This runs a real login screen and a real GNOME session with the real ROS
# packages. It is not how ROS is deployed - that is an ISO - but it shows
# exactly what the branding, the policy and the login screen do, in about a
# minute instead of a multi-hour image build.
#
# Two things differ from a workstation, both forced by the container:
#
#   * systemd runs as PID 1, because GNOME requires logind.
#   * LightDM stands in for GDM. GDM needs a seat with a graphics device;
#     a container has a seat0 with no DRM device at all, so GDM has no display
#     to manage. LightDM has a VNC mode that starts Xvnc per connection and
#     runs its greeter on it, which is exactly the shape this needs.
FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive \
    container=docker \
    LIBGL_ALWAYS_SOFTWARE=1 \
    GALLIUM_DRIVER=llvmpipe \
    LANG=en_US.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        systemd systemd-sysv dbus dbus-user-session \
        lightdm lightdm-gtk-greeter \
        gnome-themes-extra \
        gnome-session \
        gnome-shell \
        gnome-settings-daemon \
        gnome-control-center \
        gnome-shell-extension-dashtodock \
        gnome-shell-extension-appindicator \
        nautilus \
        gnome-console \
        gnome-text-editor \
        gnome-system-monitor \
        python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
        polkitd pkexec \
        adwaita-icon-theme \
        fonts-cantarell \
        fonts-noto-core \
        dconf-cli \
        dconf-gsettings-backend \
        fontconfig \
        librsvg2-common \
        libgl1-mesa-dri \
        tigervnc-standalone-server \
        tigervnc-common \
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
COPY out/packages/ros-fonts_*.deb out/packages/ros-branding_*.deb \
     out/packages/ros-agent_*.deb out/packages/ros-store_*.deb \
     out/packages/ros-app-defaults_*.deb /tmp/ros/
RUN apt-get update \
    && apt-get install -y --no-install-recommends /tmp/ros/*.deb \
    && rm -rf /tmp/ros /var/lib/apt/lists/*

# The person who logs in. Password is set at start-up, not baked into a layer.
RUN useradd --create-home --uid 1000 --shell /bin/bash --comment "ROS User" ros

COPY preview/desktop/lightdm.conf /etc/lightdm/lightdm.conf
COPY preview/desktop/lightdm-gtk-greeter.conf /etc/lightdm/lightdm-gtk-greeter.conf
COPY preview/desktop/start.sh /usr/local/bin/ros-desktop-preview
COPY preview/desktop/ros-preview.service /etc/systemd/system/
COPY preview/desktop/ros-agent-preview.conf \
     /etc/systemd/system/ros-agent.timer.d/preview.conf
RUN chmod +x /usr/local/bin/ros-desktop-preview \
    && systemctl enable ros-preview.service \
    && systemctl enable lightdm.service

EXPOSE 5900
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
