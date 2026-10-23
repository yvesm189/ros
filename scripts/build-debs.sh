#!/usr/bin/env bash
# Build the ROS .deb packages.
#
# The package trees under packages/ are plain filesystem layouts with a DEBIAN/
# control directory, so they build with dpkg-deb alone - no debhelper, no build
# dependencies beyond dpkg itself. On a machine without dpkg (a Mac, say) this
# script re-executes itself inside a Debian container.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(cat "${ROOT}/VERSION")"
OUT="${ROOT}/out/packages"
PACKAGES=(ros-fonts ros-branding ros-agent ros-store ros-app-defaults ros-desktop-base)
BUILDER_IMAGE="${ROS_BUILDER_IMAGE:-debian:trixie-slim}"

if ! command -v dpkg-deb >/dev/null 2>&1; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "error: neither dpkg-deb nor docker is available" >&2
        exit 1
    fi
    echo ">> no dpkg-deb on this host; building inside ${BUILDER_IMAGE}"
    exec docker run --rm \
        -v "${ROOT}:/ros" -w /ros \
        "${BUILDER_IMAGE}" \
        bash /ros/scripts/build-debs.sh "$@"
fi

mkdir -p "${OUT}"
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

for pkg in "${PACKAGES[@]}"; do
    echo ">> building ${pkg} ${VERSION}"
    src="${ROOT}/packages/${pkg}"
    dst="${STAGE}/${pkg}"
    cp -a "${src}" "${dst}"

    # Version is kept in one place (VERSION) and substituted at build time.
    sed -i "s/@VERSION@/${VERSION}/g" "${dst}/DEBIAN/control"

    # The typefaces live in branding/fonts and are staged in here, so that the
    # repository holds exactly one copy of each font rather than one per
    # consumer. The staged copies are gitignored inside the package tree.
    if [ "${pkg}" = "ros-fonts" ]; then
        cp "${ROOT}/branding/fonts"/*.ttf "${dst}/usr/share/fonts/truetype/ros/"
        cp "${ROOT}/branding/fonts"/OFL-*.txt "${dst}/usr/share/doc/ros-fonts/"
        cp "${ROOT}/branding/fonts/README.md" "${dst}/usr/share/doc/ros-fonts/"
        rm -f "${dst}/usr/share/fonts/truetype/ros/.gitignore" \
              "${dst}/usr/share/doc/ros-fonts/.gitignore"
    fi

    # Everything a package ships under /etc is a conffile: dpkg then leaves a
    # locally modified policy file alone on upgrade instead of silently
    # reverting an administrator's change.
    if [ -d "${dst}/etc" ]; then
        ( cd "${dst}" && find etc -type f | sed 's|^|/|' | sort ) > "${dst}/DEBIAN/conffiles"
    fi

    # Normalise permissions; a .deb should not inherit a developer's umask.
    find "${dst}" -type d -exec chmod 0755 {} +
    find "${dst}" -type f ! -path "${dst}/DEBIAN/*" -exec chmod 0644 {} +
    [ -d "${dst}/usr/bin" ] && chmod 0755 "${dst}"/usr/bin/* || true
    [ -f "${dst}/usr/lib/ros-agent/agent.py" ] && chmod 0755 "${dst}/usr/lib/ros-agent/agent.py"
    for script in postinst preinst prerm postrm; do
        [ -f "${dst}/DEBIAN/${script}" ] && chmod 0755 "${dst}/DEBIAN/${script}"
    done

    # md5sums, excluding the control directory itself.
    ( cd "${dst}" && find . -type f ! -path './DEBIAN/*' -printf '%P\0' \
        | xargs -0 md5sum > DEBIAN/md5sums ) 2>/dev/null || true

    dpkg-deb --root-owner-group --build "${dst}" \
        "${OUT}/${pkg}_${VERSION}_all.deb" >/dev/null
done

echo
echo ">> packages in ${OUT}:"
ls -lh "${OUT}"/*.deb
echo
for deb in "${OUT}"/*.deb; do
    echo "--- $(basename "${deb}") ---"
    dpkg-deb --info "${deb}" | sed -n '2,12p'
done
