#!/bin/bash
set -e
VERSION="0.0.3"
PACKAGE_NAME="mops-messenger_${VERSION}_all.deb"
BUILD_DIR="mops-deb"

mkdir -p $BUILD_DIR/DEBIAN
mkdir -p $BUILD_DIR/usr/bin
mkdir -p $BUILD_DIR/usr/share/mops
mkdir -p $BUILD_DIR/usr/share/applications
mkdir -p $BUILD_DIR/usr/share/icons/hicolor/256x256/apps
mkdir -p $BUILD_DIR/usr/share/doc/mops

cp DEBIAN/control $BUILD_DIR/DEBIAN/
cp DEBIAN/postinst $BUILD_DIR/DEBIAN/
chmod 755 $BUILD_DIR/DEBIAN/postinst

cp usr/bin/mops $BUILD_DIR/usr/bin/
chmod 755 $BUILD_DIR/usr/bin/mops

cp usr/share/applications/mops.desktop $BUILD_DIR/usr/share/applications/
cp usr/share/icons/hicolor/256x256/apps/mops.png $BUILD_DIR/usr/share/icons/hicolor/256x256/apps/
cp usr/share/doc/mops/README $BUILD_DIR/usr/share/doc/mops/

# Копируем исходники
cp main.py gui.py xmpp_client.py config.py requirements.txt $BUILD_DIR/usr/share/mops/

chmod 644 $BUILD_DIR/usr/share/mops/*.py
chmod 644 $BUILD_DIR/usr/share/mops/requirements.txt

dpkg-deb --build $BUILD_DIR $PACKAGE_NAME
echo "✅ Пакет создан: $PACKAGE_NAME"